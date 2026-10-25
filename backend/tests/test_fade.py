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


def test_simulation_does_not_touch_real_learner_rows_and_uses_lemmas():
    with TestClient(app) as c:
        c.post("/api/fade/reset", json={"learner": "p_arjun"})
        c.post("/api/fade/expose", json={"learner": "p_arjun", "text": "நேத்து"})
        before = c.get("/api/fade/mastery?learner=p_arjun").json()
        w8 = c.post("/api/fade/simulate", json={"learner": "p_arjun", "weeks": 8}).json()
        after = c.get("/api/fade/mastery?learner=p_arjun").json()
        assert after == before, "simulation must not write the real learner's mastery"
        assert "சாப்பிட்டியா" in w8["passthrough"] and "மழை" in {t["lemma_surface"] for t in w8["trajectories"]}
        assert all(t["lemma"] == t["lemma"].strip() for t in w8["trajectories"])
        assert w8["mastery"] and all({"lemma", "p_known", "mastered"} <= set(r) for r in w8["mastery"])


def test_fade_routes_never_touch_the_world_space(monkeypatch):
    """Seeding off: family 1 is the world space, and Fade (a legacy-family mode) answers 404 like a missing family."""
    monkeypatch.setenv("SEED_DEMO_FAMILY", "0")
    from app import config
    from app.db.session import reset_engine, session_scope
    from app.world.users import create_user
    config.get_settings.cache_clear(); reset_engine()
    with TestClient(app) as c:
        with session_scope() as s:
            _, me, _ = create_user(s, "Arjun", "ta")
            slug = me.slug
        body = {"learner": slug, "text": "நேத்து"}
        assert c.get(f"/api/fade/mastery?learner={slug}").status_code == 404
        for path in ("expose", "verify", "policy", "reset", "simulate"):
            assert c.post(f"/api/fade/{path}", json=body).status_code == 404, path


def test_fade_verify_never_reads_a_world_utterance():
    """With the legacy family seeded, a world user's slug and a world transcript are still out of Fade's reach."""
    import pytest
    from app.db import models as m
    from app.db.session import session_scope
    from app.world.users import create_user, get_space
    with TestClient(app) as c:
        with session_scope() as s:
            _, me, _ = create_user(s, "Paatti", "ta")
            call = m.Call(family_id=get_space(s).id, transport="livekit", mode="world"); s.add(call); s.flush()
            u = m.Utterance(call_id=call.id, speaker_id=me.id, listener_id=me.id, src_text="நேத்து போன் பண்ணான்")
            s.add(u); s.flush()
            uid, pid, slug = u.id, me.id, me.slug
        r = c.post("/api/fade/verify", json={"utterance_id": uid, "understood": True}).json()
        assert r["lemmas"] == [] and r["learner"] == "p_arjun"
        with pytest.raises(ValueError):  # the world slug is not a learner in the legacy family
            c.get(f"/api/fade/mastery?learner={slug}")
        with session_scope() as s:
            assert s.query(m.Mastery).filter(m.Mastery.learner_id == pid).count() == 0
