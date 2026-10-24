from sqlalchemy import select, func
from app.db import models as m
from app.db.session import session_scope, init_db, reset_engine
from app.db.seed import seed_demo_family

def _seed():
    reset_engine(); init_db()
    with session_scope() as s:
        fam = seed_demo_family(s)
        return fam.id

def test_seed_creates_tamil_family_with_name_collision():
    fid = _seed()
    with session_scope() as s:
        fam = s.get(m.Family, fid)
        assert fam.heritage_lang == "ta"
        people = s.scalars(select(m.Person).where(m.Person.family_id == fid)).all()
        assert len(people) >= 12
        ravis = [p for p in people if p.display_name == "Ravi"]
        assert len(ravis) == 2, "the Ravi problem needs two Ravis"
        slugs = {p.slug for p in people}
        assert {"p_arjun", "p_kamala", "p_ravi_mama", "p_ravi_periyappa"} <= slugs

def test_seed_things_and_events_and_terms():
    fid = _seed()
    with session_scope() as s:
        kinds = dict(s.execute(select(m.Thing.kind, func.count()).where(m.Thing.family_id == fid).group_by(m.Thing.kind)).all())
        assert kinds["dish"] >= 6 and kinds["place"] >= 4 and kinds["event"] >= 3
        terms = s.scalars(select(m.KinTerm).where(m.KinTerm.lang == "ta")).all()
        assert len(terms) >= 20

def test_seed_is_idempotent():
    fid = _seed()
    with session_scope() as s:
        fam2 = seed_demo_family(s)
        assert fam2.id == fid
        assert s.scalar(select(func.count()).select_from(m.Person).where(m.Person.family_id == fid)) >= 12

def test_aliases_cover_tamil_script_and_roman_forms():
    fid = _seed()
    with session_scope() as s:
        ravi = s.scalar(select(m.Person).where(m.Person.slug == "p_ravi_mama"))
        aliases = {a.alias for a in ravi.aliases}
        assert "ரவி" in aliases and "ravi" in {a.lower() for a in aliases}

def test_edges_make_ravi_mama_priyas_brother_and_ravi_periyappa_senthils_brother():
    fid = _seed()
    with session_scope() as s:
        by = {p.slug: p for p in s.scalars(select(m.Person).where(m.Person.family_id == fid))}
        edges = s.scalars(select(m.Edge).where(m.Edge.family_id == fid)).all()
        sib = {(e.src_person, e.dst_person) for e in edges if e.relation == "sibling"}
        assert (by["p_priya"].id, by["p_ravi_mama"].id) in sib or (by["p_ravi_mama"].id, by["p_priya"].id) in sib
        assert (by["p_ravi_periyappa"].id, by["p_senthil"].id) in sib or (by["p_senthil"].id, by["p_ravi_periyappa"].id) in sib
