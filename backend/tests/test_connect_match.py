"""POST /api/connect/match: which of my phone contacts are on KIN, by sha256 of the E.164 number. Offline TestClient."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.world.users import create_user, normalize_phone
from app.db.session import session_scope

PHONE = "+15125550100"


def _sha(number: str) -> str:
    return hashlib.sha256(number.encode()).hexdigest()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _user(name, phone=None):
    with session_scope() as s:
        _, p, tok = create_user(s, name, "en", phone)
        return p.slug, {"X-KIN-User": tok}


def _match(client, h, hashes):
    return client.post("/api/connect/match", json={"hashes": hashes}, headers=h)


def test_finds_by_hash_of_e164_and_of_a_local_format(client):
    mei_slug, mei = _user("Mei", PHONE)
    _, arjun = _user("Arjun")
    assert normalize_phone("(512) 555-0100") == PHONE == normalize_phone("1 512 555 0100")
    for typed in (PHONE, "(512) 555-0100"):  # the client hashes its normalized contact number
        r = _match(client, arjun, [_sha(normalize_phone(typed)), _sha("+15125550199")])
        assert r.status_code == 200, r.text
        assert r.json() == {"results": [{"slug": mei_slug, "name": "Mei", "relation": "none"}]}
    assert PHONE not in r.text
    assert _match(client, mei, [_sha(PHONE)]).json() == {"results": []}  # never yourself


def test_relation_follows_requests_and_slug_add(client):
    mei_slug, mei = _user("Mei", "+15125550101")
    arjun_slug, arjun = _user("Arjun", "+15125550102")
    rel = lambda h, n: [x["relation"] for x in _match(client, h, [_sha(n)]).json()["results"]]  # noqa: E731
    r = client.post("/api/connect", json={"slug": mei_slug}, headers=arjun)
    assert r.status_code == 200 and r.json() == {"status": "pending", "user": {"slug": mei_slug, "name": "Mei"}}
    assert rel(arjun, "+15125550101") == ["requested"] and rel(mei, "+15125550102") == ["incoming"]
    assert client.post("/api/connect", json={"slug": arjun_slug}, headers=mei).json()["status"] == "accepted"
    assert rel(arjun, "+15125550101") == ["connected"] == rel(mei, "+15125550102")


def test_validation_and_auth(client):
    _, a = _user("Arjun")
    assert _match(client, a, [_sha("+15125550123")]).json() == {"results": []}
    assert _match(client, a, []).json() == {"results": []}
    assert _match(client, a, [_sha(str(i)) for i in range(2001)]).status_code == 422
    assert _match(client, a, ["not-hex"]).status_code == 422
    assert _match(client, a, [_sha(PHONE).upper()]).status_code == 422  # lowercase only
    assert client.post("/api/connect/match", json={"hashes": []}).status_code == 401
    assert client.post("/api/connect", json={"slug": "p_nobody_0"}, headers=a).status_code == 404
    assert client.post("/api/connect", json={}, headers=a).status_code == 422
    assert client.post("/api/connect", json={"handle": "x-1", "slug": "p_x_1"}, headers=a).status_code == 422
