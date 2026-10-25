"""World REST (docs/ARCHITECTURE.md 9.2): sign-up, X-KIN-User auth, visibility of /api/world, place, dev routes, delete."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

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
