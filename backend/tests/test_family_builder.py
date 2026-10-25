"""Nothing pre-seeded: a family starts as the learner + the person they call, and grows from confirmed cards."""
from fastapi.testclient import TestClient

from app.db.session import init_db, reset_engine, session_scope
from app.graph.builder import add_relative, create_family, path_label, suggest
from app.graph.kinship import FamilyGraph
from app.main import app
from app.mt.translate import Translator


def _graph(fid):
    with session_scope() as s:
        return FamilyGraph.from_session(s, fid)


def _setup(lang="ta"):
    reset_engine(); init_db()
    with session_scope() as s:
        fam, learner, elder = create_family(s, lang, learner_name="Arjun", elder_name="Kamala", elder_call="Paatti", elder_path="mother.mother")
        return fam.id, learner.slug, elder.slug


def test_setup_creates_learner_elder_and_an_unnamed_mom_between_them():
    fid, learner, elder = _setup()
    g = _graph(fid)
    assert g.learner_slug() == learner and g.elder_slug() == elder  # the placeholder Mom is never the "elder"
    assert g.shortest_path(g.by_slug[learner].id, g.by_slug[elder].id) == ["mother", "mother"]
    assert "paatti" in g.render(g.by_slug[learner].id, g.by_slug[elder].id).lower()


def test_confirmed_card_makes_the_next_mention_grounded():
    fid, learner, elder = _setup()
    assert not [s for s in Translator(_graph(fid)).linker.link("ரவி மாமா நேத்து போன் பண்ணான்", elder, learner) if s.node]
    with session_scope() as s:
        ravi = add_relative(s, fid, "mother.younger_brother", name="Ravi", call_them="மாமா")
    g = _graph(fid)
    linked = {sp.node for sp in Translator(g).linker.link("ரவி மாமா நேத்து போன் பண்ணான்", elder, learner) if sp.node}
    assert ravi.slug in linked
    assert g.shortest_path(g.by_slug[learner].id, g.by_slug[ravi.slug].id) == ["mother", "younger_brother"]


def test_naming_a_placeholder_fills_it_in_instead_of_duplicating():
    fid, learner, _ = _setup()
    with session_scope() as s:
        priya = add_relative(s, fid, "mother", name="Priya", call_them="Amma")
    g = _graph(fid)
    moms = [p for p in g.people.values() if g.shortest_path(g.by_slug[learner].id, p.id) == ["mother"]]
    assert [p.slug for p in moms] == [priya.slug] and moms[0].name == "Priya"


def test_two_people_with_the_same_name_stay_apart():
    fid, learner, _ = _setup()
    with session_scope() as s:
        a = add_relative(s, fid, "mother.younger_brother", name="Ravi", call_them="mama")
        b = add_relative(s, fid, "father.elder_brother", name="Ravi", call_them="periyappa")
    assert a.slug != b.slug
    g = _graph(fid)
    assert g.shortest_path(g.by_slug[learner].id, g.by_slug[b.slug].id) == ["father", "elder_brother"]


def test_suggestions_come_from_the_familys_language_table():
    assert any(x["path"] == "mother.brother" for x in suggest("மாமா", "ta"))
    assert any(x["path"] == "mother.mother" for x in suggest("नानी", "hi"))
    assert path_label("mother.younger_brother") == "Mom's younger brother"


def test_app_starts_with_no_family_and_setup_api_builds_one(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_FAMILY", "0")
    from app import config
    config.get_settings.cache_clear()
    with TestClient(app) as c:
        assert c.get("/api/family/all").json() == []
        r = c.post("/api/family/setup", json={"language": "hi", "your_name": "Riya", "their_name": "Savitri",
                                              "you_call_them": "Nani", "relation": "mother.mother"}).json()
        fid = r["family_id"]
        assert c.get("/api/family/all").json()[0]["heritage_lang"] == "hi"
        rel = c.post("/api/family/relative", json={"family_id": fid, "path": "mother.younger_brother", "name": "Rohit",
                                                   "you_call_them": "मामा"}).json()
        assert rel["render"].startswith("your") and "Rohit" in rel["render"]
        assert any(x["path"] == "mother.brother" for x in c.get(f"/api/family/suggest?term=मामा&family_id={fid}").json())


def test_a_kin_word_with_no_relative_yet_is_flagged_for_a_card_and_not_called_generic():
    fid, learner, elder = _setup()
    tr = Translator(_graph(fid))
    spans = tr.linker.link("ரவி மாமா நேத்து போன் பண்ணான்", elder, learner)
    unknown = [s for s in spans if s.type == "kin" and s.node is None and s.method == "unknown-relative"]
    assert [s.source for s in unknown] == ["மாமா"]
    prompt = tr.user_prompt("ரவி மாமா நேத்து போன் பண்ணான்", elder, learner, spans, [], [])
    assert "NOT a relative" not in prompt and "not on the family graph yet" in prompt


def test_graph_before_any_family_is_a_clean_404_not_a_crash(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_FAMILY", "0")
    from app import config
    config.get_settings.cache_clear()
    with TestClient(app) as c:
        r = c.get("/api/family/graph")
        assert r.status_code == 404 and "set one up" in r.json()["detail"]
        assert c.get("/api/languages").status_code == 200 and c.get("/api/family/relations").status_code == 200
