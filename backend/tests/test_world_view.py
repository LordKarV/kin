import time
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.db.seed import seed_demo_family
from app.db.session import init_db, reset_engine, session_scope
from app.graph.kinship import FamilyGraph
from app.world.users import create_user
from app.world.view import WorldView

SEP14 = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def _fact(s, space, subject, speaker, predicate, text, audience, refs=(), at=SEP14, keys=()):
    f = m.Fact(family_id=space, subject_id=subject, speaker_id=speaker, predicate=predicate, text=text, lang="en",
               keys=[list(k) for k in keys], source_kind="call", said_at=at)
    s.add(f)
    s.flush()
    s.add_all([m.FactAudience(fact_id=f.id, person_id=p, via="heard", at=at) for p in audience])
    s.add_all([m.FactRef(fact_id=f.id, kind=k, ref_id=i) for k, i in refs])
    s.flush()
    return f.id


def _tie(s, space, src, dst, kind, context, audience, speaker=None):
    fid = _fact(s, space, src, speaker or src, "tie", f"{kind} {context}".strip(), audience, refs=[("person", dst)])
    s.add(m.Tie(family_id=space, src_person=src, dst_person=dst, kind=kind, context=context, fact_id=fid))
    s.flush()
    return fid


@pytest.fixture
def world():
    reset_engine()
    init_db()
    with session_scope() as s:
        seed_demo_family(s)  # Krishnan family stays a separate tenant next to the space
        ids = {}
        for name, lang in [("Arjun", "en"), ("Mei", "zh"), ("Priya", "en"), ("Paatti", "ta")]:
            _, p, _ = create_user(s, name, lang)
            ids[name.lower()] = p.id
        space = s.get(m.Person, ids["arjun"]).family_id
        s.get(m.Person, ids["arjun"]).gender = "m"
        s.get(m.Person, ids["paatti"]).gender = "f"
        lin = m.Person(family_id=space, slug="p_lin", display_name="Lin")
        lin.aliases = [m.Alias(alias="林", lang="zh", kind="translit"), m.Alias(alias="Lynn", lang="en", kind="asr")]
        mom = m.Person(family_id=space, slug="p_mom", display_name="Mom", gender="f")
        jess = m.Person(family_id=space, slug="p_jess", display_name="Jess")
        s.add_all([lin, mom, jess])
        s.flush()
        a, mei, priya, paatti = ids["arjun"], ids["mei"], ids["priya"], ids["paatti"]
        ids.update(lin=lin.id, mom=mom.id, jess=jess.id, space=space)
        s.add_all([m.Edge(family_id=space, src_person=paatti, dst_person=mom.id, relation="parent"),
                   m.Edge(family_id=space, src_person=mom.id, dst_person=a, relation="parent")])
        ids["tie_lin"] = _tie(s, space, mei, lin.id, "friend", "from the Fudan climbing wall", [mei, a])
        ids["tie_mei"] = _tie(s, space, a, mei, "friend", "from high school", [a])
        ids["lives_arjun"] = _fact(s, space, mei, a, "lives_in", "lives in Shanghai", [a],
                                   refs=[("person", mei)], keys=[("Shanghai", "上海")])
        ids["lives_mei"] = _fact(s, space, mei, mei, "lives_in", "lives in Pudong", [mei, a], refs=[("person", mei)])
        ids["tie_jess"] = _tie(s, space, priya, jess.id, "roommate", "", [priya])
        ids["priya_only"] = _fact(s, space, priya, priya, "did", "went to Austin with Jess", [priya],
                                  refs=[("person", jess.id)])
    return ids


def _view(ids, *members):
    with session_scope() as s:
        return WorldView.build(s, ids["space"], [ids[x] for x in members], NOW)


def test_render_speaker_context_for_third_party(world):
    v = _view(world, "arjun", "mei")
    assert v.render(world["arjun"], world["lin"], speaker=world["mei"]) == \
        "Mei's friend Lin (from the Fudan climbing wall)"


def test_render_cross_world_through_kin_speaker(world):
    v = _view(world, "arjun", "paatti")
    assert v.render(world["paatti"], world["mei"], speaker=world["arjun"]).startswith("your grandson Arjun's friend Mei")


def test_render_kin_path(world):
    v = _view(world, "arjun", "paatti")
    text = v.render(world["paatti"], world["arjun"])
    assert text.startswith("your grandson Arjun") and text.endswith("(your daughter's son)")
    assert v.render(world["arjun"], world["arjun"]) == "you"


def test_card_body_uses_only_speakers_own_identity_facts(world):
    v = _view(world, "arjun", "paatti")
    body, fids = v.card_body(world["paatti"], "person", world["mei"], world["arjun"], NOW)
    assert "Shanghai" in body and world["lives_arjun"] in fids
    assert "Pudong" not in body and world["lives_mei"] not in fids  # Mei said it, Arjun cannot disclose it


def test_card_body_first_mentioned_only_counts_what_the_listener_heard(world):
    """Paatti never heard of Mei: Arjun's facts disclosed now must not date the card ("New to you" + "Sep 14")."""
    v = _view(world, "arjun", "paatti")
    body, fids = v.card_body(world["paatti"], "person", world["mei"], world["arjun"], NOW)
    assert "Shanghai" in body and "first mentioned" not in body
    assert "first mentioned Sep 14" in v.card_body(world["arjun"], "person", world["mei"], None, NOW)[0]


def test_card_body_first_mentioned(world):
    with session_scope() as s:
        later = _fact(s, world["space"], world["lin"], world["mei"], "lives_in", "lives in Beijing",
                      [world["mei"], world["arjun"]], at=SEP14 + timedelta(days=17))
    v = _view(world, "arjun", "mei")
    body, fids = v.card_body(world["arjun"], "person", world["lin"], world["mei"], NOW)
    assert body.startswith("Mei's friend Lin") and "Beijing" in body
    assert "first mentioned Sep 14" in body and "Oct 1" not in body  # earliest fact, not the newest
    assert world["tie_lin"] in fids and later in fids


def test_structural_known_needs_a_tie(world):
    v = _view(world, "arjun", "mei")
    assert not v.structural_known(world["priya"], "person", world["lin"])
    with session_scope() as s:
        _tie(s, world["space"], world["priya"], world["lin"], "classmate", "", [world["priya"]])
    v = _view(world, "arjun", "mei")
    assert v.structural_known(world["priya"], "person", world["lin"])
    assert v.structural_known(world["arjun"], "person", world["mei"])
    assert not v.structural_known(world["arjun"], "person", world["lin"])


def test_roster_only_what_every_listener_heard(world):
    v = _view(world, "arjun", "mei", "priya")
    alone = v.roster(frozenset({world["arjun"]}), world["mei"])
    both = v.roster(frozenset({world["arjun"], world["priya"]}), world["mei"])
    assert "Jess" not in alone and "Austin" not in alone
    assert "Jess" not in both and "Austin" not in both
    assert "Jess" in v.roster(frozenset({world["priya"]}), world["mei"])
    assert "Mei's friend Lin (from the Fudan climbing wall)" in alone
    assert "| Lin |" in both  # Mei speaking may disclose her own friend
    assert "| Lin |" not in v.roster(frozenset({world["arjun"], world["priya"]}), world["arjun"])  # Arjun may not


def test_roster_has_no_notes_and_respects_recent_ids(world):
    with session_scope() as s:
        s.get(m.Person, world["lin"]).notes = "SECRET NOTE"
    v = _view(world, "arjun", "mei")
    r = v.roster(frozenset({world["arjun"]}), world["mei"], recent_ids=[world["lin"]])
    assert "SECRET" not in r
    lines = r.splitlines()
    assert lines[0].startswith(v.people[world["mei"]].slug)  # speaker first
    assert any(line.startswith("p_lin | Lin |") and "林" in line for line in lines)


def test_visibility_of_third_party(world):
    v = _view(world, "arjun", "mei", "priya")
    assert v.visible(world["arjun"], "person", world["lin"])
    assert not v.visible(world["priya"], "person", world["lin"])
    assert not v.visible(world["arjun"], "person", world["jess"])
    assert v.visible(world["priya"], "person", world["jess"])


def test_index_and_fact_forms(world):
    v = _view(world, "arjun", "mei")
    forms = v.index_forms()
    assert ("林", "person", world["lin"]) in forms and ("Lynn", "person", world["lin"]) in forms
    assert ("上海", "fact", world["lives_arjun"]) in v.fact_forms()


def test_family_graph_person_filter_and_krishnan_unchanged(world):
    with session_scope() as s:
        fam = s.query(m.Family).filter_by(kind="family").first()
        full = FamilyGraph.from_session(s, fam.id)
        assert len(full.people) == len(FamilyGraph.from_session(s, fam.id, person_ids=None).people)
        a = full.by_slug["p_arjun"].id
        assert full.render(a, full.by_slug["p_ravi_mama"].id) == "your uncle Ravi mama (Mom's younger brother)"
        keep = {a, full.by_slug["p_priya"].id}
        part = FamilyGraph.from_session(s, fam.id, person_ids=keep)
        assert set(part.people) == keep and part.role(a, full.by_slug["p_priya"].id) == "mom"


def test_build_300_people_fast(world):
    with session_scope() as s:
        space, mei = world["space"], world["mei"]
        people = [m.Person(family_id=space, slug=f"p_x{i}", display_name=f"X{i}") for i in range(300)]
        s.add_all(people)
        s.flush()
        for i, p in enumerate(people):
            _tie(s, space, mei, p.id, "friend", "", [mei, world["arjun"]])
            if i % 3 == 0:
                _fact(s, space, p.id, mei, "lives_in", f"lives in city {i}", [mei], at=SEP14 + timedelta(days=i % 30))
    t0 = time.perf_counter()
    v = _view(world, "arjun", "mei")
    elapsed = time.perf_counter() - t0
    assert len(v.people) > 300
    assert elapsed < 0.2, elapsed


def _add(s, *rows):
    s.add_all(rows)
    s.flush()
    return rows


def test_kin_render_skips_a_path_through_a_hidden_edge(world):
    """FamilyGraph's shortest path to Raj is Mom -> (shared parent Paatti) -> Raj, but only Priya heard that Raj is
    Paatti's son. A longer visible route exists (Mom's husband's brother), so rule 2 must not print "Mom's brother"."""
    with session_scope() as s:
        sp, a, mom = world["space"], world["arjun"], world["mom"]
        dad, raj = _add(s, m.Person(family_id=sp, slug="p_dad", display_name="Dad", gender="m"),
                        m.Person(family_id=sp, slug="p_raj", display_name="Raj", gender="m"))
        hidden = _fact(s, sp, raj.id, world["priya"], "parent", "Raj is Paatti's son", [world["priya"]])
        _add(s, m.Edge(family_id=sp, src_person=world["paatti"], dst_person=raj.id, relation="parent", fact_id=hidden),
             m.Edge(family_id=sp, src_person=mom, dst_person=dad.id, relation="spouse"),
             m.Edge(family_id=sp, src_person=dad.id, dst_person=raj.id, relation="sibling"))
        raj_id = raj.id
    v = _view(world, "arjun", "paatti")
    assert v.kin.shortest_path(a, raj_id) == ["mother", "brother"]
    assert v.render(a, raj_id) == "Mom's husband's brother Raj"


def test_render_bfs_and_fallback(world):
    with session_scope() as s:
        sp, a, priya, jess = world["space"], world["arjun"], world["priya"], world["jess"]
        (kim,) = _add(s, m.Person(family_id=sp, slug="p_kim", display_name="Kim", gender="f"),)
        _tie(s, sp, a, priya, "classmate", "", [a])
        _tie(s, sp, priya, jess, "roommate", "", [priya, a])
        fid = _fact(s, sp, jess, priya, "sibling", "Jess's sister Kim", [priya, a], refs=[("person", kim.id)])
        _add(s, m.Edge(family_id=sp, src_person=jess, dst_person=kim.id, relation="sibling", fact_id=fid))
        kim_id = kim.id
    v = _view(world, "arjun", "priya")
    assert v.render(a, kim_id) == "Priya's roommate's sister Kim"  # rule 5, anchored at Priya
    assert v.render(priya, world["lin"], speaker=a) == "Lin, mentioned by Arjun"  # rule 6
    assert v.render(priya, world["lin"]) == "Lin"


def test_group_hops_need_both_memberships_visible(world):
    with session_scope() as s:
        sp, paatti, lin = world["space"], world["paatti"], world["lin"]
        (bo,) = _add(s, m.Person(family_id=sp, slug="p_bo", display_name="Bo"))
        (g,) = _add(s, m.Group(family_id=sp, slug="g_choir", name="choir"))
        f_paatti = _fact(s, sp, paatti, paatti, "member_of", "sings in the choir", [paatti])
        f_bo = _fact(s, sp, bo.id, paatti, "member_of", "Bo sings in the choir", [paatti])
        _add(s, m.GroupMember(group_id=g.id, person_id=paatti, fact_id=f_paatti),
             m.GroupMember(group_id=g.id, person_id=bo.id, fact_id=f_bo),
             m.GroupMember(group_id=g.id, person_id=lin, fact_id=None))
        bo_id = bo.id
    v = _view(world, "arjun", "mei", "priya", "paatti")
    assert v.structural_known(paatti, "person", lin)  # shared group, no tie
    assert v.structural_known(paatti, "person", bo_id)
    assert v.render(paatti, bo_id) == "your fellow choir member Bo"
    assert v.render(world["arjun"], bo_id) == "Bo"  # Arjun never heard either membership


def test_tie_fact_about_someone_else_is_disclosable_only_for_its_subject(world):
    """Mei said "Priya's roommate is Kate" to Arjun alone: subject Priya. Rendering Kate for Paatti with Mei
    speaking only mentions Kate, so the tie stays hidden (D9: the speaker or the entity just mentioned)."""
    with session_scope() as s:
        sp, mei, priya = world["space"], world["mei"], world["priya"]
        (kate,) = _add(s, m.Person(family_id=sp, slug="p_kate", display_name="Kate"))
        _tie(s, sp, priya, kate.id, "roommate", "", [mei, world["arjun"]], speaker=mei)
        kate_id = kate.id
    v = _view(world, "mei", "paatti")
    assert not v.visible(world["paatti"], "person", kate_id, speaker=mei)
    assert v.render(world["paatti"], kate_id, speaker=mei) == "Kate, mentioned by Mei"


def test_card_body_drops_expired_and_sensitive_facts_and_falls_back_to_first_at(world):
    with session_scope() as s:
        sp, a, mei, jess = world["space"], world["arjun"], world["mei"], world["jess"]
        old = _fact(s, sp, jess, mei, "lives_in", "lives in Dallas", [a, mei])
        s.get(m.Fact, old).expires_at = NOW - timedelta(days=1)
        sick = _fact(s, sp, jess, mei, "health", "has the flu", [a, mei])
        s.get(m.Fact, sick).sensitive_kind = "health"
        _add(s, m.Knowledge(knower_id=a, item_kind="person", item_id=jess, p=0.9, half_life_days=30,
                            first_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
                            last_at=SEP14, last_day="2026-09-14"))
    v = _view(world, "arjun", "mei")
    body, fids = v.card_body(a, "person", jess, None, NOW)
    assert "Dallas" not in body and "flu" not in body and not fids
    assert "first mentioned Aug 2" in body
    earlier, _ = v.card_body(a, "person", jess, None, SEP14)  # a card's own clock decides expiry
    assert "Dallas" in earlier


def test_roster_cap_and_empty_listeners(world):
    with session_scope() as s:
        sp, mei = world["space"], world["mei"]
        people = _add(s, *[m.Person(family_id=sp, slug=f"p_y{i}", display_name=f"Y{i}") for i in range(60)])
        for p in people:
            _tie(s, sp, mei, p.id, "friend", "", [mei, world["arjun"]])
    v = _view(world, "arjun", "mei")
    assert len(v.roster(frozenset({world["arjun"]}), mei).splitlines()) == 40
    with pytest.raises(ValueError):
        v.roster(frozenset(), mei)


def test_world_view_constructs_from_spec_fields():
    v = WorldView(1, frozenset({1}), FamilyGraph(1, "en", [], [], []), {}, {}, {}, {}, {}, {}, {}, {})
    assert v.links == {} and v.now.tzinfo is not None
