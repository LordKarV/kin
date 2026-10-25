"""scripts/demo_common_ground.py against the in-process app with a mock LLM: the planted story, the sign-in links and
the dev sign-in route. The LiveKit legs are stubbed; only the HTTP contract the driver relies on is exercised."""
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import llm as llm_mod
from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.world import clock
from app.world.match import AliasIndex
from app.world.users import get_space
from app.world.view import WorldView

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import demo_common_ground as demo  # noqa: E402


def _reply(content: dict) -> httpx.Response:
    return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                     "choices": [{"index": 0, "finish_reason": "stop",
                                                  "message": {"role": "assistant", "content": json.dumps(content)}}],
                                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


@pytest.fixture
def mock_llm(monkeypatch):
    def handler(req: httpx.Request):
        name = json.loads(req.content)["response_format"]["json_schema"]["name"]
        if name == "FormsOut":
            return _reply({"forms": []})
        if name == "SmsOut":
            return _reply({"facts": [{"predicate": "started", "text_en": "started bouldering", "storyline": None,
                                      "keys": [["bouldering", "climbing", "攀岩"]], "sensitive_kind": "", "told": []}],
                           "ack": "Nice: you started bouldering."})
        return httpx.Response(500, json={"error": f"unexpected schema {name}"})

    monkeypatch.setattr(llm_mod, "_default", llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m",
                                                         transport=httpx.MockTransport(handler)))
    yield
    monkeypatch.setattr(llm_mod, "_default", None)


@pytest.fixture(autouse=True)
def _reset_clock():
    clock.set_offset_days(0)
    yield
    clock.set_offset_days(0)


class _Http:
    """Demo.http over the in-process app (TestClient answers with httpx.Response, same as the AsyncClient)."""

    def __init__(self, c: TestClient) -> None:
        self.c = c

    async def post(self, path: str, json: dict, headers: dict) -> httpx.Response:
        return self.c.post(path, json=json, headers=headers)


def test_driver_plants_the_story(mock_llm, monkeypatch, capsys):
    from app.rtc import agent as agent_mod
    monkeypatch.setattr(agent_mod.agents, "ensure", lambda call_id: None)

    async def no_livekit(self, join):
        self.join = join
        return self

    monkeypatch.setattr(demo.Leg, "connect", no_livekit)
    with TestClient(app) as c:
        d = demo.Demo(_Http(c), wait_s=0)

        async def run():
            await d.clock(-42)
            await d.users()
            await d.plant_call_1()
            await d.plant_arjun()
            await d.plant_ravis()
            await d.sms()
            return await d.call("Arjun", "Mei")

        _cid, legs = asyncio.run(run())
        out = capsys.readouterr().out
        assert "placed Paatti for Arjun: your grandmother Paatti (Mom's mom)" in out
        assert "placed ravi_mama for Arjun: your uncle Ravi (Mom's younger brother)" in out
        assert "placed ravi_periyappa for Arjun: your uncle Ravi (Dad's elder brother)" in out
        assert "reply 'Nice: you started bouldering.'" in out
        # the second leg joined the first leg's call through its invite code
        assert legs["Mei"].join["call_id"] == legs["Arjun"].join["call_id"]
        world = c.get("/api/world", headers={"X-KIN-User": d.token["Arjun"]}).json()
        ravis = {p["id"] for p in world["people"] if p["name"] == "Ravi"}
        assert len(ravis) == 2  # two uncles, not one merged Ravi
        with session_scope() as s:  # Paatti's line names each one by his kin word, and the alias index tells them apart
            members = list(s.scalars(select(m.Person.id).where(m.Person.slug.in_([d.slug["Arjun"], d.slug["Paatti"]]))))
            view = WorldView.build(s, get_space(s).id, members, clock.now())
            hits = [h for h in AliasIndex(view.index_forms()).scan(demo.PAATTI_RAVIS, "ta") if h.kind == "person"]
        assert [h.surface for h in hits] == ["ரவி மாமா", "ரவி பெரியப்பா"] and {h.ids for h in hits} == {(i,) for i in ravis}


def test_signin_links_carry_the_token_and_a_reachable_server():
    tok = "a+b/c=="
    q = parse_qs(urlsplit(demo.signin_link(tok, "http://localhost:8000", "")).query)
    assert q == {"token": [tok]}  # a phone cannot reach the laptop's loopback: keep the phone's own server
    link = demo.signin_link(tok, "http://192.168.1.20:8000", "k&y")
    assert link.startswith("kin://signin?")
    assert parse_qs(urlsplit(link).query) == {"token": [tok], "server": ["http://192.168.1.20:8000"], "key": ["k&y"]}


def test_dev_signin_rotates_the_token(mock_llm):
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        old = c.post("/api/users", json={"name": "Arjun", "lang": "en"}).json()
        r = c.post("/api/dev/signin", json={"person": old["person"]})
        assert r.status_code == 200 and r.json()["person"] == old["person"]
        new = r.json()["token"]
        assert c.get("/api/me", headers={"X-KIN-User": new}).json()["person"] == old["person"]
        assert c.get("/api/me", headers={"X-KIN-User": old["token"]}).status_code == 401
        assert c.post("/api/dev/signin", json={"person": "p_nobody_99"}).status_code == 404
    with TestClient(app) as c:  # host "testclient": not loopback, so the key alone never mints a token
        assert c.post("/api/dev/signin", json={"person": old["person"]}).status_code == 404
        assert c.get("/api/me", headers={"X-KIN-User": new}).status_code == 200  # and nothing was rotated


def test_dev_signin_is_off_without_dev_endpoints(monkeypatch):
    from app import config
    monkeypatch.setenv("DEV_ENDPOINTS", "0")
    config.get_settings.cache_clear()
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        assert c.post("/api/dev/signin", json={"person": "p_arjun_1"}).status_code == 404
