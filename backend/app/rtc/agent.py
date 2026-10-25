"""KIN as a server-side participant in a LiveKit room (the KIN call app).

Each person joins from the app with their own audio track, so there is no "who spoke?" guesswork (unlike a merged
phone call). The agent subscribes to every person's microphone at 16 kHz and feeds it to the normal CallSession
(linker, glance cards, Fade, translation, memory). What KIN produces goes only to the person it is for:
  - JSON (partials, glance cards, transcripts, enrich cards, asks) as data messages addressed to that participant;
  - the translated voice on a per-listener track named `kin-to-<identity>`, which only that listener plays.
Participants say who they are in their token metadata: {"role": "grandparent"|"grandchild", "person": "<slug>"}.
Verified against livekit==1.1.21 (rtc) signatures on 2026-10-24.
"""
from __future__ import annotations

import asyncio
import json
import logging

from livekit import api, rtc

from ..audio.pipeline import CallSession, registry
from ..config import get_settings

log = logging.getLogger("kin.rtc")
SAMPLE_RATE = 16000
FRAME_SAMPLES = 320  # 20 ms frames into the AudioSource
QUIET_AFTER_S = 0.06  # no mic frame for this long: feed silence to the ASR (WebRTC DTX)
AGENT_IDENTITY = "kin"
DATA_TOPIC = "kin"
DEV_URL, DEV_KEY, DEV_SECRET = "ws://localhost:7880", "devkey", "secret"  # `livekit-server --dev` (local only)


def livekit_creds() -> tuple[str, str, str]:
    s = get_settings()
    return (s.livekit_url or DEV_URL, s.livekit_api_key or DEV_KEY, s.livekit_api_secret or DEV_SECRET)


def room_name(call_id: int) -> str:
    return f"kin-call-{call_id}"


def mint_token(room: str, identity: str, name: str, metadata: dict | None = None, agent: bool = False) -> str:
    _, key, secret = livekit_creds()
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True, can_publish_data=True, agent=agent or None)
    tok = api.AccessToken(key, secret).with_identity(identity).with_name(name).with_grants(grants)
    if metadata:
        tok = tok.with_metadata(json.dumps(metadata))
    return tok.to_jwt()


class _Leg:
    """One person in the room as a CallSession side: their data channel and their private translated-voice track."""

    def __init__(self, room: rtc.Room, identity: str, role: str, person: str):
        self.room, self.identity, self.role, self.person = room, identity, role, person
        self.source = rtc.AudioSource(SAMPLE_RATE, 1)
        self.track = rtc.LocalAudioTrack.create_audio_track(f"kin-to-{identity}", self.source)
        self.token: str | None = None
        self.mic_task: asyncio.Task | None = None
        self._pending = b""

    async def send_json(self, msg: dict) -> None:
        await self.room.local_participant.publish_data(json.dumps(msg, ensure_ascii=False), reliable=True,
                                                       destination_identities=[self.identity], topic=DATA_TOPIC)

    async def send_bytes(self, pcm16: bytes) -> None:
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

    async def run(self) -> None:
        url, _, _ = livekit_creds()
        self.session = registry.get_or_create(self.call_id)
        self.room.on("participant_connected", lambda p: asyncio.create_task(self._join(p)))
        self.room.on("participant_disconnected", lambda p: asyncio.create_task(self._leave(p)))
        self.room.on("track_subscribed", lambda track, _pub, p: self._listen(track, p))
        await self.room.connect(url, mint_token(room_name(self.call_id), AGENT_IDENTITY, "KIN", agent=True))
        log.info("KIN agent in %s", room_name(self.call_id))
        for p in list(self.room.remote_participants.values()):
            await self._join(p)
        try:
            await self.done.wait()
        finally:
            await self.room.disconnect()
            registry.drop_if_empty(self.call_id)
            log.info("KIN agent left %s", room_name(self.call_id))

    async def _join(self, p: rtc.RemoteParticipant) -> None:
        try:
            meta = json.loads(p.metadata or "{}")
        except json.JSONDecodeError:
            meta = {}
        role, person = meta.get("role"), meta.get("person")
        if role not in ("grandparent", "grandchild") or not person or p.identity in self.legs:
            return
        leg = _Leg(self.room, p.identity, role, person)
        await self.room.local_participant.publish_track(leg.track, rtc.TrackPublishOptions())
        side = await self.session.join(role, person, leg.send_json, leg.send_bytes)
        leg.token = side.token
        self.legs[p.identity] = leg
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
        log.info("KIN hears %s (%s)", leg.identity, leg.role)

        async def keep_alive() -> None:
            while True:
                await asyncio.sleep(FRAME_SAMPLES / SAMPLE_RATE)
                owed = int((loop.time() - clock["start"]) * SAMPLE_RATE) - clock["sent"]
                if owed > QUIET_AFTER_S * SAMPLE_RATE:
                    n = min(owed, SAMPLE_RATE)  # at most 1 s at once after a long stall
                    clock["sent"] += n
                    await self.session.on_audio(leg.role, b"\0" * (n * 2))

        filler = asyncio.create_task(keep_alive())
        try:
            async for ev in stream:
                clock["sent"] += ev.frame.samples_per_channel
                await self.session.on_audio(leg.role, bytes(ev.frame.data))
        finally:
            filler.cancel()
            await stream.aclose()

    async def _leave(self, p: rtc.RemoteParticipant) -> None:
        leg = self.legs.pop(p.identity, None)
        if leg:
            if leg.mic_task:
                leg.mic_task.cancel()
            await self.session.leave(leg.role, token=leg.token)
            try:
                await self.room.local_participant.unpublish_track(leg.track.sid)
            except Exception as e:  # noqa: BLE001  (track already gone when the room closes)
                log.debug("unpublish %s: %s", leg.identity, e)
        if not self.room.remote_participants:
            self.done.set()


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
