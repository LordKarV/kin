"""KIN as a server-side participant in a LiveKit room (the KIN call app).

Each person joins from the app with their own audio track, so there is no "who spoke?" guesswork (unlike a merged
phone call). The agent subscribes to every person's microphone at 16 kHz and feeds it to the normal CallSession
(linker, glance cards, Fade, translation, memory). What KIN produces goes only to the person it is for:
  - JSON (partials, glance cards, transcripts, enrich cards, asks) as data messages addressed to that participant;
  - the translated voice on a per-listener track named `kin-to-<identity>`, which only that listener plays.
Participants say who they are in their token metadata: legacy {"role": "grandparent"|"grandchild", "person": "<slug>"}
or world {"person": "<slug>", "person_id": <id>, "lang": "<code>", "name": "..."} (ARCHITECTURE 8.7).
World legs publish their `kin-to-<identity>` track lazily on their first `audio_start` (sent only to listeners with
voice on), so a listener with voice off (the default) never gets one. There is no client-to-agent data handler (D17: pause, feedback and text go over REST).
Verified against livekit==1.1.21 (rtc) signatures on 2026-10-24.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from livekit import api, rtc
from sqlalchemy import update

from ..audio.pipeline import CallSession, registry
from ..config import get_settings
from ..db import models as m
from ..db.session import session_scope
from ..world import clock

log = logging.getLogger("kin.rtc")
SAMPLE_RATE = 16000
FRAME_SAMPLES = 320  # 20 ms frames into the AudioSource
QUIET_AFTER_S = 0.06  # no mic frame for this long: feed silence to the ASR (WebRTC DTX)
AGENT_IDENTITY = "kin"
DATA_TOPIC = "kin"


def livekit_creds() -> tuple[str, str, str]:
    s = get_settings()
    return (s.livekit_url or s.livekit_dev_url, s.livekit_api_key or s.livekit_dev_key,
            s.livekit_api_secret or s.livekit_dev_secret)


def room_name(call_id: int) -> str:
    return f"kin-call-{call_id}"


def participant_from_meta(identity: str, metadata_json: str | None) -> tuple[str, str, str | None, int | None] | None:
    """(session identity, person slug, lang, person_id) from token metadata, or None when it is not a KIN participant.
    World metadata (has person_id) keys the session by the LiveKit identity; legacy metadata keys it by role."""
    try:
        meta = json.loads(metadata_json or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(meta, dict):
        return None
    person = meta.get("person")
    if not isinstance(person, str) or not person:
        return None
    pid = meta.get("person_id")
    if pid is not None:
        lang = meta.get("lang")
        if isinstance(pid, bool) or not isinstance(pid, int) or not isinstance(lang, str) or not lang:
            return None
        return identity, person, lang, pid
    role = meta.get("role")
    if role in ("grandparent", "grandchild"):
        return role, person, None, None
    return None


def mint_token(room: str, identity: str, name: str, metadata: dict | None = None, agent: bool = False) -> str:
    _, key, secret = livekit_creds()
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True, can_publish_data=True, agent=agent or None)
    tok = api.AccessToken(key, secret).with_identity(identity).with_name(name).with_grants(grants)
    if metadata:
        tok = tok.with_metadata(json.dumps(metadata))
    return tok.to_jwt()


class _Leg:
    """One person in the room as a CallSession side: their data channel and their private translated-voice track."""

    def __init__(self, room: rtc.Room, identity: str, key: str, person: str, on_publish: Callable[["_Leg"], None]):
        # identity: LiveKit identity (data destination); key: CallSession side identity (role for legacy)
        self.room, self.identity, self.key, self.person = room, identity, key, person
        self.source = rtc.AudioSource(SAMPLE_RATE, 1)
        self.track = rtc.LocalAudioTrack.create_audio_track(f"kin-to-{identity}", self.source)
        self.published = False  # legacy legs publish in _join before the session starts; world legs on first audio_start
        self._on_publish = on_publish
        self._publish_lock = asyncio.Lock()
        self.token: str | None = None
        self.mic_task: asyncio.Task | None = None
        self._pending = b""

    async def ensure_track(self) -> None:
        if not self.published:
            async with self._publish_lock:
                if not self.published:
                    await self.room.local_participant.publish_track(self.track, rtc.TrackPublishOptions())
                    self.published = True
                    self._on_publish(self)

    async def send_json(self, msg: dict) -> None:
        if msg.get("type") == "audio_start":  # publish before the voice starts, so the listener can subscribe in time
            await self.ensure_track()
        await self.room.local_participant.publish_data(json.dumps(msg, ensure_ascii=False), reliable=True,
                                                       destination_identities=[self.identity], topic=DATA_TOPIC)

    async def send_bytes(self, pcm16: bytes) -> None:
        await self.ensure_track()  # no-op after audio_start; covers bytes sent without one
        buf = self._pending + pcm16
        step = FRAME_SAMPLES * 2
        cut = len(buf) - len(buf) % step
        for i in range(0, cut, step):
            await self.source.capture_frame(rtc.AudioFrame(buf[i:i + step], SAMPLE_RATE, 1, FRAME_SAMPLES))
        self._pending = buf[cut:]


class RoomAgent:
    def __init__(self, call_id: int):
        self.call_id = call_id
        self.room = rtc.Room()
        self.session: CallSession | None = None
        self.legs: dict[str, _Leg] = {}
        self.done = asyncio.Event()
        self._joining: dict[str, rtc.RemoteParticipant] = {}  # identity -> participant whose session.join is in flight
        self._tasks: set[asyncio.Task] = set()  # join/leave handlers; run() waits for them before the call can end

    async def run(self) -> None:
        url, _, _ = livekit_creds()
        self.session = registry.get_or_create(self.call_id)
        self.room.on("participant_connected", lambda p: self._spawn(self._safe_join(p)))
        self.room.on("participant_disconnected", lambda p: self._spawn(self._leave(p)))
        self.room.on("track_subscribed", lambda track, _pub, p: self._listen(track, p))
        await self.room.connect(url, mint_token(room_name(self.call_id), AGENT_IDENTITY, "KIN", agent=True))
        self._restrict_voice()  # before any publish: nobody may subscribe to a kin-to-* track until it is theirs
        log.info("KIN agent in %s", room_name(self.call_id))
        for p in list(self.room.remote_participants.values()):
            await self._safe_join(p)
        try:
            await self.done.wait()
        finally:
            # a leave still waiting for its last line (or a join still connecting) must finish before the call can
            # end, or drop_if_empty runs the call-end extraction without that line (or never, with a zombie side)
            # only pending ones: the last _leave sets done and returns in one step, so its discard callback is still
            # queued when we wake, and gathering only done tasks never yields (the whole loop spun at 100% CPU)
            while pending := [t for t in self._tasks if not t.done()]:
                await asyncio.wait(pending)
            await self.room.disconnect()
            registry.drop_if_empty(self.call_id)
            log.info("KIN agent left %s", room_name(self.call_id))

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._reap)

    def _reap(self, t: asyncio.Task) -> None:
        self._tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            log.error("KIN join/leave in call %s failed", self.call_id, exc_info=t.exception())

    def _restrict_voice(self, leg: _Leg | None = None) -> None:
        """Only <identity> may subscribe to kin-to-<identity>: it carries that listener's private grounding (the client
        also plays only its own, Routing.swift). Each call replaces the whole set, so it lists every published leg."""
        legs = {x.identity: x for x in self.legs.values() if x.published}
        if leg is not None:  # a legacy leg publishes before _join registers it
            legs[leg.identity] = leg
        perms = [rtc.ParticipantTrackPermission(participant_identity=i, allowed_track_sids=[x.track.sid])
                 for i, x in legs.items()]
        try:  # sync in livekit 1.1.21 (an FFI request), not a coroutine
            self.room.local_participant.set_track_subscription_permissions(allow_all_participants=False,
                                                                           participant_permissions=perms)
        except Exception as e:  # noqa: BLE001  (fails open to the old behavior; the client-side routing still holds)
            log.warning("track permissions for call %s not set: %s", self.call_id, e)

    async def _safe_join(self, p: rtc.RemoteParticipant) -> None:
        try:  # one bad participant must not take the room down, and a failed join must be logged
            await self._join(p)
        except Exception:  # noqa: BLE001
            log.exception("KIN join failed for %s in call %s", p.identity, self.call_id)

    async def _join(self, p: rtc.RemoteParticipant) -> None:
        parsed = participant_from_meta(p.identity, p.metadata)
        if parsed is None or p.identity in self.legs:
            return
        key, person, lang, person_id = parsed
        leg = _Leg(self.room, p.identity, key, person, on_publish=self._restrict_voice)
        # not in self.legs until session.join returns: track_subscribed would start a second ASR during the join
        self._joining[p.identity] = p
        try:
            if person_id is not None:
                side = await self.session.join(key, person, leg.send_json, leg.send_bytes, lang=lang, person_id=person_id)
            else:
                await leg.ensure_track()
                side = await self.session.join(key, person, leg.send_json, leg.send_bytes)
        finally:
            left = self._joining.get(p.identity) is not p  # _leave took it: they hung up while we were joining
            if not left:
                del self._joining[p.identity]
        leg.token = side.token
        if left:  # a zombie side would sit in every later audience and keep the call from ending
            await self._drop(leg)
            return
        self.legs[p.identity] = leg
        if leg.published:  # a publish by another leg during our join replaced the set without this one
            self._restrict_voice()
        for pub in p.track_publications.values():  # mic published before we arrived
            if pub.track is not None:
                self._listen(pub.track, p)

    def _listen(self, track: rtc.Track, p: rtc.RemoteParticipant) -> None:
        leg = self.legs.get(p.identity)
        if leg is None or track.kind != rtc.TrackKind.KIND_AUDIO or (leg.mic_task and not leg.mic_task.done()):
            return
        leg.mic_task = asyncio.create_task(self._pump(leg, track))

    async def _pump(self, leg: _Leg, track: rtc.Track) -> None:
        """Mic frames into the ASR, plus silence whenever the track goes quiet. WebRTC stops sending packets in
        silence (DTX), and Muse Voice Transcribe both needs real-time ingress and only ends a turn after hearing
        silence; without the filler a sentence sat unfinished until the stream timed out (28 s in testing)."""
        stream = rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1)
        loop = asyncio.get_running_loop()
        # clock-based: count samples delivered since the start and top up exactly the deficit. A sleep-then-send
        # filler drifts behind real time (each sleep runs long) and Muse closed the stream after ~50 s of silence.
        clock = {"start": loop.time(), "sent": 0}
        log.info("KIN hears %s (%s)", leg.identity, leg.key)

        async def keep_alive() -> None:
            while True:
                await asyncio.sleep(FRAME_SAMPLES / SAMPLE_RATE)
                owed = int((loop.time() - clock["start"]) * SAMPLE_RATE) - clock["sent"]
                if owed > QUIET_AFTER_S * SAMPLE_RATE:
                    n = min(owed, SAMPLE_RATE)  # at most 1 s at once after a long stall
                    clock["sent"] += n
                    await self.session.on_audio(leg.key, b"\0" * (n * 2))

        filler = asyncio.create_task(keep_alive())
        try:
            async for ev in stream:
                clock["sent"] += ev.frame.samples_per_channel
                await self.session.on_audio(leg.key, bytes(ev.frame.data))
        finally:
            filler.cancel()
            await stream.aclose()

    async def _leave(self, p: rtc.RemoteParticipant) -> None:
        leg = self.legs.pop(p.identity, None)
        if leg is None and self._joining.get(p.identity) is p:
            del self._joining[p.identity]  # still joining: _join drops the leg when session.join returns
        if leg:
            await self._drop(leg)
        if not self.room.remote_participants:
            self.done.set()

    async def _drop(self, leg: _Leg) -> None:
        if leg.mic_task:
            leg.mic_task.cancel()
        if leg.key == leg.identity:  # world leg: mark the participant row left so later joins do not list them
            try:  # before session.leave, which can wait seconds for the last line: a rejoin's reset in that wait stands
                await asyncio.to_thread(self._mark_left, leg.identity)
            except Exception:  # noqa: BLE001
                log.exception("left_at for %s in call %s", leg.identity, self.call_id)
        await self.session.leave(leg.key, token=leg.token)
        try:
            if leg.published:  # a world leg with voice off never published its track
                await self.room.local_participant.unpublish_track(leg.track.sid)
        except Exception as e:  # noqa: BLE001  (track already gone when the room closes)
            log.debug("unpublish %s: %s", leg.identity, e)


    def _mark_left(self, identity: str) -> None:
        with session_scope() as s:
            s.execute(update(m.CallParticipant).where(m.CallParticipant.call_id == self.call_id,
                                                      m.CallParticipant.identity == identity,
                                                      m.CallParticipant.left_at.is_(None)).values(left_at=clock.now()))


class AgentRegistry:
    """One KIN agent per call room, started on the first join, gone when the room empties."""

    def __init__(self) -> None:
        self._agents: dict[int, asyncio.Task] = {}

    def ensure(self, call_id: int) -> None:
        t = self._agents.get(call_id)
        if t is None or t.done():
            self._agents[call_id] = asyncio.create_task(self._run(call_id))

    async def _run(self, call_id: int) -> None:
        try:
            await RoomAgent(call_id).run()
        except Exception as e:  # noqa: BLE001  (a dead agent must not take the API down; the next join restarts it)
            log.warning("KIN agent for call %s stopped: %s", call_id, e)

    def running(self, call_id: int) -> bool:
        t = self._agents.get(call_id)
        return t is not None and not t.done()


agents = AgentRegistry()
