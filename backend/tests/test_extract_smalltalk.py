"""Remarks about the call or the app, and bare reactions, are not facts about anyone's life. Offline."""
from app.world import extract as ex
from app.world.contracts import WorldUpdateOut


def _fact(text, line):
    return {"subject": "speaker", "predicate": "attribute", "text_en": text, "text_src": "", "keys": [], "refs": [],
            "lines": [line], "sensitive_kind": "", "same_as": None, "contradicts": None, "storyline": None}


def test_prompt_states_the_life_facts_only_rule():
    system, _ = ex.build_prompt([ex.Line(1, 5, "en", "hi")], [ex.Participant(5, "p_mei_5", "Mei", "en")], {}, {}, ["en"])
    assert "Never a fact: remarks about this call, the app or" in system and "at most 3 per speaker" in system
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


def test_meta_mention_lines_are_dropped_but_news_mentions_are_kept():
    assert ex.is_smalltalk("Mentions Jev") and ex.is_smalltalk("talked about the resize task")
    assert not ex.is_smalltalk("Mentioned that she got the internship at Google in Seattle")


def test_news_is_capped_per_speaker_but_storylines_are_kept():
    lines = [ex.Line(n, 5, "en", f"line {n}") for n in range(1, 7)]
    ctx = ex.validate_ctx(lines, [ex.Participant(5, "p_mei_5", "Mei", "en")], {}, {})
    news = [_fact(t, n) for n, t in enumerate(("did an online competition with two CMU students", "started bouldering",
                                               "moved to a new apartment", "is learning Korean"), 1)]
    story = {**_fact("applied to ByteDance", 5),
             "storyline": {"existing_id": None, "title": "job search", "state_label": "applied", "resolved": False}}
    upd = WorldUpdateOut.model_validate({"entities": [], "ties": [], "facts": news + [story]})
    clean, dropped = ex.validate(upd, ctx)
    kept = [f.text_en for f in clean.facts]
    assert kept[:3] == [f["text_en"] for f in news[:3]] and "is learning Korean" not in kept
    assert "applied to ByteDance" in kept and any("news cap" in d for d in dropped)
