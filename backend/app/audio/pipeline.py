"""Transport-agnostic call pipeline: ASR final → linker → fade policy → grounded MT → TTS → peer, with per-stage latencies.

Used by the WebSocket transport (api/ws.py) and by the optional LiveKit agent (audio/agent.py).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from sqlalchemy import select

from ..config import get_settings
from ..db import models as m
from ..db.session import session_scope
from ..mt.translate import Translator, get_translator
from .asr import ASRSession, make_asr
from .tts import TTS, get_tts

log = logging.getLogger("kin.pipeline")
SendJSON = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]


@dataclass
class Side:
    role: str                    # grandparent | grandchild
    person: str                  # slug
    lang: str                    # language this side speaks (ta / en)
    send_json: SendJSON
    send_bytes: SendBytes
    asr: ASRSession | None = None
    asr_task: asyncio.Task | None = None
    voice_id: str = ""
    speech_end_at: float = 0.0   # perf_counter when the last final was received


@dataclass
class CallSession:
    call_id: int
    family_id: int
    translator: Translator
    tts: TTS
    sides: dict[str, Side] = field(default_factory=dict)
    history: list[tuple[str, str, str]] = field(default_factory=list)  # (speaker slug, src, translation)
    fade: Callable | None = None   # Phase 4: (listener_slug, text) -> list[str] passthrough tokens
    on_utterance: Callable | None = None  # Phase 4/6 hook: (utterance dict) -> None

    # ---- membership --------------------------------------------------------
    async def join(self, role: str, person: str, send_json: SendJSON, send_bytes: SendBytes) -> Side:
        heritage = self.translator.g.heritage_lang
        lang = heritage if role == "grandparent" else "en"
        side = Side(role, person, lang, send_json, send_bytes)
        node = self.translator.g.by_slug.get(person)
        side.voice_id = getattr(node, "voice_id", "") or ""
        self.sides[role] = side
        await self._start_asr(side)
        await send_json({"type": "joined", "role": role, "person": person, "call_id": self.call_id, "peer_present": self.peer(role) is not None})
        peer = self.peer(role)
        if peer:
            await peer.send_json({"type": "peer", "present": True, "person": person})
        return side

    async def leave(self, role: str) -> None:
        side = self.sides.pop(role, None)
        if not side:
            return
        if side.asr:
            await side.asr.finish()
        if side.asr_task:
            side.asr_task.cancel()
        peer = self.peer(role)
        if peer:
            try:
                await peer.send_json({"type": "peer", "present": False})
            except Exception:  # noqa: BLE001
                pass

    def peer(self, role: str) -> Side | None:
        return next((s for r, s in self.sides.items() if r != role), None)

    # ---- audio in -----------------------------------------------------------
    async def _start_asr(self, side: Side) -> None:
        try:
            side.asr = make_asr(language=side.lang, keyterms=self.translator.linker.keyterms())
            await side.asr.start()
            side.asr_task = asyncio.create_task(self._asr_loop(side))
        except Exception as e:  # noqa: BLE001
            log.warning("ASR unavailable for %s (%s); typed input still works", side.role, e)
            await side.send_json({"type": "status", "asr": "unavailable", "detail": str(e)[:200]})

    async def _asr_loop(self, side: Side) -> None:
        async for ev in side.asr.events():
            if not ev.final:
                await self._broadcast({"type": "partial", "role": side.role, "text": ev.text})
                continue
            side.speech_end_at = time.perf_counter()
            await self.process_utterance(side, ev.text, lang_tags=ev.lang_tags, t_start=ev.t_start, t_end=ev.t_end)

    async def on_audio(self, role: str, pcm16: bytes) -> None:
        side = self.sides.get(role)
        if side and side.asr:
            await side.asr.send_audio(pcm16)

    async def on_text(self, role: str, text: str) -> None:
        side = self.sides.get(role)
        if side and text.strip():
            side.speech_end_at = time.perf_counter()
            await self.process_utterance(side, text.strip())

    # ---- the pipeline -----------------------------------------------------
    async def process_utterance(self, side: Side, text: str, lang_tags=(), t_start: float = 0.0, t_end: float = 0.0) -> dict:
        t0 = time.perf_counter()
        peer = self.peer(side.role)
        listener = peer.person if peer else self._default_listener(side)
        target_lang = (peer.lang if peer else ("en" if side.role == "grandparent" else self.translator.g.heritage_lang))
        passthrough = self.fade(listener, text) if (self.fade and target_lang == "en") else []
        res = await asyncio.to_thread(self.translator.translate, text, side.person, listener, self.history, passthrough, None, target_lang)
        lat = dict(res.latencies)
        lat["asr_ms"] = round((t0 - side.speech_end_at) * 1000, 1) if side.speech_end_at else 0.0
        payload = {"type": "transcript", "call_id": self.call_id, "speaker": side.person, "listener": listener, "role": side.role,
                   "src_text": text, "src_lang_tags": list(lang_tags), "target_lang": target_lang, **res.as_dict(), "latencies": lat}
        # persist first so the UI gets an id, then show text immediately (audio follows)
        payload["utterance_id"] = self._persist(side, listener, text, list(lang_tags), t_start, t_end, res, lat)
        self.history.append((side.person, text, res.result.translation)); self.history = self.history[-6:]
        await self._broadcast(payload)
        # TTS to the peer, measuring first byte
        if peer and res.result.translation:
            t_tts = time.perf_counter()
            first = None
            try:
                await peer.send_json({"type": "audio_start", "utterance_id": payload["utterance_id"]})
                async for chunk in self.tts.stream(res.result.translation, voice_id=side.voice_id, language_code=target_lang):
                    if first is None:
                        first = time.perf_counter()
                    await peer.send_bytes(chunk)
                await peer.send_json({"type": "audio_end", "utterance_id": payload["utterance_id"]})
            except Exception as e:  # noqa: BLE001
                log.warning("TTS failed: %s", e)
                await peer.send_json({"type": "error", "stage": "tts", "message": str(e)[:200]})
            lat["tts_first_byte_ms"] = round(((first or time.perf_counter()) - t_tts) * 1000, 1)
        else:
            lat["tts_first_byte_ms"] = 0.0
        lat["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        payload["latencies"] = lat
        self._update_latencies(payload["utterance_id"], lat)
        await self._broadcast({"type": "latency", "utterance_id": payload["utterance_id"], "latencies": lat})
        if self.on_utterance:
            try:
                r = self.on_utterance(payload)
                if asyncio.iscoroutine(r):
                    await r
            except Exception as e:  # noqa: BLE001
                log.warning("on_utterance hook failed: %s", e)
        return payload

    def _default_listener(self, side: Side) -> str:
        g = self.translator.g
        learner = next((p.slug for p in g.people.values() if p.is_learner), None)
        if side.role == "grandparent":
            return learner or side.person
        return next((p.slug for p in g.people.values() if not p.is_learner and p.slug != side.person), side.person)

    async def _broadcast(self, msg: dict) -> None:
        for s in list(self.sides.values()):
            try:
                await s.send_json(msg)
            except Exception as e:  # noqa: BLE001
                log.debug("send failed to %s: %s", s.role, e)

    def _persist(self, side, listener, text, lang_tags, t_start, t_end, res, lat) -> int:
        g = self.translator.g
        with session_scope() as s:
            u = m.Utterance(call_id=self.call_id, speaker_id=g.by_slug[side.person].id if side.person in g.by_slug else None,
                            listener_id=g.by_slug[listener].id if listener in g.by_slug else None, t_start=t_start, t_end=t_end,
                            src_text=text, src_lang_tags=lang_tags, translation=res.result.translation,
                            grounded_spans=[sp.model_dump() for sp in res.result.grounded_spans],
                            cards=[c.model_dump() for c in res.result.pragmatics_cards], passthrough=res.passthrough, latencies=lat)
            s.add(u); s.flush()
            for c in res.result.pragmatics_cards:
                s.add(m.GlossaryEntry(family_id=self.family_id, card=c.model_dump(), utterance_id=u.id, speaker_id=u.speaker_id))
            return u.id

    def _update_latencies(self, utterance_id: int, lat: dict) -> None:
        with session_scope() as s:
            u = s.get(m.Utterance, utterance_id)
            if u:
                u.latencies = lat


class CallRegistry:
    def __init__(self):
        self._calls: dict[int, CallSession] = {}

    def get_or_create(self, call_id: int) -> CallSession:
        if call_id not in self._calls:
            with session_scope() as s:
                call = s.get(m.Call, call_id)
                family_id = call.family_id if call else get_settings().demo_family_id
            cs = CallSession(call_id=call_id, family_id=family_id, translator=get_translator(family_id), tts=get_tts())
            from ..fade.policy import make_fade_policy  # Phase 4 (safe no-op until mastery exists)
            cs.fade = make_fade_policy(family_id)
            self._calls[call_id] = cs
        return self._calls[call_id]

    def drop_if_empty(self, call_id: int) -> None:
        cs = self._calls.get(call_id)
        if cs and not cs.sides:
            self._calls.pop(call_id, None)


registry = CallRegistry()
