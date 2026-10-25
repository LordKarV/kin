"""Validator (ARCHITECTURE 6.2): each speaker may only link the entities their own prompt section offered."""
import logging

from app.world import extract as ex
from app.world.contracts import WorldUpdateOut

MEI, ARJUN, JESS, CAFE = 1, 2, 50, 60


def _ctx(mei_cands=(), arjun_cands=(ex.Candidate("person", JESS, "p_jess_50", "Jess", False),)):
    window = [ex.Line(1, MEI, "zh", "我和Jess去爬山了"), ex.Line(2, ARJUN, "en", "Jess moved to Austin")]
    parts = [ex.Participant(MEI, "p_mei_1", "Mei", "zh"), ex.Participant(ARJUN, "p_arjun_2", "Arjun", "en")]
    return ex.validate_ctx(window, parts, {}, {MEI: list(mei_cands), ARJUN: list(arjun_cands)})


def _fact(line, refs=("e1",), text="went hiking with Jess", subject="speaker"):
    return {"subject": subject, "predicate": "did", "text_en": text, "text_src": "", "keys": [], "refs": list(refs),
            "lines": [line], "sensitive_kind": "", "same_as": None, "contradicts": None, "storyline": None}


def _upd(facts, existing=JESS):
    jess = {"ref": "e1", "name": "Jess", "native": "", "forms": ["Jess"], "kind": "person", "existing_id": existing}
    return WorldUpdateOut.model_validate({"entities": [jess], "ties": [], "facts": facts})


def test_a_speaker_cannot_link_another_speakers_known_entity():
    clean, dropped = ex.validate(_upd([_fact(1)]), _ctx())
    assert clean.facts == [] and clean.entities == []
    assert "refs not offered to speaker 1" in dropped[0] and "not offered to every speaker" in dropped[1]


def test_the_speaker_it_was_offered_to_can_link_it():
    clean, dropped = ex.validate(_upd([_fact(2, text="moved to Austin", subject="e1", refs=())]), _ctx())
    assert dropped == [] and [e.existing_id for e in clean.entities] == [JESS] and len(clean.facts) == 1


def test_a_slug_from_another_speakers_list_is_refused_too():
    clean, dropped = ex.validate(_upd([_fact(1, refs=("p_jess_50",))], existing=None), _ctx())
    assert clean.facts == [] and "refs not offered" in dropped[0]


def test_participants_and_shared_entities_stay_linkable():
    cafe = ex.Candidate("thing", CAFE, "th_cafe_60", "Cafe", False)
    ctx = _ctx(mei_cands=(cafe,), arjun_cands=(cafe,))
    upd = WorldUpdateOut.model_validate({"entities": [{"ref": "e1", "name": "Cafe", "native": "", "forms": [],
                                                       "kind": "place", "existing_id": CAFE}], "ties": [],
                                         "facts": [_fact(1, refs=("p_arjun_2",), text="had tea with Arjun")]})
    clean, dropped = ex.validate(upd, ctx)
    assert dropped == [] and len(clean.facts) == 1 and len(clean.entities) == 1  # uncited, offered to both


def test_dropped_facts_are_logged_without_their_text(caplog):
    with caplog.at_level(logging.INFO, logger="kin.world.extract"):
        _clean, dropped = ex.validate(_upd([_fact(1, text="started seeing a therapist")]), _ctx())
    assert dropped and "therapist" not in " ".join(dropped) and "therapist" not in caplog.text
    assert "fact #0" in dropped[0]
