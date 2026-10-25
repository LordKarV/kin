"""RoomAgent lifecycle races and voice-track permissions (rtc/agent.py). Fake room and session; no LiveKit server."""
import asyncio
import json
import threading
from types import SimpleNamespace

from app.rtc import agent as agent_mod
from app.rtc.agent import RoomAgent


class FakeRoom:
    def __init__(self, log):
        self.log, self.handlers, self.perms = log, {}, []
        self.remote_participants = {}

        async def publish_track(track, _opts):
            track._info.sid = f"TR_{track.name}"  # what livekit 1.1.21 does once the publish lands
            log.append(("publish", track.name))

        async def unpublish_track(sid):
            log.append(("unpublish", sid))

        async def publish_data(*_a, **_kw):
            pass

        def set_perms(*, allow_all_participants, participant_permissions):
            self.perms.append((allow_all_participants,
                               {(x.participant_identity, tuple(x.allowed_track_sids)) for x in participant_permissions}))
        self.local_participant = SimpleNamespace(publish_track=publish_track, unpublish_track=unpublish_track,
                                                 publish_data=publish_data, set_track_subscription_permissions=set_perms)

    def on(self, event, cb):
        self.handlers[event] = cb

    def emit(self, event, *args):
        self.handlers[event](*args)

    async def connect(self, *_a, **_kw):
        pass

    async def disconnect(self):
        self.log.append(("disconnect",))


def _part(identity, pid, lang="zh"):
    meta = {"person": f"p_{identity}", "person_id": pid, "lang": lang, "name": identity}
    return SimpleNamespace(identity=identity, track_publications={}, metadata=json.dumps(meta))


def _agent(log, session, monkeypatch):
    ag = RoomAgent(1)
    ag.room, ag.session = FakeRoom(log), session
    monkeypatch.setattr(ag, "_mark_left", lambda identity: log.append(("left", identity)))
    return ag


def test_hangup_during_join_leaves_no_zombie_side(monkeypatch):
    """A disconnect while session.join was still connecting found no leg, so the side stayed in every audience."""
    log = []

    async def run():
        gate = asyncio.Event()

        class Session:
            async def join(self, key, *_a, **_kw):
                await gate.wait()  # Muse connect, up to 20 s
                return SimpleNamespace(token="t")

            async def leave(self, key, token=None):
                log.append(("leave", key, token))
        ag = _agent(log, Session(), monkeypatch)
        p = _part("p5", 5)
        ag.room.remote_participants["p5"] = p
        join = asyncio.create_task(ag._join(p))
        await asyncio.sleep(0)
        del ag.room.remote_participants["p5"]  # the SDK pops the participant before it emits participant_disconnected
        await ag._leave(p)
        gate.set()
        await join
        assert ag.legs == {} and ("leave", "p5", "t") in log and ("left", "p5") in log and ag.done.is_set()

    asyncio.run(run())


def test_call_end_waits_for_a_leave_still_storing_its_last_line(monkeypatch):
    """Two people hang up together; the call must not end (extraction, sweep) while one leave is still in flight."""
    log = []

    async def run():
        gate = asyncio.Event()

        class Session:
            async def join(self, key, *_a, **_kw):
                return SimpleNamespace(token=key)

            async def leave(self, key, token=None):
                if key == "p5":
                    await gate.wait()  # Mei's last line is still in MT
                log.append(("leave", key))
        session = Session()
        monkeypatch.setattr(agent_mod, "registry", SimpleNamespace(get_or_create=lambda _cid: session,
                                                                   drop_if_empty=lambda cid: log.append(("drop", cid))))
        ag = _agent(log, session, monkeypatch)
        room = ag.room
        mei, arjun = _part("p5", 5), _part("p6", 6, "en")
        room.remote_participants.update(p5=mei, p6=arjun)
        task = asyncio.create_task(ag.run())
        while len(ag.legs) < 2:
            assert not task.done(), task  # run() failed before the joins: fail, do not spin
            await asyncio.sleep(0)
        for p in (mei, arjun):
            del room.remote_participants[p.identity]
            room.emit("participant_disconnected", p)
        await asyncio.wait_for(ag.done.wait(), 1)  # Arjun's leave emptied the room
        await asyncio.sleep(0.05)
        assert ("drop", 1) not in log
        gate.set()
        await asyncio.wait_for(task, 1)
        assert log.index(("leave", "p5")) < log.index(("drop", 1))
        assert room.perms[0] == (False, set())  # restricted on connect, before anything is published

    asyncio.run(run())


def test_last_leaver_ends_the_agent(monkeypatch):
    """The last _leave sets done and returns in the same step, so run() woke with that task still in _tasks (its discard
    callback queued). Gathering only done tasks never yields: run() spun at 100% CPU and froze the server."""
    log, errors = [], []

    async def run():
        class Session:
            async def join(self, key, *_a, **_kw):
                return SimpleNamespace(token=key)

            async def leave(self, key, token=None):
                log.append(("leave", key))
        session = Session()
        monkeypatch.setattr(agent_mod, "registry", SimpleNamespace(get_or_create=lambda _cid: session,
                                                                   drop_if_empty=lambda cid: log.append(("drop", cid))))
        ag = _agent(log, session, monkeypatch)
        mei = _part("p5", 5)
        ag.room.remote_participants["p5"] = mei
        task = asyncio.create_task(ag.run())
        while not ag.legs:
            assert not task.done(), task
            await asyncio.sleep(0)
        del ag.room.remote_participants["p5"]
        ag.room.emit("participant_disconnected", mei)
        await task

    def main():
        try:
            asyncio.run(run())
        except BaseException as e:  # noqa: BLE001  (surface it in the main thread)
            errors.append(e)
    th = threading.Thread(target=main, daemon=True)  # a spin blocks wait_for too; a thread lets the test fail, not hang
    th.start()
    th.join(5)
    assert not th.is_alive(), "run() is spinning in its drain loop"
    assert not errors, errors
    assert ("leave", "p5") in log and log[-1] == ("drop", 1)


def test_left_at_is_marked_before_waiting_for_the_last_line(monkeypatch):
    """session.leave can wait seconds for the last line. A rejoin in that wait resets left_at (api/rtc.py), and marking
    after the wait overwrote the reset, so later joins did not list the person who was back."""
    log = []

    async def run():
        gate = asyncio.Event()

        class Session:
            async def join(self, key, *_a, **_kw):
                return SimpleNamespace(token=key)

            async def leave(self, key, token=None):
                await gate.wait()  # the last line is still in MT
                log.append(("leave", key))
        ag = _agent(log, Session(), monkeypatch)
        p = _part("p5", 5)
        await ag._join(p)
        leaving = asyncio.create_task(ag._leave(p))
        await asyncio.sleep(0.05)
        assert ("left", "p5") in log  # marked before the wait, so a rejoin's reset during it stands
        gate.set()
        await leaving
        assert log.index(("left", "p5")) < log.index(("leave", "p5"))

    asyncio.run(run())


def test_voice_tracks_are_subscribable_only_by_their_listener(monkeypatch):
    log = []

    async def run():
        class Session:
            async def join(self, key, *_a, **_kw):
                return SimpleNamespace(token=key)

            async def leave(self, key, token=None):
                pass
        ag = _agent(log, Session(), monkeypatch)
        await ag._join(_part("p5", 5))
        await ag._join(_part("p6", 6, "en"))
        assert ag.room.perms == []  # world legs publish lazily: captions only so far
        await ag.legs["p6"].send_json({"type": "audio_start", "utterance_id": 1})
        assert ag.room.perms[-1] == (False, {("p6", ("TR_kin-to-p6",))})
        await ag.legs["p5"].ensure_track()
        assert ag.room.perms[-1] == (False, {("p6", ("TR_kin-to-p6",)), ("p5", ("TR_kin-to-p5",))})
        legacy = SimpleNamespace(identity="grandparent-3", track_publications={},
                                 metadata=json.dumps({"role": "grandparent", "person": "p_kamala"}))
        await ag._join(legacy)  # publishes before it is registered: its own listener must be allowed at once
        assert ("grandparent-3", ("TR_kin-to-grandparent-3",)) in ag.room.perms[-2][1]
        assert ag.room.perms[-1] == (False, {("p6", ("TR_kin-to-p6",)), ("p5", ("TR_kin-to-p5",)),
                                             ("grandparent-3", ("TR_kin-to-grandparent-3",))})

    asyncio.run(run())


def test_a_failing_join_or_leave_task_is_logged(caplog):
    async def run():
        ag = RoomAgent(1)

        async def boom():
            raise RuntimeError("db gone")
        ag._spawn(boom())
        for _ in range(3):
            await asyncio.sleep(0)
        assert not ag._tasks
    asyncio.run(run())
    assert any("join/leave in call 1 failed" in r.getMessage() and r.exc_info for r in caplog.records)
