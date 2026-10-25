"""World calls through CallSession (docs/ARCHITECTURE.md 8.1-8.3, 9.2, 10): one MT call per target language, per-listener
transcripts, voice opt-in, pause, and the call routes' auth. LiveWorld is a fake with the 8.5 signatures; no network."""
import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import llm as llm_mod
from app.audio import pipeline
from app.audio.asr import ASREvent
from app.audio.glossary_audio import media_dir
from app.audio.pipeline import CallSession
from app.audio.tts import MockTTS
from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.mt.translate import Translator
from app.world import live, privacy
from app.world.live import FinalResult
from app.world.users import create_user, get_space
from tests.graph_fixtures import graph  # noqa: F401

LIN = "林"
TEXT = "我和林去攀岩了"


class LLMLog:
    def __init__(self, new_people=()):
        self.a, self.b, self.new_people = [], [], list(new_people)

    def handler(self, req: httpx.Request):
        body = json.loads(req.content)
        if body["response_format"]["json_schema"]["name"] == "CardsOut":
            self.b.append(body)
            reply = {"pragmatics_cards": [], "new_people": self.new_people}
        else:
            self.a.append(body)
            reply = {"a_translation": "I went climbing with Lin.", "confidence": 0.9, "passthrough_kept": [],
                     "grounded_spans": [{"source": LIN, "rendered": "Lin", "node_id": "p_lin_99"}]}
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    def llm(self):
        return llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(self.handler))


class FakeLiveWorld:
    """8.5 signatures. Arjun can see Lin; nobody else can. Bridges go to Arjun only."""
    instances: list = []

    def __init__(self, call_id, space_id, emit, loop, graph=None, llm=None, bridge_to=None, see_lin=()):
        self.call_id, self.space_id, self.emit, self.loop = call_id, space_id, emit, loop
        self.graph, self.llm, self.bridge_to, self.see_lin = graph, llm, bridge_to, set(see_lin)
        self.calls: list[tuple] = []
        self._tr: dict = {}
        self.final_raises = False
        self.roster_fails_for: set = set()
        FakeLiveWorld.instances.append(self)

    def join(self, identity, person_id, lang): self.calls.append(("join", identity, person_id, lang))
    def leave(self, identity): self.calls.append(("leave", identity))
    def on_partial(self, speaker, text): return {}

    def on_final(self, speaker, text):
        self.calls.append(("final", speaker, text))
        if self.final_raises:
            raise RuntimeError("card engine bug")
        i = text.find(LIN)
        spans = [{"start": i, "end": i + 1, "source": LIN, "node_id": "p_lin_99", "type": "person", "rendered": "Lin",
                  "confidence": 0.95}] if i >= 0 else []
        return FinalResult({}, spans)

    def on_translated(self, speaker, utterance_id, text, translations, audience):
        self.calls.append(("translated", speaker, utterance_id, dict(translations), list(audience)))
        if not self.bridge_to:
            return {}
        return {self.bridge_to: [{"type": "glance", "speaker": speaker, "role": "participant", "partial": False,
                                  "items": [{"key": "bridge:1", "kind": "bridge", "title": "You haven't told Mei",
                                             "body": "you started bouldering", "target": "p_mei", "private": True}]}]}

    def asks(self, speaker, listeners, new_people):
        self.calls.append(("asks", speaker, list(listeners), [p.name for p in new_people]))
        return {L: [{"type": "glance", "speaker": speaker, "items": [{"key": "ask:lin", "kind": "ask", "term": "Lin"}]}]
                for L in listeners}

    def feedback(self, listener, key, action): self.calls.append(("feedback", listener, key, action))
    def render(self, listener, node_id): return "Mei's friend Lin" if listener in self.see_lin else None
    def roster(self, listeners, speaker):
        if self.roster_fails_for & set(listeners):
            raise RuntimeError("roster failed")
        return "ROSTER " + ",".join(listeners)

    def translator(self, lang):
        self.calls.append(("translator", lang))
        if lang not in self._tr:
            self._tr[lang] = Translator(self.graph, self.llm, lang=lang)
        return self._tr[lang]

    def keyterms(self, speaker): return []
    def refresh(self): pass
    def close(self): self.calls.append(("close",))


class Leg:
    def __init__(self):
        self.log: list = []

    async def send_json(self, msg):
        self.log.append(msg)

    async def send_bytes(self, b):
        self.log.append(("bytes", len(b)))

    def of(self, typ):
        return [x for x in self.log if isinstance(x, dict) and x.get("type") == typ]

    def nbytes(self):
        return sum(x[1] for x in self.log if isinstance(x, tuple))


def _people(langs: dict[str, str]):
    """Users in the world space plus a world call that all of them joined."""
    out = {}
    with session_scope() as s:
        for name, lang in langs.items():
            user, person, token = create_user(s, name, lang)
            out[name] = {"pid": person.id, "slug": person.slug, "lang": lang, "token": token, "id": f"p{person.id}"}
        space = get_space(s)
        call = m.Call(family_id=space.id, transport="livekit", mode="world")
        s.add(call); s.flush()
        for p in out.values():
            s.add(m.CallParticipant(call_id=call.id, person_id=p["pid"], identity=p["id"], lang=p["lang"],
                                    joined_at=datetime.now(timezone.utc)))
        return call.id, space.id, out


async def _settle(cs):
    while cs.bg_tasks:
        await asyncio.gather(*list(cs.bg_tasks))


async def _group(graph, llm_log, voice=("Arjun", "Priya", "Wei"), bridge=True):
    cid, sid, ppl = _people({"Mei": "zh", "Arjun": "en", "Priya": "en", "Wei": "zh"})
    cs = CallSession(call_id=cid, family_id=sid, translator=Translator(graph, llm_log.llm()), tts=MockTTS())
    cs.world = FakeLiveWorld(cid, sid, cs._send_to, asyncio.get_running_loop(), graph=graph, llm=llm_log.llm(),
                             bridge_to=ppl["Arjun"]["id"] if bridge else None, see_lin=[ppl["Arjun"]["id"]])
    legs = {}
    for name, p in ppl.items():
        legs[name] = Leg()
        side = await cs.join(p["id"], p["slug"], legs[name].send_json, legs[name].send_bytes, start_asr=False,
                             lang=p["lang"], person_id=p["pid"])
        side.voice_on = name in voice
    watcher = Leg()
    cs.add_watcher(watcher.send_json)
    return cs, ppl, legs, watcher


def _utterance_count(cid):
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(m.Utterance).where(m.Utterance.call_id == cid))


def test_one_mt_call_per_language_and_per_listener_transcripts(graph):
    async def run():
        log = LLMLog()
        cs, ppl, legs, watcher = await _group(graph, log)
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await _settle(cs)
        assert len(log.a) == 1, "one A call for en, none for zh"
        assert "Target language" not in log.a[0]["messages"][-1]["content"]  # en target
        assert len(log.b) == 1
        assert [c for c in cs.world.calls if c[0] == "translator"] == [("translator", "zh")]  # the speaker's language

        for name in ("Arjun", "Priya", "Wei", "Mei"):
            trs = legs[name].of("transcript")
            assert len(trs) == 1, name
            assert trs[0]["target_lang"] == ppl[name]["lang"]
        arjun, priya, wei, mei = (legs[n].of("transcript")[0] for n in ("Arjun", "Priya", "Wei", "Mei"))
        assert arjun["listener"] == ppl["Arjun"]["slug"] and priya["listener"] == ppl["Priya"]["slug"]
        assert arjun["translation"] == priya["translation"] == "I went climbing with Lin."
        assert wei["translation"] is None and mei["translation"] is None and mei["listener"] is None
        # Arjun can see Lin; Priya cannot: surface text, node id null
        assert arjun["grounded_spans"] == [{"source": LIN, "rendered": "Mei's friend Lin", "node_id": "p_lin_99"}]
        assert priya["grounded_spans"] == [{"source": LIN, "rendered": LIN, "node_id": None}]
        assert wei["grounded_spans"] == [{"source": LIN, "rendered": LIN, "node_id": None}]
        assert all(s["node_id"] is None for s in priya["linker_spans"])

        # the bridge reaches only Arjun's leg, never a watcher
        assert [g["items"][0]["key"] for g in legs["Arjun"].of("glance")] == ["bridge:1"]
        assert not any(legs[n].of("glance") for n in ("Priya", "Wei", "Mei"))
        assert watcher.log == []

        with session_scope() as s:
            [u] = s.scalars(select(m.Utterance).where(m.Utterance.call_id == cs.call_id)).all()
            assert u.lang == "zh" and u.speaker_id == ppl["Mei"]["pid"]
            assert sorted(u.audience) == sorted(ppl[n]["pid"] for n in ("Arjun", "Priya", "Wei"))
            assert u.translations == {"en": "I went climbing with Lin."} and u.translation == "I went climbing with Lin."
            assert {"scan_ms", "mt_ms_en", "cards_ms", "total_ms", "b_ms", "tts_first_byte_ms"} <= set(u.latencies)
        assert ("translated", ppl["Mei"]["id"], u.id, {"en": "I went climbing with Lin."}, u.audience) in cs.world.calls
    asyncio.run(run())


def test_tts_only_to_voiced_other_language_legs_in_order(graph):
    async def run():
        cs, ppl, legs, _ = await _group(graph, LLMLog(), bridge=False)
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await cs.on_text(ppl["Mei"]["id"], "林也去了")
        await _settle(cs)
        assert legs["Arjun"].nbytes() > 0 and legs["Priya"].nbytes() > 0
        assert legs["Wei"].nbytes() == 0 and legs["Mei"].nbytes() == 0  # same language / speaker: captions only
        assert not legs["Wei"].of("audio_start")
        uids = [t["utterance_id"] for t in legs["Arjun"].of("transcript")]
        for name in ("Arjun", "Priya"):
            seq = []
            for x in legs[name].log:
                if isinstance(x, tuple):
                    seq.append("b")
                elif x["type"] in ("audio_start", "audio_end"):
                    seq.append((x["type"], x["utterance_id"]))
            first_end = seq.index(("audio_end", uids[0]))
            assert seq[0] == ("audio_start", uids[0]) and seq[first_end + 1] == ("audio_start", uids[1]), seq
            assert seq[-1] == ("audio_end", uids[1]) and "b" in seq[1:first_end]
            assert legs[name].of("audio_start")[0]["lang"] == "en"
    asyncio.run(run())


def test_voice_off_by_default_means_captions_only(graph):
    async def run():
        cs, ppl, legs, _ = await _group(graph, LLMLog(), voice=("Priya",), bridge=False)
        assert pipeline.Side("participant", "x", "en", legs["Mei"].send_json, legs["Mei"].send_bytes).voice_on is False
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await _settle(cs)
        assert legs["Arjun"].of("transcript") and legs["Arjun"].nbytes() == 0
        assert not legs["Arjun"].of("audio_start") and not legs["Arjun"].of("audio_end")
        assert legs["Priya"].nbytes() > 0 and legs["Priya"].of("audio_start")
    asyncio.run(run())


def test_new_people_from_b_become_asks_for_that_language_group_only(graph):
    async def run():
        log = LLMLog(new_people=[{"source": LIN, "name": "Lin", "owner": "speaker", "owner_name": "Mei", "relation": "friend",
                                  "context": "climbing"}])
        cs, ppl, legs, _ = await _group(graph, log, bridge=False)
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await _settle(cs)
        [asks] = [c for c in cs.world.calls if c[0] == "asks"]
        assert sorted(asks[2]) == sorted([ppl["Arjun"]["id"], ppl["Priya"]["id"]]) and asks[3] == ["Lin"]
        assert legs["Arjun"].of("glance") and legs["Priya"].of("glance") and legs["Arjun"].of("enrich")
        assert not legs["Wei"].of("glance") and not legs["Wei"].of("enrich")
    asyncio.run(run())


def test_pause_drops_typed_text_and_audio_and_writes_nothing(graph):
    async def run():
        log = LLMLog()
        cs, ppl, legs, _ = await _group(graph, log)
        kin = await cs.set_paused(ppl["Priya"]["pid"], True)
        assert kin == {"on": False, "paused_by": {"person": ppl["Priya"]["slug"], "name": "Priya"}}
        for leg in legs.values():
            assert leg.of("kin_status")[-1] == {"type": "kin_status", **kin}

        class Spy:
            frames = 0
            async def send_audio(self, b): Spy.frames += 1
            async def finish(self): pass
        cs.sides[ppl["Mei"]["id"]].asr = Spy()
        with session_scope() as s:
            before = (s.scalar(select(func.count()).select_from(m.Fact)), s.scalar(select(func.count()).select_from(m.Knowledge)))
        media = sorted(p for p in media_dir().rglob("*") if p.is_file())
        await cs.on_audio(ppl["Mei"]["id"], b"\0\0" * 160)
        await cs._world_event(cs.sides[ppl["Mei"]["id"]], ASREvent(text=TEXT, final=False))
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await cs._world_event(cs.sides[ppl["Mei"]["id"]], ASREvent(text=TEXT, final=True))
        await _settle(cs)
        assert Spy.frames == 0 and log.a == [] and _utterance_count(cs.call_id) == 0
        assert not any(c[0] in ("final", "translated") for c in cs.world.calls)
        with session_scope() as s:
            assert before == (s.scalar(select(func.count()).select_from(m.Fact)), s.scalar(select(func.count()).select_from(m.Knowledge)))
        assert media == sorted(p for p in media_dir().rglob("*") if p.is_file())
        assert not any(leg.of("transcript") or leg.of("partial") for leg in legs.values())

        assert (await cs.set_paused(ppl["Priya"]["pid"], False)) == {"on": True, "paused_by": None}
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await _settle(cs)
        assert _utterance_count(cs.call_id) == 1
    asyncio.run(run())


def test_world_join_sends_participants_and_kin_status(graph):
    async def run():
        cs, ppl, legs, watcher = await _group(graph, LLMLog())
        joined = legs["Wei"].of("joined")[0]
        assert joined["identity"] == ppl["Wei"]["id"] and joined["kin"] == {"on": True, "paused_by": None}
        assert {p["identity"] for p in joined["participants"]} == {ppl[n]["id"] for n in ("Mei", "Arjun", "Priya")}
        assert legs["Wei"].of("kin_status") == [{"type": "kin_status", "on": True, "paused_by": None}]
        last = legs["Mei"].of("participants")[-1]["participants"]
        assert {p["name"] for p in last} == {"Arjun", "Priya", "Wei"}
        assert [c for c in cs.world.calls if c[0] == "join"][0] == ("join", ppl["Mei"]["id"], ppl["Mei"]["pid"], "zh")
        await cs.leave(ppl["Wei"]["id"])
        assert ("leave", ppl["Wei"]["id"]) in cs.world.calls
        assert {p["name"] for p in legs["Mei"].of("participants")[-1]["participants"]} == {"Arjun", "Priya"}
        assert watcher.log == []
    asyncio.run(run())


@pytest.fixture
def fake_world(monkeypatch):
    FakeLiveWorld.instances = []
    monkeypatch.setattr(live, "LiveWorld", FakeLiveWorld)
    sweeps = []
    monkeypatch.setattr(privacy, "run_sweep", lambda: sweeps.append(1) or {})
    yield sweeps
    pipeline.registry._calls.clear()


def test_registry_world_session_and_call_end_sweep(graph, fake_world):
    cid, sid, ppl = _people({"Mei": "zh", "Arjun": "en"})
    cs = pipeline.registry.get_or_create(cid)
    assert isinstance(cs.world, FakeLiveWorld) and cs.fade is None and cs.on_utterance is None
    assert cs.world.space_id == sid and cs.world.emit == cs._send_to
    pipeline.registry.drop_if_empty(cid)
    assert pipeline.registry.get(cid) is None and ("close",) in cs.world.calls and fake_world == [1]
    with session_scope() as s:
        legacy = m.Call(family_id=graph.family_id); s.add(legacy); s.flush(); lid = legacy.id
    assert pipeline.registry.get_or_create(lid).world is None


def test_end_call_route_runs_the_sweep(monkeypatch, fake_world):
    async def no_startup_sweep() -> None:  # the lifespan sweep runs in a thread; keep this test about the end route
        return None
    monkeypatch.setattr("app.api.calls.sweep_loop", no_startup_sweep)
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"family_id": 1}).json()["id"]
        assert c.post(f"/api/calls/{cid}/end").status_code == 200
    assert fake_world == [1]


def test_call_routes_auth_pause_text_feedback_voice(monkeypatch, fake_world):
    log = LLMLog()
    monkeypatch.setattr(llm_mod, "_default", log.llm())
    with TestClient(app) as c:
        cid, _sid, ppl = _people({"Mei": "zh", "Arjun": "en"})
        with session_scope() as s:
            _u, _p, stranger = create_user(s, "Stranger", "en")
        cs = pipeline.registry.get_or_create(cid)
        from app.graph.kinship import FamilyGraph
        with session_scope() as s:
            cs.world.graph = FamilyGraph.from_session(s, 1)
        cs.world.llm = log.llm()
        legs = {n: Leg() for n in ppl}

        async def join(name):
            p = ppl[name]
            await cs.join(p["id"], p["slug"], legs[name].send_json, legs[name].send_bytes, start_asr=False,
                          lang=p["lang"], person_id=p["pid"])
        H = lambda name: {"X-KIN-User": ppl[name]["token"]}  # noqa: E731

        assert c.post(f"/api/calls/{cid}/pause", json={"paused": True}).status_code == 401
        assert c.post(f"/api/calls/{cid}/pause", json={"paused": True}, headers={"X-KIN-User": "nope"}).status_code == 401
        for path, body in (("pause", {"paused": True}), ("feedback", {"key": "who:x", "action": "know"}),
                           ("text", {"text": "hi"}), ("voice", {"on": True})):
            assert c.post(f"/api/calls/{cid}/{path}", json=body, headers={"X-KIN-User": stranger}).status_code == 403
        assert c.get(f"/api/calls/{cid}/participants", headers={"X-KIN-User": stranger}).status_code == 403
        for path, body in (("voice", {"on": True}), ("pause", {"paused": True}), ("feedback", {"key": "k", "action": "know"})):
            assert c.post(f"/api/calls/{cid}/{path}", json=body, headers=H("Arjun")).status_code == 409, path  # not joined

        c.portal.call(join, "Mei")
        c.portal.call(join, "Arjun")
        r = c.post(f"/api/calls/{cid}/voice", json={"on": True}, headers=H("Arjun"))
        assert r.json() == {"on": True} and cs.sides[ppl["Arjun"]["id"]].voice_on is True
        r = c.post(f"/api/calls/{cid}/pause", json={"paused": True}, headers=H("Arjun"))
        assert r.status_code == 200 and r.json() == {"on": False, "paused_by": {"person": ppl["Arjun"]["slug"], "name": "Arjun"}}
        assert c.post(f"/api/calls/{cid}/text", json={"text": TEXT}, headers=H("Mei")).json() == {"ok": True}
        assert _utterance_count(cid) == 0 and log.a == []
        assert c.post(f"/api/calls/{cid}/pause", json={"paused": False}, headers=H("Mei")).json() == {"on": True, "paused_by": None}
        assert c.post(f"/api/calls/{cid}/text", json={"text": TEXT}, headers=H("Mei")).json() == {"ok": True}
        assert _utterance_count(cid) == 1 and legs["Arjun"].of("transcript")
        assert c.post(f"/api/calls/{cid}/feedback", json={"key": "who:p_lin_99", "action": "dismiss"}, headers=H("Arjun")).json() == {"ok": True}
        assert ("feedback", ppl["Arjun"]["id"], "who:p_lin_99", "dismiss") in cs.world.calls
        assert c.post(f"/api/calls/{cid}/feedback", json={"key": "k", "action": "bogus"}, headers=H("Arjun")).status_code == 422
        rows = c.get(f"/api/calls/{cid}/participants", headers=H("Mei")).json()
        assert [(r["person"], r["identity"], r["lang"]) for r in rows] == [(ppl[n]["slug"], ppl[n]["id"], ppl[n]["lang"]) for n in ("Mei", "Arjun")]
        assert rows[0]["joined_at"] and rows[0]["left_at"] is None


def test_world_call_rejects_unverified_joiners(graph):
    async def run():
        cs, ppl, legs, _ = await _group(graph, LLMLog())
        spy = Leg()
        for identity, pid in (("grandchild", None), (ppl["Arjun"]["id"], None), (ppl["Arjun"]["id"], ppl["Mei"]["pid"])):
            with pytest.raises(PermissionError):
                await cs.join(identity, "x", spy.send_json, spy.send_bytes, start_asr=False, lang="en", person_id=pid)
        assert spy.log == [] and cs.sides[ppl["Arjun"]["id"]].send_json == legs["Arjun"].send_json
    asyncio.run(run())


def test_on_final_failure_still_captions(graph):
    async def run():
        cs, ppl, legs, _ = await _group(graph, LLMLog(), bridge=False)
        cs.world.final_raises = True
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await _settle(cs)
        assert legs["Arjun"].of("transcript")[0]["translation"] == "I went climbing with Lin."
        assert _utterance_count(cs.call_id) == 1
    asyncio.run(run())


def test_failed_translation_group_is_flagged_and_first_good_one_is_stored(graph):
    async def run():
        cid, sid, ppl = _people({"Mei": "zh", "Ana": "ta", "Arjun": "en"})
        log = LLMLog()
        cs = CallSession(call_id=cid, family_id=sid, translator=Translator(graph, log.llm()), tts=MockTTS())
        cs.world = FakeLiveWorld(cid, sid, cs._send_to, asyncio.get_running_loop(), graph=graph, llm=log.llm())
        cs.world.roster_fails_for = {ppl["Ana"]["id"]}
        legs = {n: Leg() for n in ppl}
        for n, p in ppl.items():
            await cs.join(p["id"], p["slug"], legs[n].send_json, legs[n].send_bytes, start_asr=False, lang=p["lang"], person_id=p["pid"])
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await _settle(cs)
        ana = legs["Ana"].of("transcript")[0]
        assert ana["translation"] is None and ana["error"] == "mt"
        assert legs["Arjun"].of("transcript")[0]["error"] is None
        assert legs["Mei"].of("transcript")[0]["error"] is None  # the speaker's own line is not a failure
        with session_scope() as s:
            [u] = s.scalars(select(m.Utterance).where(m.Utterance.call_id == cid)).all()
            assert u.translation == "I went climbing with Lin." and u.translations == {"en": "I went climbing with Lin."}
    asyncio.run(run())


def test_pause_during_mt_stores_nothing(graph):
    async def run():
        box = {}

        class PausingLLM(LLMLog):
            def handler(self, req):
                box["cs"].paused = True  # someone hits pause while A is in flight
                return super().handler(req)
        log = PausingLLM()
        cs, ppl, legs, _ = await _group(graph, log, bridge=False)
        box["cs"] = cs
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await _settle(cs)
        assert log.a and _utterance_count(cs.call_id) == 0
        assert not any(c[0] == "translated" for c in cs.world.calls)
        assert not any(leg.of("transcript") or leg.nbytes() for leg in legs.values())
    asyncio.run(run())


def test_reconnect_keeps_voice_and_one_dead_leg_does_not_cut_others(graph):
    async def run():
        cs, ppl, legs, _ = await _group(graph, LLMLog(), bridge=False)
        p, fresh = ppl["Arjun"], Leg()
        await cs.join(p["id"], p["slug"], fresh.send_json, fresh.send_bytes, start_asr=False, lang="en", person_id=p["pid"])
        assert cs.sides[p["id"]].voice_on is True

        async def dead(_b):
            raise ConnectionError("leg dropped")
        cs.sides[p["id"]].send_bytes = dead
        await cs.on_text(ppl["Mei"]["id"], TEXT)
        await _settle(cs)
        assert legs["Priya"].nbytes() > 0 and fresh.of("audio_end")
    asyncio.run(run())
