"""Cross-script name forms (ARCHITECTURE 3.3): a language new to the space refetches everyone's forms."""
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


def test_a_new_language_refetches_the_other_users_forms(mock_llm, fetched):
    with TestClient(app) as c:
        mei, arjun = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun", "en")
        assert fetched == [mei["id"], arjun["id"]]  # English is always asked for
        priya = sign_up(c, "Priya", "zh")
        assert fetched[2:] == [priya["id"]]  # Chinese is not new
        fetched.clear()
        paatti = sign_up(c, "Paatti", "ta")
        assert fetched[0] == paatti["id"] and sorted(fetched[1:]) == sorted([mei["id"], arjun["id"], priya["id"]])


def test_switching_to_a_new_language_refetches_the_others(mock_llm, fetched):
    with TestClient(app) as c:
        mei, arjun = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun", "en")
        fetched.clear()
        assert c.patch("/api/me", headers=arjun["h"], json={"lang": "zh"}).status_code == 200
        assert fetched == []  # Mei already speaks it
        assert c.patch("/api/me", headers=arjun["h"], json={"lang": "ta"}).status_code == 200
        assert fetched == [mei["id"]]
