"""Long-history padding (eval/long_history.py): deterministic, schema-valid, collision-free, and harmless to KIN."""
import os

import pytest

import eval.run_cg as cg
from app import config
from app import llm as llm_mod
from app.world.match import AliasIndex
from eval.common_ground.schemas import Scenario, load_scenarios
from eval.long_history import DX, PAD, pad
from eval.run_cg import KIN_EXIT

# one 2-user zh/en, one 3-user with a bridge, one Tamil, one near-name trap (two Lins), one storyline
IDS = ("heard_42_days", "lin_six_weeks", "murukku_term_card", "two_lins_ambiguous", "storyline_behind")


@pytest.fixture
def in_process(monkeypatch):
    """As in test_cg_eval: env and the blocked LLM.structured for an in-process run_set, restored on teardown."""
    for k in ("BRIDGE_RERANK", "SEED_DEMO_FAMILY", "MODEL_API_KEY", "DATABASE_URL"):
        monkeypatch.setenv(k, os.environ.get(k, ""))
    monkeypatch.setenv("BRIDGE_RERANK", "0")
    monkeypatch.setenv("SEED_DEMO_FAMILY", "0")
    monkeypatch.setattr(llm_mod.LLM, "structured", cg._blocked)
    config.get_settings.cache_clear()
    llm_mod.reset_llm()
    yield
    config.get_settings.cache_clear()
    llm_mod.reset_llm()


@pytest.fixture(scope="module")
def pairs():
    by_id = {s.id: s for s in load_scenarios()}
    return [(by_id[i], pad(by_id[i], 3)) for i in IDS if i in by_id]


def test_pad_is_deterministic_per_seed(pairs):
    sc, p = pairs[0]
    assert pad(sc, 3).model_dump() == p.model_dump()
    assert pad(sc, 3, seed=1).model_dump() != p.model_dump()
    assert pad(sc, 0) is sc


def test_padded_scenarios_validate_and_keep_the_scenario_intact(pairs):
    for sc, p in pairs:
        Scenario.model_validate(p.model_dump())
        assert p.expect == sc.expect and p.probe == sc.probe
        assert p.facts[-len(sc.facts):] == sc.facts if sc.facts else True
        assert p.evidence[len(p.evidence) - len(sc.evidence):] == sc.evidence  # filler evidence comes first
        filler = [f for f in p.facts if f.key.startswith(PAD)]
        assert len(filler) > 300 and max(f.day for f in filler) < min([0, *(f.day for f in sc.facts)])
        assert {x.key for x in sc.people} <= {x.key for x in p.people}
        assert any(f.key.startswith(DX) for f in filler) and any(x.key.startswith(DX + "near") for x in p.people)


def test_no_filler_collides_with_scenario_entities(pairs):
    for sc, p in pairs:
        forms = [f for x in sc.people for f in (x.name, *x.forms)] + [f for g in sc.groups for f in (g.name, *g.forms)]
        idx = AliasIndex((f, "x", 0) for f in forms)
        langs = {x.lang for x in sc.people} | {""}
        new = [x for x in p.people if x.key.startswith(PAD)]
        assert not {x.key for x in new} & {x.key for x in sc.people}
        for f in p.facts:
            if f.key.startswith(PAD):
                assert not any(idx.scan(f.text, lg) for lg in langs), (sc.id, f.text)
        fill = AliasIndex((f, "x", 0) for x in new for f in (x.name, *x.forms))
        probe = [sc.probe.text, *sc.probe.partials, *sc.probe.translations.values()]
        assert not any(fill.scan(t, lg) for t in probe for lg in langs), sc.id


def test_distractors_are_never_expected(pairs):
    for _sc, p in pairs:
        for ex in p.expect.values():
            for c in ex.cards:
                assert not c.key.startswith(PAD) and not any(k.startswith(PAD) for k in c.cites)


def test_kin_offline_on_padded_scenarios_matches_unpadded(in_process, tmp_path, pairs):
    base = [sc for sc, _ in pairs]
    plain = cg.run_set(base, tmp_path, None, "plain-")[0]
    padded = cg.run_set([p for _, p in pairs], tmp_path, None, "pad-")[0]
    assert all(padded.c[h] == 0 for h in KIN_EXIT), {h: padded.c[h] for h in KIN_EXIT}
    for cat in cg.CATS:
        for x in ("tp", "fp", "fn"):
            assert padded.c[f"{cat}_{x}"] == plain.c[f"{cat}_{x}"], (cat, x, padded.misses)
