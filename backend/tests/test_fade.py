import json
from fastapi.testclient import TestClient

from app.fade.lemmas import heritage_lemmas, lemma
from app.main import app


def test_lemmatizer_strips_common_tamil_suffixes():
    assert lemma("அடையாறுலேர்ந்து") == "அடையாறு"
    assert lemma("மதுரைக்கு") == "மதுரை"
    assert lemma("நேத்து") == "நேத்து"
    assert lemma("ரவியும்") == "ரவி"
    assert lemma("Madurai-kku") == "madurai"


def test_heritage_lemmas_skip_english_and_short_tokens():
    out = heritage_lemmas("இன்னைக்கு phone பண்ணான், ok?")
    assert "இன்னைக்கு" in out and "பண்ணான்" in out
    assert "phone" not in out and "ok" not in out


def test_exposures_verification_and_policy_threshold():
    with TestClient(app) as c:
        c.post("/api/fade/reset", json={"learner": "p_arjun"})
        # 1 exposure: still translated
        c.post("/api/fade/expose", json={"learner": "p_arjun", "text": "நேத்து போன் பண்ணான்"})
        m = {r["lemma"]: r for r in c.get("/api/fade/mastery?learner=p_arjun").json()}
        assert 0.1 < m["நேத்து"]["p_known"] < 0.5 and m["நேத்து"]["n_exposures"] == 1
        # verified understanding x6 pushes past the 0.85 threshold
        for _ in range(6):
            c.post("/api/fade/verify", json={"learner": "p_arjun", "text": "நேத்து", "understood": True})
        m = {r["lemma"]: r for r in c.get("/api/fade/mastery?learner=p_arjun").json()}
        assert m["நேத்து"]["p_known"] >= 0.85 and m["நேத்து"]["n_verified"] == 6
        pt = c.post("/api/fade/policy", json={"learner": "p_arjun", "text": "உன் மாமா நேத்து போன் பண்ணான்."}).json()
        assert pt["passthrough"] == ["நேத்து"]


def test_policy_never_passes_through_inside_grounded_entity_span():
    with TestClient(app) as c:
        c.post("/api/fade/reset", json={"learner": "p_arjun"})
        for _ in range(8):
            c.post("/api/fade/verify", json={"learner": "p_arjun", "text": "மாமா ரவி நேத்து", "understood": True})
        pt = c.post("/api/fade/policy", json={"learner": "p_arjun", "text": "ரவி மாமா நேத்து போன் பண்ணான்."}).json()
        assert "நேத்து" in pt["passthrough"] and "மாமா" not in pt["passthrough"] and "ரவி" not in pt["passthrough"]


def test_simulation_replays_real_history_and_reduces_translated_words():
    with TestClient(app) as c:
        c.post("/api/fade/reset", json={"learner": "p_arjun"})
        w1 = c.post("/api/fade/simulate", json={"learner": "p_arjun", "weeks": 1}).json()
        w8 = c.post("/api/fade/simulate", json={"learner": "p_arjun", "weeks": 8}).json()
        assert w1["weeks"] == 1 and w8["weeks"] == 8 and w8["simulated"] is True
        assert len(w8["passthrough"]) > len(w1["passthrough"])
        assert all(len(t["curve"]) == 9 for t in w8["trajectories"])  # week 0..8 per word
        assert any(t["curve"][-1] >= 0.85 for t in w8["trajectories"])
