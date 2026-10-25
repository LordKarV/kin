"""Task 1E: the planted common-ground scenarios load, validate, and cover every bucket of ARCHITECTURE 11."""
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.common_ground.schemas import Scenario, load_scenarios

ARCH = Path(__file__).resolve().parents[2] / "docs" / "ARCHITECTURE.md"

# One tag per bucket listed in ARCHITECTURE 11. "paused" is not here: pause is a live-call action, not planted state.
BUCKETS = [
    "never_heard", "heard_6_days", "heard_42_days", "heard_spaced", "said_yourself", "shown_yesterday",
    "asked_last_time", "tie_owner", "group_member", "co_participant", "cross_circle", "cross_circle_own_fact",
    "sensitive", "third_party_expired", "pinned", "same_language", "cjk_single_char", "latin_variants",
    "thai_unspaced", "ambiguous", "tamil_kin", "contradiction", "storyline_behind", "storyline_current",
    "bridge_irrelevant", "bridge_told", "bridge_rate_limit", "bridge_next_day", "sms_only", "non_self_fact",
]


@pytest.fixture(scope="module")
def scenarios():
    return load_scenarios()


def test_loads_at_least_30_unique(scenarios):
    assert len(scenarios) >= 30
    assert len({s.id for s in scenarios}) == len(scenarios)


def test_every_bucket_covered(scenarios):
    tags = {t for s in scenarios for t in s.tags}
    assert [b for b in BUCKETS if b not in tags] == []


def test_same_language_tag_is_true(scenarios):
    for s in scenarios:
        if "same_language" in s.tags:
            langs = {p.key: p.lang for p in s.people}
            assert all(langs[k] == langs[s.probe.speaker] for k in s.probe.participants), s.id


def test_cross_language_listeners_get_a_translation(scenarios):
    for s in scenarios:
        langs = {p.key: p.lang for p in s.people}
        need = {langs[k] for k in s.probe.participants} - {langs[s.probe.speaker]}
        assert need <= set(s.probe.translations), (s.id, need)


def test_first_scenario_is_the_doc_example():
    block = re.search(r'```jsonc\n(\{"id":"lin_six_weeks".*?)\n```', ARCH.read_text(encoding="utf-8"), re.S)
    assert block, "example not found in ARCHITECTURE 11"
    doc = json.loads(block.group(1))
    path = Path(__file__).resolve().parents[1] / "eval" / "common_ground" / "scenarios.jsonl"
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert first == doc


def _base() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "eval" / "common_ground" / "scenarios.jsonl")
                      .read_text(encoding="utf-8").splitlines()[0])


@pytest.mark.parametrize("mutate", [
    lambda d: d["ties"][0].update(heard_by=["nobody"]),                       # unknown person
    lambda d: d["probe"].update(speaker="lin"),                               # speaker not a participant
    lambda d: d["expect"].update(lin={"cards": []}),                          # expectation for a non-participant
    lambda d: d["expect"]["mei"]["cards"].append({"kind": "who", "key": "lin", "gap": "new"}),  # speaker card
    lambda d: d["expect"]["priya"]["cards"].append({"kind": "bridge", "key": "boulder"}),       # non-self bridge
    lambda d: d["expect"]["arjun"]["cards"].append({"kind": "who", "key": "ghost", "gap": "new"}),
    lambda d: d["evidence"].append({"knower": "arjun", "item": {"kind": "fact", "key": "nope"}, "ev": "heard", "day": 1}),
    lambda d: d["evidence"][0].update(day=50),                                # after the probe
    lambda d: d["facts"][0].update(speaker="priya"),                          # bridge on a fact someone else said
    lambda d: d["expect"]["arjun"]["cards"].append({"kind": "ask", "key": "Bob"}),  # ask term not in text
    lambda d: d["expect"]["arjun"]["cards"][0].pop("gap"),                    # who card without a gap
    lambda d: d["expect"]["arjun"]["cards"][1].update(gap="new"),             # gap on a bridge card
    lambda d: d["facts"][0].update(contradicts="x"),                          # contradicts an unknown fact
    lambda d: d["evidence"].append({"knower": "arjun", "item": {"kind": "bridge", "key": "boulder"},
                                    "ev": "shown", "day": 1}),               # bridge evidence without target
    lambda d: d["evidence"].append({"knower": "priya", "item": {"kind": "bridge", "key": "boulder"},
                                    "ev": "shown", "day": 1, "target": "mei"}),  # bridge shown to a non-owner
    lambda d: d["evidence"].append({"knower": "arjun", "item": {"kind": "bridge", "key": "boulder"},
                                    "ev": "shown", "day": 1, "target": "arjun"}),  # target already in audience
    lambda d: d["probe"]["participants"].append("lin") or d["expect"].update(lin={"cards": []}),  # non-user
    lambda d: d["facts"][0].update(day=43),                                   # fact after the probe
    lambda d: d["people"].append(dict(d["people"][0])),                       # duplicate key
    lambda d: d.update(bogus=1),                                              # unknown field
    lambda d: d["expect"]["arjun"]["cards"].append({"kind": "who", "key": "priya", "gap": "new"}),  # participant
    lambda d: d["probe"]["partials"].append("林去"),                           # partial not a prefix
])
def test_validator_rejects_bad_references(mutate):
    d = _base()
    mutate(d)
    with pytest.raises(ValidationError):
        Scenario.model_validate(d)
