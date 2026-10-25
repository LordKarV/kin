"""Remarks about the call or the app, and bare reactions, are not facts about anyone's life. Offline."""
from app.world import extract as ex
from app.world.contracts import WorldUpdateOut


def _fact(text, line):
    return {"subject": "speaker", "predicate": "attribute", "text_en": text, "text_src": "", "keys": [], "refs": [],
            "lines": [line], "sensitive_kind": "", "same_as": None, "contradicts": None, "storyline": None}


def test_prompt_states_the_life_facts_only_rule():
    system, _ = ex.build_prompt([ex.Line(1, 5, "en", "hi")], [ex.Participant(5, "p_mei_5", "Mei", "en")], {}, {}, ["en"])
    assert "Never a fact: remarks about this call, the app or the connection" in system
    assert '"the UI is fire"' in system and '"I started bouldering"' in system


def test_validate_drops_call_remarks_and_keeps_news():
    lines = [ex.Line(1, 5, "en", "The UI is fire"), ex.Line(2, 5, "en", "this call is lagging"),
             ex.Line(3, 5, "en", "haha nice"), ex.Line(4, 5, "en", "I started bouldering at the campus gym")]
    ctx = ex.validate_ctx(lines, [ex.Participant(5, "p_mei_5", "Mei", "en")], {}, {})
    upd = WorldUpdateOut.model_validate({"entities": [], "ties": [], "facts": [
        _fact("The UI is fire", 1), _fact("this call is lagging", 2), _fact("haha nice", 3),
        _fact("started bouldering at the campus gym", 4)]})
    clean, dropped = ex.validate(upd, ctx)
    assert [f.text_en for f in clean.facts] == ["started bouldering at the campus gym"]
    assert len(dropped) == 3 and all("small talk" in d for d in dropped)


def test_news_that_mentions_an_app_or_a_call_is_kept():
    for text in ("my sister moved to Austin", "has an interview at Meta next week", "launched the app",
                 "got the call from Google", "has a call with a recruiter", "missed the connection in Denver"):
        assert not ex.is_smalltalk(text), text
