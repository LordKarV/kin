"""Phase 1 acceptance: test files validate against the Pydantic schema and meet the plan's counts."""
import json
from collections import Counter
from pathlib import Path

from eval.schemas import GroundingItem, IdiomItem, stem_in

TS = Path(__file__).resolve().parents[1] / "eval" / "testset"

def _load(name, model):
    rows = [json.loads(l) for l in (TS / name).read_text(encoding="utf-8").splitlines() if l.strip()]
    return [model.model_validate(r) for r in rows]

def test_grounding_set_counts():
    items = _load("kinship_names_dishes.jsonl", GroundingItem)
    assert len(items) >= 100
    c = Counter(i.category for i in items)
    assert c["kin"] >= 40 and c["name_collision"] >= 30 and c["dish_place"] >= 30
    assert len({i.id for i in items}) == len(items)

def test_grounding_items_have_script_and_roman_and_entities():
    for i in _load("kinship_names_dishes.jsonl", GroundingItem):
        assert i.src_text and i.src_roman and i.entities, i.id
        for e in i.entities:
            assert stem_in(e.source, i.src_text) or e.source in i.src_roman, (i.id, e.source)
            assert e.must_include, (i.id, e.node)

def test_name_collision_items_reference_a_ravi():
    for i in _load("kinship_names_dishes.jsonl", GroundingItem):
        if i.category == "name_collision":
            assert any(e.node in ("p_ravi_mama", "p_ravi_periyappa") for e in i.entities), i.id

def test_idiom_set_counts():
    items = _load("idioms.jsonl", IdiomItem)
    pos = [i for i in items if i.expect_card]
    neg = [i for i in items if not i.expect_card]
    assert len(pos) >= 40 and len(neg) >= 40
    for i in pos:
        assert i.card and i.card.meaning and i.card.kind, i.id
