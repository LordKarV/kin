"""Grounded translation: prompt carries the family context + linked entities; output validated; generic baseline has none."""
import json
import httpx

from app import llm as llm_mod
from app.graph.linker import Linker
from app.mt.schemas import TranslationOut
from app.mt.translate import Translator
from tests.graph_fixtures import graph  # noqa: F401


def _llm_with(reply: dict, seen: list):
    def handler(req: httpx.Request):
        seen.append(json.loads(req.content))
        body = {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(reply)}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        return httpx.Response(200, json=body)
    return llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))


GOOD = {"translation": "Your uncle Ravi mama called yesterday.",
        "grounded_spans": [{"source": "மாமா", "rendered": "your uncle Ravi mama (Mom's younger brother)", "node_id": "p_ravi_mama"}],
        "pragmatics_cards": [], "passthrough_kept": [], "confidence": 0.9}


def test_grounded_prompt_contains_roster_rule_and_linked_entities(graph):
    seen = []
    tr = Translator(graph, _llm_with(GOOD, seen))
    out = tr.translate("உன் மாமா நேத்து போன் பண்ணான்.", speaker="p_kamala", listener="p_arjun")
    assert isinstance(out.result, TranslationOut)
    assert out.result.grounded_spans[0].node_id == "p_ravi_mama"
    req = seen[0]
    system = req["messages"][0]["content"]
    assert "never flatten" in system.lower() or "never render" in system.lower()
    assert "Ravi" in system and "Dad's elder brother" in system  # roster (cached prefix) includes both Ravis
    user = req["messages"][-1]["content"]
    assert "p_ravi_mama" in user and "Mom's younger brother" in user  # linked entity for this utterance
    assert req["response_format"]["json_schema"]["strict"] is True
    assert out.latencies["link_ms"] >= 0 and out.latencies["mt_ms"] >= 0


def test_generic_baseline_has_no_family_context(graph):
    seen = []
    tr = Translator(graph, _llm_with({"translation": "Your uncle called yesterday.", "grounded_spans": [], "pragmatics_cards": [], "passthrough_kept": [], "confidence": 0.8}, seen))
    tr.translate_generic("உன் மாமா நேத்து போன் பண்ணான்.")
    joined = " ".join(m["content"] for m in seen[0]["messages"])
    assert "Ravi" not in joined and "Krishnan" not in joined


def test_passthrough_tokens_are_instructed_and_never_inside_grounded_span(graph):
    seen = []
    tr = Translator(graph, _llm_with(GOOD, seen))
    out = tr.translate("உன் மாமா நேத்து போன் பண்ணான்.", speaker="p_kamala", listener="p_arjun", passthrough=["நேத்து", "மாமா"])
    user = seen[0]["messages"][-1]["content"]
    assert "நேத்து" in user
    assert "மாமா" not in out.passthrough  # guardrail: inside a grounded entity span


def test_history_is_included_as_recent_context(graph):
    seen = []
    tr = Translator(graph, _llm_with(GOOD, seen))
    tr.translate("ரவி ஹால் புக் பண்ணிட்டாரு.", speaker="p_kamala", listener="p_arjun", history=[("p_kamala", "Vishnu-vukku kalyaanam adutha varusham.", "Vishnu's wedding is next year.")])
    user = seen[0]["messages"][-1]["content"]
    assert "Vishnu-vukku kalyaanam" in user


def test_invalid_model_output_surfaces_fallback_not_crash(graph):
    def handler(req):
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "oops"}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    tr = Translator(graph, llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler)))
    out = tr.translate("உன் மாமா நேத்து போன் பண்ணான்.", speaker="p_kamala", listener="p_arjun")
    assert out.error and out.result.translation  # linker-only fallback rendering
    assert "Ravi" in out.result.translation
