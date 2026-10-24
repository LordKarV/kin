from fastapi.testclient import TestClient
from app.main import app


def test_family_graph_endpoint_renders_relative_to_learner():
    with TestClient(app) as c:
        j = c.get("/api/family/graph").json()
    people = {p["id"]: p for p in j["people"]}
    assert j["learner"] == "p_arjun" and j["heritage_lang"] == "ta"
    assert people["p_ravi_mama"]["render"] == "your uncle Ravi mama (Mom's younger brother)"
    assert any(e["src"] == "p_priya" and e["dst"] == "p_arjun" and e["relation"] == "parent" for e in j["edges"])
    assert any(t["id"] == "d_rasam" and t["kind"] == "dish" for t in j["things"])
    assert people["p_kamala"]["generation"] == -2 and people["p_arjun"]["generation"] == 0


def test_glossary_endpoint_lists_cards_newest_first():
    with TestClient(app) as c:
        assert c.get("/api/glossary").json() == []
