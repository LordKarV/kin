"""Transport-agnostic call pipeline: ASR final -> LiveWorld scan -> grounded MT per listener language -> TTS -> listener,
with per-stage latencies. Used by the LiveKit room agent (rtc/agent.py).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..db import models as m
from ..db.session import session_scope
from ..world import clock
from .asr import ASRSession, make_asr
from .tts import TTS, get_tts

log = logging.getLogger("kin.pipeline")
_LAT_LOCK = threading.Lock()  # Known limit: one global lock; per-utterance locks if merges ever contend
ASR_RETRY_S = 2.0  # Known limit: fixed backoff after a failed ASR connect; exponential if Muse ever rate-limits reconnects
INFLIGHT_WAIT_S = 8.0  # leave() waits this long for a final still in MT (about 2 s) so it is stored and extracted
SendJSON = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]


@dataclass
class Side:
    role: str                    # "participant"
    person: str                  # slug
    lang: str                    # language this side speaks
    send_json: SendJSON
    send_bytes: SendBytes
    asr: ASRSession | None = None
    asr_task: asyncio.Task | None = None
    voice_id: str = ""
    speech_end_at: float = 0.0   # perf_counter when the last final was received
    wants_audio: bool = True     # False for a leg that only takes captions
    token: str = field(default_factory=lambda: uuid.uuid4().hex)  # identifies this connection (reconnects reuse the identity)
    identity: str = ""           # sides key: f"p{person_id}"
    person_id: int | None = None
    tts_lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one utterance's audio at a time per listener
    voice_on: bool = False       # translated voice is opt-in, captions are the default
    name: str = ""
    asr_retry_at: float = 0.0    # time.monotonic() before which on_audio does not reopen a failed ASR
    inflight: asyncio.Task | None = None  # the ASR final in MT/persist/cards (survives the ASR loop's cancel)


@dataclass
class CallSession:
    call_id: int
    family_id: int
    tts: TTS
    sides: dict[str, Side] = field(default_factory=dict)
    bg_tasks: set = field(default_factory=set)  # TTS and card tasks (a reference keeps them from being GC'd mid-flight)
    world: Any = None            # app.world.live.LiveWorld
    paused_by: int | None = None
    paused: bool = False
    world_history: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)  # target lang -> last 6

    async def join(self, identity: str, person: str, send_json: SendJSON, send_bytes: SendBytes, wants_audio: bool = True,
                   start_asr: bool = True, *, lang: str | None = None, person_id: int | None = None) -> Side:
        """Calls are private: only a verified participant (person_id from the rtc token, keyed f"p{id}") gets in."""
        if person_id is None or identity != f"p{person_id}":
            raise PermissionError("calls need a verified participant")
        return await self._join_world(identity, person, send_json, send_bytes, wants_audio, start_asr, lang or "en", person_id)

    async def _stop_asr(self, side: Side) -> None:
        asr, side.asr = side.asr, None  # cleared first, so the loop's finally knows this stop was ours and stays quiet
        if side.asr_task:
            side.asr_task.cancel()
        if asr:
            await _close_asr(asr)

    async def leave(self, role: str, token: str | None = None) -> None:
        side = self.sides.get(role)
        if not side or (token is not None and side.token != token):
            return  # a stale connection must not evict the live one
        self.sides.pop(role, None)
        await self._stop_asr(side)  # first, so no new final starts while we wait for the one in flight
        t = side.inflight
        if t is not None and not t.done():  # hanging up right after a line must not lose it (stored, captioned, extracted)
            # Known limit: a line Muse is still endpointing is still lost; it needs an endStream flush before the cancel
            _, late = await asyncio.wait({t}, timeout=INFLIGHT_WAIT_S)
            if late:
                log.warning("final from %s still in flight after %ss; leaving before it lands", role, INFLIGHT_WAIT_S)
        if role in self.sides:  # rejoined while we waited: world.join already ran for the new connection
            return
        try:
            await asyncio.to_thread(self.world.leave, role)
        except Exception as e:  # noqa: BLE001
            log.warning("LiveWorld.leave failed for %s: %s", role, e)
        await self._send_participants()

    # ---- audio in -----------------------------------------------------------
    async def _start_asr(self, side: Side, reopen: bool = False) -> None:
        asr = None
        try:
            others = [o.lang for i, o in self.sides.items() if i != side.identity]
            asr = side.asr = make_asr(language=side.lang, keyterms=self.world.keyterms(side.identity), others=others)
            await asr.start()
        except Exception as e:  # noqa: BLE001
            # clear the dead session so on_audio reopens after the backoff; left in place, the side stayed deaf all call
            if side.asr is asr:
                side.asr = None
            side.asr_retry_at = time.monotonic() + ASR_RETRY_S
            log.warning("ASR unavailable for %s (%s); retrying in %ss, typed input still works", side.identity, e, ASR_RETRY_S)
            if asr is not None:
                await _close_asr(asr)  # a handshake that connected but got no sessionId still holds a socket
            await self._safe_send(side, {"type": "status", "asr": "unavailable", "detail": str(e)[:200]})
            return
        if side.asr is not asr:  # the side left or reconnected while we were connecting
            await _close_asr(asr)
            return
        side.asr_task = asyncio.create_task(self._asr_loop(side, asr))
        if reopen:  # clears the "ended"/"unavailable" banner; the first start stays quiet so "joined" comes first
            await self._safe_send(side, {"type": "status", "asr": "ok", "detail": ""})

    async def _asr_loop(self, side: Side, asr: ASRSession | None = None) -> None:
        asr = asr or side.asr
        try:
            async for ev in asr.events():
                await self._world_event(side, ev)
        finally:
            # still ours: the provider closed the stream. A deliberate stop (leave, reconnect) already cleared it and
            # stays quiet: its "ended" could reach the rejoined client (same LiveKit identity), with no "ok" to follow
            if side.asr is asr:
                side.asr = None
                await self._safe_send(side, {"type": "status", "asr": "ended", "detail": "ASR stream closed; reconnecting. Typed input still works."})

    async def on_audio(self, role: str, pcm16: bytes) -> None:
        side = self.sides.get(role)
        if not side or self.paused:  # paused: frames are dropped before ASR (privacy)
            return
        if side.asr is None:  # (re)open lazily: first frame after a drop restarts the provider stream
            if time.monotonic() < side.asr_retry_at:
                return
            await self._start_asr(side, reopen=True)
            if side.asr is None:
                return
        try:
            await side.asr.send_audio(pcm16)
        except Exception as e:  # noqa: BLE001  (provider socket closed; never take the user's call down)
            log.warning("ASR send failed (%s); stream will be reopened on the next frame", e)
            await self._stop_asr(side)
            await self._safe_send(side, {"type": "status", "asr": "ended", "detail": str(e)[:200]})

    async def _safe_send(self, side: Side, msg: dict) -> None:
        try:
            await side.send_json(msg)
        except Exception as e:  # noqa: BLE001  (a dead leg must not break the call, but say so)
            log.warning("send %s to %s failed: %s", msg.get("type"), side.identity, e)

    async def on_text(self, role: str, text: str) -> None:
        side = self.sides.get(role)
        if side and text.strip() and not self.paused:
            side.speech_end_at = time.perf_counter()
            await self._world_final(side, text.strip())

    # ---- the pipeline -------------------------------------------------------
    async def _join_world(self, identity: str, person: str, send_json: SendJSON, send_bytes: SendBytes, wants_audio: bool,
                          start_asr: bool, lang: str, person_id: int | None) -> Side:
        side = Side("participant", person, lang, send_json, send_bytes, wants_audio=wants_audio, identity=identity,
                    person_id=person_id, name=await asyncio.to_thread(_person_name, person_id) or person)
        old = self.sides.get(identity)
        if old is not None:  # reconnect: the new connection replaces the old one and keeps the listener's voice choice
            side.voice_on = old.voice_on
            await self._stop_asr(old)
        self.sides[identity] = side
        try:  # blocking: view rebuild, knowledge cache, prewarm
            await asyncio.to_thread(self.world.join, identity, person_id, lang)
        except Exception as e:  # noqa: BLE001  (the call still works without cards)
            log.exception("LiveWorld.join failed for %s: %s", identity, e)
        if start_asr:
            await self._start_asr(side)
        kin = await self._kin_state()
        await self._safe_send(side, {"type": "joined", "call_id": self.call_id, "identity": identity, "person": person,
                                     "name": side.name, "lang": lang, "role": side.role, "peer_present": len(self.sides) > 1,
                                     "participants": self._participants(identity), "kin": kin})
        await self._send_participants()
        await self._safe_send(side, {"type": "kin_status", **kin})
        return side

    def _participants(self, exclude: str) -> list[dict]:
        return [{"identity": s.identity, "person": s.person, "name": s.name, "lang": s.lang}
                for i, s in self.sides.items() if i != exclude]

    async def _send_participants(self) -> None:
        for i, s in list(self.sides.items()):
            await self._safe_send(s, {"type": "participants", "participants": self._participants(i)})

    async def _kin_state(self) -> dict:
        if not self.paused:
            return {"on": True, "paused_by": None}
        by = next((s for s in self.sides.values() if s.person_id == self.paused_by), None)
        if by is not None:
            return {"on": False, "paused_by": {"person": by.person, "name": by.name}}
        slug, name = await asyncio.to_thread(_person_ref, self.paused_by)
        return {"on": False, "paused_by": {"person": slug, "name": name} if slug else None}

    async def set_paused(self, by_person_id: int | None, paused: bool) -> dict:
        """Anyone in the call can pause KIN; everyone is told (privacy). Returns the kin state."""
        self.paused, self.paused_by = paused, (by_person_id if paused else None)
        kin = await self._kin_state()
        for s in list(self.sides.values()):
            await self._safe_send(s, {"type": "kin_status", **kin})
        return kin

    async def _send_to(self, identity: str, msg: dict) -> None:
        """deliver(identity, msg): the LiveWorld emit callback and the only way world messages leave the session."""
        side = self.sides.get(identity)
        if side is not None:
            await self._safe_send(side, msg)

    async def _deliver(self, sends: dict | None) -> None:
        for identity, msgs in (sends or {}).items():
            for msg in msgs:
                await self._send_to(identity, msg)

    async def _world_event(self, side: Side, ev) -> None:
        if self.paused:
            return
        try:
            if not ev.final:
                msg = {"type": "partial", "speaker": side.identity, "person": side.person, "role": side.role,
                       "lang": side.lang, "text": ev.text}
                for s in list(self.sides.values()):
                    await self._safe_send(s, msg)
                await self._deliver(self.world.on_partial(side.identity, ev.text))  # sync, in memory
                return
            side.speech_end_at = time.perf_counter()
            # shielded: hanging up cancels this ASR loop, and leave() waits for the line instead of cutting it mid-MT
            side.inflight = asyncio.ensure_future(
                self._world_final(side, ev.text, lang_tags=ev.lang_tags, t_start=ev.t_start, t_end=ev.t_end))
            await asyncio.shield(side.inflight)
        except Exception as e:  # noqa: BLE001
            log.exception("world utterance failed: %s", e)
            await self._safe_send(side, {"type": "error", "stage": "pipeline", "message": str(e)[:200]})

    async def _world_final(self, side: Side, text: str, lang_tags=(), t_start: float = 0.0, t_end: float = 0.0) -> dict | None:
        if self.paused:
            return None
        t0 = time.perf_counter()
        try:
            fr = await asyncio.to_thread(self.world.on_final, side.identity, text)  # writes card_log: off the loop
        except Exception as e:  # noqa: BLE001  (a card-engine bug must not silence captions)
            log.exception("LiveWorld.on_final failed: %s", e)
            from ..world.live import FinalResult  # local: live imports heavy deps
            fr = FinalResult({}, [])
        scan_ms = round((time.perf_counter() - t0) * 1000, 1)
        await self._deliver(fr.sends)
        return await self._process_world(side, text, spans=fr.spans, lang_tags=lang_tags, t_start=t_start, t_end=t_end,
                                         t0=t0, scan_ms=scan_ms)

    async def _process_world(self, side: Side, text: str, spans=(), lang_tags=(), t_start: float = 0.0, t_end: float = 0.0,
                             t0: float | None = None, scan_ms: float = 0.0) -> dict | None:
        """One MT call per distinct target language, one Utterance, one transcript per listener."""
        if self.paused:
            return None
        t0 = t0 or time.perf_counter()
        listeners = [s for i, s in self.sides.items() if i != side.identity]
        audience = [s.person_id for s in listeners if s.person_id]
        groups: dict[str, list[Side]] = {}
        for L in listeners:
            if L.lang != side.lang:
                groups.setdefault(L.lang, []).append(L)
        spans = list(spans)
        res = dict(zip(groups, await asyncio.gather(*(self._translate_group(side, text, lang, Ls, spans)
                                                      for lang, Ls in groups.items()))))
        if self.paused:  # paused during MT: nothing transcribed, stored, carded or counted as evidence
            return None
        lat = {"scan_ms": scan_ms, "asr_ms": round((t0 - side.speech_end_at) * 1000, 1) if side.speech_end_at else 0.0}
        for lang, r in res.items():
            lat[f"mt_ms_{lang}"] = r.latencies.get("mt_ms", 0.0) if r else 0.0
        if res:
            lat["a_ms"] = lat["mt_ms"] = max(lat[f"mt_ms_{lang}"] for lang in res)
        translations = {lang: r.result.translation for lang, r in res.items() if r}
        first = next((r for r in res.values() if r), None)
        uid = await asyncio.to_thread(self._persist_world, side, listeners, audience, text, list(lang_tags), t_start, t_end,
                                      first, translations, lat)
        for lang, r in res.items():
            if r:
                h = [*self.world_history.get(lang, []), (side.person, text, r.result.translation)]
                self.world_history[lang] = h[-6:]
        base = {"type": "transcript", "call_id": self.call_id, "utterance_id": uid, "speaker": side.person,
                "speaker_identity": side.identity, "role": side.role, "src_text": text, "src_lang": side.lang,
                "src_lang_tags": list(lang_tags), "heritage_lang": side.lang, "latencies": lat}
        for L in [*listeners, side]:  # each listener only their own rendering; the speaker gets their own line back
            r = res.get(L.lang) if L is not side else None
            mt_failed = L is not side and L.lang != side.lang and r is None
            await self._safe_send(L, {**base, **self._render_for(L, r, spans, mt_failed), "listener": None if L is side else L.person,
                                      "target_lang": L.lang})
        for lang, Ls in groups.items():
            r = res[lang]
            if r is None:
                continue
            voiced = [L for L in Ls if L.wants_audio and L.voice_on]
            if voiced and r.result.translation:
                self._bg(self._tts_world(side, uid, lang, voiced, r.result.translation, lat))
            if r.cards is not None:
                self._bg(self._enrich_world(side, uid, Ls, r.cards))
        t_cards = time.perf_counter()
        try:
            sends = await asyncio.to_thread(self.world.on_translated, side.identity, uid, text, translations, audience)
            await self._deliver(sends)
        except Exception as e:  # noqa: BLE001  (cards are optional; the transcript already went out)
            log.exception("LiveWorld.on_translated failed: %s", e)
        lat["cards_ms"] = round((time.perf_counter() - t_cards) * 1000, 1)
        lat["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        await asyncio.to_thread(self._merge_latencies, uid, lat)
        for s in list(self.sides.values()):
            await self._safe_send(s, {"type": "latency", "utterance_id": uid, "latencies": dict(lat)})
        return {"utterance_id": uid, "translations": translations, "latencies": lat}

    async def _translate_group(self, side: Side, text: str, lang: str, Ls: list[Side], spans: list[dict]):
        try:
            tr = self.world.translator(side.lang)  # linker and kin table of the speaker's language
            roster = self.world.roster([L.identity for L in Ls], side.identity)
            listener = Ls[0].person if len(Ls) == 1 else None
            return await asyncio.to_thread(tr.translate_speech, text, side.person, listener, self.world_history.get(lang, []),
                                           (), None, lang, extra_spans=spans, roster=roster)
        except Exception as e:  # noqa: BLE001  (translate_speech already falls back on LLM errors; this is the rest)
            log.exception("world translation to %s failed: %s", lang, e)
            for L in Ls:
                await self._safe_send(L, {"type": "error", "stage": "mt", "message": str(e)[:200]})
            return None

    def _render_for(self, L: Side, r, spans: list[dict], mt_failed: bool = False) -> dict:
        """Transcript fields for one listener. Spans are re-rendered for L; a node L cannot see becomes its surface text
        with node_id null."""
        def view(source: str, node_id: str | None) -> tuple[str, str | None]:
            rendered = self.world.render(L.identity, node_id) if node_id else None
            return (rendered, node_id) if rendered is not None else (source, None)

        def linker(d: dict) -> dict:
            rendered, node = view(d.get("source", ""), d.get("node_id"))
            return {**d, "rendered": rendered, "node_id": node, "candidates": [] if node is None else d.get("candidates", [])}

        if r is None:
            ls = [linker(d) for d in spans]
            return {"translation": None, "grounded_spans": [{"source": d["source"], "rendered": d["rendered"], "node_id": d["node_id"]}
                                                            for d in ls if d.get("source")],
                    "pragmatics_cards": [], "passthrough": [], "confidence": 1.0, "linker_spans": ls, "error": "mt" if mt_failed else None}
        gs = []
        for g in r.result.grounded_spans:
            rendered, node = view(g.source, g.node_id)
            gs.append({"source": g.source, "rendered": rendered, "node_id": node})
        return {"translation": r.result.translation, "grounded_spans": gs,
                "pragmatics_cards": [c.model_dump() for c in r.result.pragmatics_cards], "passthrough": list(r.passthrough),
                "confidence": r.result.confidence, "linker_spans": [linker(s.as_dict()) for s in r.spans], "error": r.error}

    def _bg(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.bg_tasks.add(task)
        task.add_done_callback(self.bg_tasks.discard)

    async def _tts_world(self, side: Side, uid: int, lang: str, Ls: list[Side], text: str, lat: dict) -> None:
        """One TTS stream per language, fanned out to that language's voiced listeners. Holding every listener's
        tts_lock keeps each leg's audio in utterance order (asyncio.Lock is FIFO)."""
        Ls = sorted(Ls, key=lambda s: s.identity)  # fixed lock order: two tasks never deadlock
        for L in Ls:
            await L.tts_lock.acquire()
        t_tts, first = time.perf_counter(), None
        try:
            live = list(Ls)
            for L in live:
                await self._safe_send(L, {"type": "audio_start", "utterance_id": uid, "lang": lang})
            try:
                async for chunk in self.tts.stream(text, voice_id=side.voice_id, language_code=lang):
                    if first is None:
                        first = time.perf_counter()
                    for L in list(live):
                        try:
                            await L.send_bytes(chunk)
                        except Exception as e:  # noqa: BLE001  (one dropped leg must not cut the others)
                            log.warning("TTS send to %s failed: %s", L.identity, e)
                            live.remove(L)
            except Exception as e:  # noqa: BLE001  (TTS 4xx: captions already went out)
                log.warning("TTS failed: %s", e)
                for L in live:
                    await self._safe_send(L, {"type": "error", "stage": "tts", "message": str(e)[:200]})
            for L in Ls:
                await self._safe_send(L, {"type": "audio_end", "utterance_id": uid})
        finally:
            for L in Ls:
                L.tts_lock.release()
        ms = round(((first or time.perf_counter()) - t_tts) * 1000, 1)
        lat[f"tts_first_byte_ms_{lang}"] = ms
        lat["tts_first_byte_ms"] = max(ms, lat.get("tts_first_byte_ms", 0.0))
        await asyncio.to_thread(self._merge_latencies, uid, {k: v for k, v in lat.items() if k.startswith("tts_")})
        for L in Ls:
            await self._safe_send(L, {"type": "latency", "utterance_id": uid, "latencies": dict(lat)})

    async def _enrich_world(self, side: Side, uid: int, Ls: list[Side], cards_future) -> None:
        """Call B for one language group: cards to that group, then "Who is X?" asks for names nobody resolved."""
        try:
            out = await asyncio.wrap_future(cards_future)
            cards, b_ms = out[0], out[1]
            new_people = out[2] if len(out) > 2 else []  # (cards, b_ms, new_people) with a roster
            msg = {"type": "enrich", "utterance_id": uid, "pragmatics_cards": [c.model_dump() for c in cards], "b_ms": b_ms}
            for L in Ls:
                await self._safe_send(L, msg)
            await asyncio.to_thread(self._merge_latencies, uid, {"b_ms": b_ms})
            if new_people:
                await self._deliver(await asyncio.to_thread(self.world.asks, side.identity, [L.identity for L in Ls], new_people))
        except Exception as e:  # noqa: BLE001  (enrichment is optional)
            log.warning("world enrichment failed for utterance %s: %s", uid, e)

    def _persist_world(self, side: Side, listeners: list[Side], audience: list[int], text: str, lang_tags: list, t_start: float,
                       t_end: float, first, translations: dict, lat: dict) -> int:
        with session_scope() as s:
            u = m.Utterance(call_id=self.call_id, speaker_id=side.person_id, created_at=clock.now(),  # dev clock: said_at
                            listener_id=next((L.person_id for L in listeners if L.person_id), None), t_start=t_start, t_end=t_end,
                            src_text=text, src_lang_tags=lang_tags, lang=side.lang, audience=audience, translations=translations,
                            translation=first.result.translation if first else "",
                            grounded_spans=[sp.model_dump() for sp in first.result.grounded_spans] if first else [],
                            passthrough=list(first.passthrough) if first else [], latencies=dict(lat))
            s.add(u); s.flush()
            return u.id

    def _merge_latencies(self, utterance_id: int, lat: dict) -> None:
        # TTS, B and the main path merge from worker threads; read-modify-write must not interleave
        with _LAT_LOCK, session_scope() as s:
            u = s.get(m.Utterance, utterance_id)
            if u:
                u.latencies = {**(u.latencies or {}), **lat}


async def _close_asr(asr: ASRSession) -> None:
    try:
        await asr.finish()
    except Exception as e:  # noqa: BLE001  (the provider socket is often already gone)
        log.debug("ASR finish failed: %s", e)


def _person_ref(person_id: int | None) -> tuple[str, str]:
    if person_id is None:
        return "", ""
    with session_scope() as s:
        p = s.get(m.Person, person_id)
        return (p.slug, p.display_name) if p else ("", "")


def _person_name(person_id: int | None) -> str:
    return _person_ref(person_id)[1]


def _end_world(cs: CallSession) -> None:
    from ..world.privacy import run_sweep
    try:
        cs.world.close()
    except Exception:  # noqa: BLE001
        log.exception("LiveWorld.close failed for call %s", cs.call_id)
    try:
        run_sweep()
    except Exception:  # noqa: BLE001
        log.exception("third-party sweep failed after call %s", cs.call_id)


class CallRegistry:
    def __init__(self):
        self._calls: dict[int, CallSession] = {}

    def get_or_create(self, call_id: int) -> CallSession:
        if call_id not in self._calls:
            with session_scope() as s:
                call = s.get(m.Call, call_id)
                if call is None or call.mode != "world":
                    raise LookupError(f"call {call_id} is not a KIN call")
                family_id = call.family_id
            from ..world import live
            cs = CallSession(call_id=call_id, family_id=family_id, tts=get_tts())
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:  # Known limit: only a sync caller lands here; LiveWorld then has no loop for emit
                loop = None
            cs.world = live.LiveWorld(call_id, family_id, emit=cs._send_to, loop=loop)
            self._calls[call_id] = cs
        return self._calls[call_id]

    def get(self, call_id: int) -> CallSession | None:
        return self._calls.get(call_id)

    def drop_if_empty(self, call_id: int) -> None:
        cs = self._calls.get(call_id)
        if cs and not cs.sides:
            self._calls.pop(call_id, None)
            try:  # the call ended: final extraction, then the third-party sweep
                asyncio.get_running_loop().run_in_executor(None, _end_world, cs)
            except RuntimeError:
                _end_world(cs)

    def active(self) -> list[CallSession]:
        return list(self._calls.values())


registry = CallRegistry()
