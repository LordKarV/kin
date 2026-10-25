"""Changing your primary language after sign-up: PATCH /api/me {"lang": code}."""
import pytest
from fastapi.testclient import TestClient

from app.api import users as users_api
from app.main import app
from tests.test_world_api import _reset_clock, mock_llm, sign_up  # noqa: F401


@pytest.fixture
def fetched(monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(users_api, "fetch_forms", seen.append)
    return seen


def test_patch_lang_updates_me_and_returns_the_get_me_shape(mock_llm, fetched):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun", "en")
        r = c.patch("/api/me", headers=arjun["h"], json={"lang": "ta"})
        assert r.status_code == 200, r.text
        me = c.get("/api/me", headers=arjun["h"]).json()
        assert r.json() == me and me["lang"] == "ta"


def test_patch_lang_needs_a_token_and_a_supported_code(mock_llm, fetched):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun", "en")
        assert c.patch("/api/me", json={"lang": "ta"}).status_code == 401
        assert c.patch("/api/me", headers=arjun["h"], json={"lang": "xx"}).status_code == 422
        assert c.get("/api/me", headers=arjun["h"]).json()["lang"] == "en"


def test_a_language_new_to_the_space_refetches_the_others_forms(mock_llm, fetched):
    with TestClient(app) as c:
        mei, arjun = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun", "en")
        fetched.clear()
        assert c.patch("/api/me", headers=arjun["h"], json={"lang": "ta"}).status_code == 200
        assert fetched == [mei["id"]]
