"""World REST (docs/ARCHITECTURE.md 9.2): sign-up, X-KIN-User auth, visibility of /api/world, place, dev routes, delete."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import llm as llm_mod
from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.world import clock

FORMS = {"Lin": [{"lang": "zh", "form": "林"}, {"lang": "en", "form": "Lynn"}]}


def _reply(content: dict) -> httpx.Response:
    return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                     "choices": [{"index": 0, "finish_reason": "stop",
                                                  "message": {"role": "assistant", "content": json.dumps(content)}}],
                                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


TOLD = {"told Priya's mom": ["Priya's mom"], "told Priya": ["Priya"], "told 林": ["林"]}  # first match wins


def sms_reply(user_text: str) -> dict:
    body = user_text.split("MESSAGE:\n", 1)[1]
    told = next((v for k, v in TOLD.items() if k in body), [])
    if "explode" in body:
        raise RuntimeError("parse fails")
    if "news" in body:  # one fact about someone else, one bad predicate, one real one that opens with "will"
        facts = [{"predicate": p, "text_en": x, "keys": [], "sensitive_kind": "", "storyline": None, "told": []}
                 for p, x in (("did", "Priya got the internship"), ("feels", "felt great"), ("plans", "will start a new job"))]
        return {"facts": facts, "ack": "Noted."}
    if "bouldering" in body:
        facts = [{"predicate": "started", "text_en": "started bouldering", "keys": [["bouldering", "climbing", "攀岩"]],
                  "sensitive_kind": "", "storyline": None, "told": told}]
        return {"facts": facts, "ack": "Nice: you started bouldering & <loving> it."}
    return {"facts": [], "ack": "Got it, thanks."}


@pytest.fixture
def mock_llm(monkeypatch):
    calls = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        name = body["response_format"]["json_schema"]["name"]
        user = body["messages"][-1]["content"]
        calls.append(name)
        if name == "FormsOut":
            n = user.split("NAME: ", 1)[1].split("\n", 1)[0]
            return _reply({"forms": FORMS.get(n, [])})
        if name == "SmsOut":
            try:
                return _reply(sms_reply(user))
            except RuntimeError as e:
                return httpx.Response(500, json={"error": str(e)})
        return httpx.Response(500, json={"error": f"unexpected schema {name}"})

    fake = llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))
    fake.calls = calls
    monkeypatch.setattr(llm_mod, "_default", fake)
    yield fake
    monkeypatch.setattr(llm_mod, "_default", None)


@pytest.fixture(autouse=True)
def _reset_clock():
    clock.set_offset_days(0)
    yield
    clock.set_offset_days(0)


def sign_up(c, name, lang="en", phone=None):
    r = c.post("/api/users", json={"name": name, "lang": lang, "phone": phone})
    assert r.status_code == 200, r.text
    j = r.json()
    return {"token": j["token"], "slug": j["person"], "id": j["person_id"], "h": {"X-KIN-User": j["token"]}}


def befriend(c, me, other):
    r = c.post("/api/world/place", headers=me["h"], json={"person": other["slug"], "owner": me["slug"], "relation": "friend"})
    assert r.status_code == 200, r.text
    return r.json()


def plant_lin(c, mei, audience):
    """Mei tells `audience` about her climbing friend Lin (the dev path the demo uses)."""
    update = {"entities": [{"ref": "e1", "name": "Lin", "native": "林", "forms": ["Lin", "林"], "kind": "person",
                            "existing_id": None}],
              "ties": [{"a": "speaker", "b": "e1", "kind": "friend", "context": "from the Fudan climbing wall"}],
              "facts": [{"subject": "e1", "predicate": "studies_at", "text_en": "studies at Fudan", "text_src": "",
                         "keys": [], "refs": [], "lines": [0], "sensitive_kind": "", "same_as": None,
                         "contradicts": None, "storyline": None}]}
    r = c.post("/api/dev/apply", json={"speaker": mei["slug"], "audience": [a["slug"] for a in audience], "update": update})
    assert r.status_code == 200, r.text
    return r.json()


def test_sign_up_returns_token_once_and_me_works(mock_llm):
    with TestClient(app) as c:
        u = sign_up(c, "Arjun", phone="5125550101")
        me = c.get("/api/me", headers=u["h"]).json()
        assert me["name"] == "Arjun" and me["phone"] == "+15125550101" and me["person"] == u["slug"]
        assert "token" not in me
        assert c.patch("/api/me", headers=u["h"], json={"lang": "ta"}).json()["lang"] == "ta"
        assert c.patch("/api/me", headers=u["h"], json={"lang": "xx"}).status_code == 422
        assert sign_up(c, "Lin")["slug"]
    assert "FormsOut" in mock_llm.calls
    with session_scope() as s:
        lin = s.scalars(select(m.Person).where(m.Person.display_name == "Lin")).one()
        assert {(a.alias, a.kind) for a in lin.aliases} == {("林", "translit"), ("Lynn", "translit")}


def test_missing_or_bad_token_is_401(mock_llm):
    with TestClient(app) as c:
        for path in ("/api/me", "/api/world", "/api/me/facts", "/api/contacts"):
            assert c.get(path).status_code == 401
            assert c.get(path, headers={"X-KIN-User": "nope"}).status_code == 401


def test_patch_someone_elses_fact_is_403(mock_llm):
    with TestClient(app) as c:
        mei, arjun, priya = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun"), sign_up(c, "Priya")
        fid = plant_lin(c, mei, [arjun])["facts"][0]
        assert c.patch(f"/api/me/facts/{fid}", headers=priya["h"], json={"pinned": True}).status_code == 403
        assert c.patch(f"/api/me/facts/{fid}", headers=arjun["h"], json={"text": "x"}).status_code == 403
        assert c.delete(f"/api/me/facts/{fid}", headers=arjun["h"]).status_code == 403
        assert c.patch(f"/api/me/facts/{fid}", headers=arjun["h"], json={"pinned": True}).json()["pinned"] is True
        assert c.patch(f"/api/me/facts/{fid}", headers=mei["h"], json={"text": "studies at Fudan U"}).json()["text"] == "studies at Fudan U"
        assert c.delete(f"/api/me/facts/{fid}", headers=mei["h"]).json() == {"deleted": True}
        assert c.patch(f"/api/me/facts/{fid}", headers=mei["h"], json={"pinned": True}).status_code == 404


def test_world_never_shows_what_the_viewer_did_not_hear(mock_llm):
    with TestClient(app) as c:
        mei, arjun, priya = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun"), sign_up(c, "Priya")
        befriend(c, arjun, mei)
        befriend(c, arjun, priya)
        plant_lin(c, mei, [arjun])
        heard = c.get("/api/world", headers=arjun["h"]).json()
        lin = next(p for p in heard["people"] if p["name"] == "Lin")
        assert "Mei's friend Lin" in lin["render"]
        assert any(t["dst"] == lin["person"] and t["context"] == "from the Fudan climbing wall" for t in heard["ties"])
        not_heard = c.get("/api/world", headers=priya["h"]).json()
        assert "Lin" not in json.dumps(not_heard) and "Fudan" not in json.dumps(not_heard)
        facts = c.get("/api/me/facts", headers=priya["h"]).json()
        assert "Fudan" not in json.dumps(facts)


def test_place_social_tie_shows_in_world_and_contacts(mock_llm):
    with TestClient(app) as c:
        arjun, mei = sign_up(c, "Arjun"), sign_up(c, "Mei", "zh")
        r = c.post("/api/world/place", headers=arjun["h"],
                   json={"name": "Jess", "owner": mei["slug"], "relation": "roommate", "context": "in Shanghai"})
        assert r.status_code == 404  # Mei is not in Arjun's world yet
        befriend(c, arjun, mei)
        r = c.post("/api/world/place", headers=arjun["h"],
                   json={"name": "Jess", "owner": mei["slug"], "relation": "roommate", "context": "in Shanghai"})
        assert r.status_code == 200 and r.json()["render"] == "Mei's roommate Jess (in Shanghai)"
        world = c.get("/api/world", headers=arjun["h"]).json()
        assert {"src": mei["slug"], "dst": r.json()["person"], "kind": "roommate", "context": "in Shanghai"} in world["ties"]
        assert next(p for p in world["people"] if p["person"] == mei["slug"])["circle"] == "friends"
        contacts = c.get("/api/contacts", headers=arjun["h"]).json()
        assert [x["person"] for x in contacts] == [mei["slug"]] and contacts[0]["circle"] == "friends"
        rel = c.get("/api/world/relations?lang=zh", headers=arjun["h"]).json()
        assert {"kind": "roommate", "label": "roommate"} in rel["social"] and rel["kin"]
        bad = c.post("/api/world/place", headers=arjun["h"], json={"name": "X", "owner": mei["slug"], "relation": "nemesis"})
        assert bad.status_code == 422


def test_dev_clock_shifts_world_now(mock_llm, monkeypatch):
    with TestClient(app) as c:
        before = clock.now()
        r = c.post("/api/dev/clock", json={"offset_days": 42})
        assert r.status_code == 200
        assert (clock.now() - before).days in (41, 42)
        assert c.post("/api/dev/clock", json={"offset_days": 1e9}).status_code == 422
    monkeypatch.setenv("DEV_ENDPOINTS", "0")
    from app.config import get_settings
    get_settings.cache_clear()
    with TestClient(app) as c:
        assert c.post("/api/dev/clock", json={"offset_days": 0}).status_code == 404


def test_dev_routes_are_loopback_only_when_locked(mock_llm, monkeypatch):
    """A real KIN key travels in every invite link, so on a locked server the key alone must not reach /api/dev/*."""
    monkeypatch.setenv("KIN_API_KEY", "real-key")
    from app.config import get_settings
    get_settings.cache_clear()
    key = {"X-KIN-Key": "real-key"}
    sms = {"from": "+15550000001", "body": "x"}
    with TestClient(app, headers=key) as c:  # client host "testclient": not loopback
        for path, body in (("/api/dev/clock", {"offset_days": 1}), ("/api/dev/sms", sms),
                           ("/api/dev/apply", {"speaker": "p_x", "audience": [], "update": {}})):
            r = c.post(path, json=body)
            assert (r.status_code, r.json()["detail"]) == (404, "Not Found"), path
        assert clock.offset_days() == 0
    with TestClient(app, headers=key, client=("127.0.0.1", 50000)) as c:
        assert c.post("/api/dev/clock", json={"offset_days": 1}).status_code == 200
        assert c.post("/api/dev/sms", json=sms).status_code == 200
        mei, arjun = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun")
        plant_lin(c, mei, [arjun])  # asserts 200


def test_dev_apply_plants_lin_with_audience_and_knowledge(mock_llm):
    with TestClient(app) as c:
        mei, arjun = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun")
        out = plant_lin(c, mei, [arjun])
        lin = out["entities"][0]
        assert lin["ref"] == "e1" and lin["slug"].startswith("p_lin_")
    with session_scope() as s:
        tie = s.scalars(select(m.Tie).where(m.Tie.dst_person == lin["id"])).one()
        assert tie.src_person == mei["id"] and tie.kind == "friend"
        aud = {a.person_id: a.via for a in s.scalars(select(m.FactAudience).where(m.FactAudience.fact_id == tie.fact_id))}
        assert aud == {mei["id"]: "said", arjun["id"]: "heard"}
        assert s.scalars(select(m.Knowledge).where(m.Knowledge.knower_id == arjun["id"], m.Knowledge.item_kind == "person",
                                                   m.Knowledge.item_id == lin["id"])).one().n_heard == 1


def test_forget_third_party_and_delete_me_leave_no_rows(mock_llm):
    from tests.test_delete import _people_refs
    with TestClient(app) as c:
        mei, arjun = sign_up(c, "Mei", "zh", phone="+8613800000000"), sign_up(c, "Arjun", phone="5125550101")
        befriend(c, arjun, mei)
        lin = plant_lin(c, mei, [arjun])["entities"][0]
        assert c.delete(f"/api/me/world/people/{mei['slug']}", headers=arjun["h"]).status_code == 403  # a user
        assert c.delete(f"/api/me/world/people/{lin['slug']}", headers=arjun["h"]).json() == {"deleted_facts": 0, "person_deleted": False}
        c.post("/api/dev/sms", json={"from": "+15125550101", "body": "started bouldering"})
        with session_scope() as s:
            fact_ids = list(s.scalars(select(m.Fact.id).where(m.Fact.subject_id == arjun["id"])))
        r = c.delete("/api/me", headers=arjun["h"])
        assert r.status_code == 200 and r.json()["deleted"] is True and r.json()["facts"] >= 1
        assert c.get("/api/me", headers=arjun["h"]).status_code == 401
        assert c.delete(f"/api/me/world/people/{lin['slug']}", headers=mei["h"]).json() == {"deleted_facts": 2, "person_deleted": True}
    with session_scope() as s:
        assert _people_refs(s, arjun["id"], fact_ids, ["started bouldering", "Mei is Arjun"]) == []
        assert _people_refs(s, lin["id"], [], ["Fudan"]) == []


def test_place_cannot_reach_hidden_people(mock_llm):
    with TestClient(app) as c:
        mei, arjun, priya = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun"), sign_up(c, "Priya")
        lin = plant_lin(c, mei, [arjun])["entities"][0]  # Priya never heard of Lin
        r = c.post("/api/world/place", headers=priya["h"], json={"person": lin["slug"], "owner": priya["slug"], "relation": "friend"})
        assert r.status_code == 404
        r = c.post("/api/world/place", headers=priya["h"], json={"name": "Lin", "owner": priya["slug"], "relation": "friend"})
        assert r.status_code == 200 and r.json()["id"] != lin["id"]
        world = c.get("/api/world", headers=priya["h"]).text
        assert "Fudan" not in world and lin["slug"] not in world
        # Arjun heard of Lin, so his name-only place reuses her.
        befriend(c, arjun, mei)
        r = c.post("/api/world/place", headers=arjun["h"], json={"name": "Lin", "owner": arjun["slug"], "relation": "friend"})
        assert r.status_code == 200 and r.json()["id"] == lin["id"]


def test_patch_text_clears_source_span_and_keys(mock_llm):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun", phone="5125550101")
        fid = c.post("/api/dev/sms", json={"from": "+15125550101", "body": "started bouldering"}).json()["facts"][0]["id"]
        with session_scope() as s:
            s.get(m.Fact, fid).text_src = "开始攀岩"
        r = c.patch(f"/api/me/facts/{fid}", headers=arjun["h"], json={"text": "started climbing"})
        assert r.status_code == 200 and r.json()["text"] == "started climbing"
    with session_scope() as s:
        f = s.get(m.Fact, fid)
        assert (f.text_src, f.keys) == ("", [])


def test_dev_apply_forces_line_zero(mock_llm):
    with TestClient(app) as c:
        mei = sign_up(c, "Mei", "zh")
        update = {"entities": [], "ties": [], "facts": [{"subject": "speaker", "predicate": "started", "text_en": "started pottery",
                  "text_src": "", "keys": [], "refs": [], "lines": [3], "sensitive_kind": "", "same_as": None,
                  "contradicts": None, "storyline": None}]}
        r = c.post("/api/dev/apply", json={"speaker": mei["slug"], "audience": [], "update": update})
        assert r.status_code == 200 and len(r.json()["facts"]) == 1
    with session_scope() as s:
        assert s.get(m.Fact, r.json()["facts"][0]).source_kind == "setup"


def test_world_storyline_carries_owner_and_hides_an_sms_title(mock_llm):
    from tests.test_cg_cards import add_fact
    with TestClient(app) as c:
        arjun, mei = sign_up(c, "Arjun"), sign_up(c, "Mei", "zh")
        befriend(c, arjun, mei)
        now = clock.now()
        with session_scope() as s:
            space = s.get(m.Person, arjun["id"]).family_id
            story = m.Storyline(family_id=space, slug="s_intern", owner_id=arjun["id"], title="Google Maps team internship",
                                keys=[["internship"]], created_at=now, updated_at=now)
            s.add(story)
            s.flush()
            f1 = add_fact(s, space, arjun["id"], arjun["id"], "state", "applied", [(arjun["id"], "authored")], now,
                          storyline_id=story.id, source_kind="message", shareable=False)
            f2 = add_fact(s, space, arjun["id"], arjun["id"], "state", "got an offer",
                          [(arjun["id"], "said"), (mei["id"], "heard")], now, storyline_id=story.id)
            s.add_all([m.StorylineState(storyline_id=story.id, seq=1, label="applied", fact_id=f1, at=now),
                       m.StorylineState(storyline_id=story.id, seq=2, label="got an offer", fact_id=f2, at=now)])
        theirs = c.get("/api/world", headers=mei["h"]).json()["storylines"]
        assert [(x["title"], x["owner"], [st["label"] for st in x["states"]]) for x in theirs] == \
            [("news", arjun["slug"], ["got an offer"])]
        mine = c.get("/api/world", headers=arjun["h"]).json()["storylines"]
        assert [(x["title"], x["owner"]) for x in mine] == [("Google Maps team internship", arjun["slug"])]


def test_place_same_as_confirms_either_candidate_of_an_ambiguous_ask(mock_llm, monkeypatch):
    """ "Which Ravi?" (cards._ask_ambiguous) posts relation same_as with the candidate as owner. One Ravi Arjun knows;
    the other only Paatti, the call's other participant, may disclose (her friend from the temple). That one is
    accepted only while the live call holds the ask card that offered it, so a guessed slug probes nothing."""
    from types import SimpleNamespace

    from app.audio import pipeline
    from app.world import cards as C
    from app.world.contracts import SuggestionOut
    from tests.test_cg_cards import add_tie, new_call
    with TestClient(app) as c:
        arjun, paatti, priya = sign_up(c, "Arjun"), sign_up(c, "Paatti", "ta"), sign_up(c, "Priya")
        now = clock.now()
        with session_scope() as s:
            space = s.get(m.Person, arjun["id"]).family_id
            ravis = [m.Person(family_id=space, slug=f"p_ravi_{k}", display_name="Ravi") for k in ("a", "b", "c")]
            s.add_all(ravis)
            s.flush()
            add_tie(s, space, arjun["id"], ravis[0].id, "friend", "", [(arjun["id"], "said")], now)
            add_tie(s, space, paatti["id"], ravis[1].id, "friend", "from the temple", [(paatti["id"], "said")], now)
            add_tie(s, space, priya["id"], ravis[2].id, "friend", "", [(priya["id"], "said")], now)  # Arjun never heard
            call = new_call(s, space)
            s.add_all([m.CallParticipant(call_id=call, person_id=p["id"], identity=f"p{p['id']}", lang="en", joined_at=now)
                       for p in (arjun, paatti)])
            ids = [r.id for r in ravis]
        temple = "Paatti's friend Ravi (from the temple)"
        card = C.ask("Ravi", "Ravi", "Which Ravi?", [SuggestionOut(owner="p_ravi_a", relation="same_as", label="your friend Ravi"),
                                                     SuggestionOut(owner="p_ravi_b", relation="same_as", label=temple)])
        live = {call: SimpleNamespace(world=SimpleNamespace(delivered={(f"p{arjun['id']}", card.key): card}))}
        monkeypatch.setattr(pipeline.registry, "get", live.get)
        place = lambda who, slug, call_id=call: c.post(  # noqa: E731
            "/api/world/place", headers=who["h"], json={"name": "Ravi", "owner": slug, "relation": "same_as", "call_id": call_id})
        for rid, slug in zip(ids[:2], ("p_ravi_a", "p_ravi_b")):
            r = place(arjun, slug)
            assert r.status_code == 200, r.text
            assert (r.json()["id"], r.json()["person"]) == (rid, slug)
        assert place(arjun, "p_ravi_b").json()["render"] == temple  # what the card showed, nothing more
        assert place(arjun, "p_ravi_b", None).status_code == 404  # outside the call Paatti is not speaking
        assert place(arjun, "p_ravi_c").status_code == 404  # only Priya heard of this Ravi, and no card offered her
        assert place(priya, "p_ravi_c").status_code == 403  # not her call
        assert place(paatti, "p_ravi_a").status_code == 404  # the card went to Arjun, not to her
        live[call] = SimpleNamespace(world=SimpleNamespace(delivered={}))  # live call, no ask card delivered
        assert place(arjun, "p_ravi_b").status_code == 404
        live.pop(call)  # the call ended: its CallParticipant rows remain, the card is gone
        assert place(arjun, "p_ravi_b").status_code == 404
        assert place(arjun, "p_ravi_a").status_code == 200  # a Ravi he knows himself needs no card
    with session_scope() as s:
        rows = {k.item_id: k.n_confirmed for k in s.scalars(select(m.Knowledge).where(
            m.Knowledge.knower_id == arjun["id"], m.Knowledge.item_kind == "person", m.Knowledge.item_id.in_(ids)))}
        assert rows == {ids[0]: 2, ids[1]: 2}
        assert s.scalar(select(func.count(m.Tie.id)).where(m.Tie.dst_person.in_(ids))) == 3  # no tie created
