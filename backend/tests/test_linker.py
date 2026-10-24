import json
from pathlib import Path

from app.graph.linker import Linker
from eval.schemas import GroundingItem
from tests.graph_fixtures import graph  # noqa: F401

TS = Path(__file__).resolve().parents[1] / "eval" / "testset" / "kinship_names_dishes.jsonl"


def _link(graph, text, ctx=()):
    return Linker(graph).link(text, speaker="p_kamala", listener="p_arjun", context=list(ctx))


def _nodes(spans):
    return {s.node for s in spans if s.node}


def test_bare_kin_term_resolves_to_listener_relative_person(graph):
    spans = _link(graph, "உன் மாமா நேத்து போன் பண்ணான்.")
    assert _nodes(spans) == {"p_ravi_mama"}
    s = spans[0]
    assert s.source == "மாமா" and s.display == "your uncle Ravi mama (Mom's younger brother)"


def test_name_plus_kin_term_merges_into_one_span(graph):
    spans = _link(graph, "ரவி மாமா உனக்கு ஃபோன் பண்ணினானா?")
    assert [(s.source, s.node) for s in spans] == [("ரவி மாமா", "p_ravi_mama")]


def test_name_collision_disambiguated_by_place_cue(graph):
    assert "p_ravi_mama" in _nodes(_link(graph, "ரவி நேத்து அடையாறுலேர்ந்து போன் பண்ணான்."))
    assert "p_ravi_periyappa" in _nodes(_link(graph, "ரவி கோவையில புது கடை திறந்திருக்காரு."))


def test_name_collision_disambiguated_by_co_mention(graph):
    assert "p_ravi_mama" in _nodes(_link(graph, "ரவியும் லட்சுமியும் பொங்கலுக்கு வர்றாங்க."))
    assert "p_ravi_periyappa" in _nodes(_link(graph, "ரவியோட பையன் விஷ்ணுவுக்கு கல்யாணம் நிச்சயம் ஆச்சு."))


def test_name_collision_uses_context_salience(graph):
    assert "p_ravi_periyappa" in _nodes(_link(graph, "ரவி ஹால் புக் பண்ணிட்டாரு.", ctx=["Vishnu-vukku kalyaanam adutha varusham."]))
    assert "p_ravi_mama" in _nodes(_link(graph, "ரவி உனக்கு புது லேப்டாப் வாங்கி தரேன்னு சொன்னான்.", ctx=["Un mama nethu phone pannaan."]))


def test_bare_ravi_defaults_to_speakers_son(graph):
    spans = _link(graph, "ரவி இன்னும் என்கிட்ட சின்ன பையன் மாதிரி தான் பேசுவான்.")
    ravi = [s for s in spans if s.source.startswith("ரவி")][0]
    assert ravi.node == "p_ravi_mama" and set(ravi.candidates) == {"p_ravi_mama", "p_ravi_periyappa"}


def test_speaker_perspective_possessive(graph):
    assert _nodes(_link(graph, "என் மகன் இந்த வாரம் மதுரைக்கு வர்றான்.")) == {"p_ravi_mama", "pl_madurai_house"}


def test_compositional_kin_chain(graph):
    assert "p_ravi_mama" in _nodes(_link(graph, "உன் அம்மாவோட தம்பிக்கு பேங்க்ல ப்ரமோஷன்."))
    assert "p_karthik" in _nodes(_link(graph, "மாமா பையன் கிரிக்கெட் மேட்ச்ல செஞ்சுரி அடிச்சான்."))


def test_things_resolve_with_family_meaning(graph):
    spans = _link(graph, "ஊருக்கு எப்போ வர்ற?")
    assert _nodes(spans) == {"pl_madurai_house"}
    assert _nodes(_link(graph, "கோவிலுக்கு வெள்ளிக்கிழமை போயிட்டு வந்தேன்.")) == {"pl_meenakshi_kovil"}


def test_romanized_input_also_links(graph):
    assert "p_ravi_mama" in _nodes(_link(graph, "Un mama nethu phone pannaan."))
    assert "d_rasam" in _nodes(_link(graph, "Innaikku rasam vachen."))


def test_generic_kin_address_is_not_linked_to_family(graph):
    spans = _link(graph, "காய்கறிக்கடை அக்கா உன்னை விசாரிச்சா.")
    assert "p_divya" not in _nodes(spans)


def test_kin_terms_inside_proverb_are_not_linked(graph):
    spans = _link(graph, "அடி உதவுற மாதிரி அண்ணன் தம்பி உதவ மாட்டான்.")
    assert not _nodes(spans) & {"p_vishnu", "p_karthik", "p_divya"}


def test_linker_accuracy_on_phase1_testset(graph):
    items = [GroundingItem.model_validate(json.loads(l)) for l in TS.read_text(encoding="utf-8").splitlines() if l.strip()]
    linker = Linker(graph)
    hit = total = 0
    misses = []
    for it in items:
        spans = linker.link(it.src_text, speaker=it.speaker, listener=it.listener, context=it.context)
        found = _nodes(spans)
        for e in it.entities:
            total += 1
            if e.node in found:
                hit += 1
            else:
                misses.append((it.id, e.source, e.node, sorted(found)))
    acc = hit / total
    assert acc >= 0.90, f"linker accuracy {acc:.2%}; misses: {misses[:15]}"


# ---- review fix pass: romanized false positives (reviewer finding 2) ----
def test_romanized_verbs_and_common_words_are_not_people(graph):
    for text in ["Un mama nethu phone pannaan.", "Pappa phone pannaa", "naan oru dosa senjen", "appam saapdu", "Divya vandhaa"]:
        spans = _link(graph, text)
        people = {s.node for s in spans if s.type == "person" and s.node}
        assert "p_vishnu" not in people and "p_senthil" not in people, (text, people)
        assert "pl_madurai_house" not in _nodes(spans), text
    assert _nodes(_link(graph, "Pappa phone pannaa")) == {"p_priya"}
    assert _nodes(_link(graph, "Divya vandhaa")) == {"p_divya"}
    assert _nodes(_link(graph, "Oorukku eppo varra?")) == {"pl_madurai_house"}


def test_romanized_testset_has_few_person_false_positives(graph):
    items = [GroundingItem.model_validate(json.loads(l)) for l in TS.read_text(encoding="utf-8").splitlines() if l.strip()]
    linker = Linker(graph)
    fp = hit = total = 0
    bad = []
    for it in items:
        expected = {e.node for e in it.entities}
        spans = linker.link(it.src_roman, speaker=it.speaker, listener=it.listener, context=it.context)
        found = {s.node for s in spans if s.node}
        for e in it.entities:
            total += 1; hit += e.node in found
        # a chain head ("mama" in "mama paiyan") is a correct extra resolution, not a false positive
        wrong = {s.node for s in spans if s.type == "person" and s.node and s.node not in expected and s.method != "chain-head"}
        if wrong:
            fp += 1; bad.append((it.id, sorted(wrong)))
    assert hit / total >= 0.80, f"romanized recall {hit/total:.0%}"
    assert fp / len(items) <= 0.05, f"person false positives in {fp}/{len(items)} items: {bad[:10]}"
