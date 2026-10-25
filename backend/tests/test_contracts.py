"""Wire contracts (ARCHITECTURE.md 9.1/9.2), strict LLM schemas, the LiveWorld stub and the stub routers."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.llm import to_strict_schema
from app.main import app
from app.world import contracts as c
from app.world.live import FinalResult, LiveWorld

GLANCE_ITEM = {
    "key": "who:p_lin_17", "kind": "who", "title": "Lin", "native": "林",
    "body": "Mei's friend from the Fudan climbing wall, first mentioned Sep 14",
    "category": "person", "image_url": "", "image_credit": "", "source_url": "",
    "node_id": "p_lin_17", "gap": "new",
    "term": "Lin", "guess": "Lin", "suggestions": [{"owner": "p_mei_5", "relation": "friend", "label": "Mei's friend"}],
    "target": "p_mei_5", "private": True,
    "storyline_id": 3, "states": [{"label": "applied", "at": "2026-09-02", "known": True},
                                  {"label": "second round", "at": "2026-10-10", "known": False}],
}

# 9.1, verbatim except the `items:[GlanceItem]` placeholder and the `ok|unavailable|ended` / `mt|tts|pipeline` alternations.
MESSAGES = [
    {"type": "joined", "call_id": 12, "identity": "p3", "person": "p_arjun_3", "name": "Arjun", "lang": "en", "role": "participant",
     "peer_present": True, "participants": [{"identity": "p5", "person": "p_mei_5", "name": "Mei", "lang": "zh"}],
     "kin": {"on": True, "paused_by": None}},
    {"type": "participants", "participants": [{"identity": "p5", "person": "p_mei_5", "name": "Mei", "lang": "zh"}]},
    {"type": "kin_status", "on": False, "paused_by": {"person": "p_priya_4", "name": "Priya"}},
    {"type": "partial", "speaker": "p5", "person": "p_mei_5", "role": "participant", "lang": "zh", "text": "我和林去"},
    {"type": "glance", "speaker": "p5", "role": "participant", "partial": True, "items": [GLANCE_ITEM]},
    {"type": "glance_retract", "keys": ["who:p_lin_17"]},
    {"type": "glance_update", "key": "who:p_lin_17", "body": "梅在复旦攀岩墙认识的朋友"},
    {"type": "transcript", "call_id": 12, "utterance_id": 91, "speaker": "p_mei_5", "speaker_identity": "p5", "role": "participant",
     "listener": "p_arjun_3", "src_text": "我和林去攀岩了", "src_lang": "zh", "src_lang_tags": [], "target_lang": "en", "heritage_lang": "zh",
     "translation": "I went climbing with Lin.",
     "grounded_spans": [{"source": "林", "rendered": "Mei's friend Lin (from the Fudan climbing wall)", "node_id": "p_lin_17"}],
     "pragmatics_cards": [], "passthrough": [], "confidence": 0.9,
     "linker_spans": [{"start": 2, "end": 3, "source": "林", "node_id": "p_lin_17", "type": "person", "confidence": 0.95,
                       "rendered": "...", "candidates": [], "method": "alias"}],
     "latencies": {"scan_ms": 0.4, "a_ms": 1850, "mt_ms": 1862}, "error": None},
    {"type": "enrich", "utterance_id": 91, "pragmatics_cards": [], "b_ms": 2100},
    {"type": "audio_start", "utterance_id": 91, "lang": "en"},
    {"type": "audio_end", "utterance_id": 91},
    {"type": "latency", "utterance_id": 91, "latencies": {"tts_first_byte_ms": 310, "cards_ms": 1.2, "total_ms": 2400}},
    {"type": "status", "asr": "ok", "detail": ""},
    {"type": "error", "stage": "mt", "message": ""},
]

SERVER = TypeAdapter(c.ServerMsg)


@pytest.mark.parametrize("msg", MESSAGES, ids=[m["type"] for m in MESSAGES])
def test_server_message_examples_validate_and_round_trip(msg):
    parsed = SERVER.validate_python(msg)
    assert parsed.type == msg["type"]
    assert SERVER.dump_python(parsed, mode="json") == msg


def test_glance_item_minimal_gets_defaults():
    it = c.GlanceItem(key="bridge:7", kind="bridge")
    assert (it.title, it.node_id, it.gap, it.suggestions, it.private, it.states) == ("", None, None, [], False, [])


def test_same_language_transcript_has_null_translation():
    t = c.TranscriptMsg(call_id=1, utterance_id=2, speaker="p_priya_4", speaker_identity="p4", src_text="hi",
                        src_lang="en", target_lang="en")
    assert t.translation is None and t.model_dump()["type"] == "transcript"


REST = [
    (c.UserIn, {"name": "Arjun", "lang": "en", "phone": "+15125550101"}),
    (c.UserOut, {"user_id": 1, "person_id": 3, "person": "p_arjun_3", "space_id": 2, "token": "t", "sms_number": "+15125550000"}),
    (c.MeOut, {"user_id": 1, "person_id": 3, "person": "p_arjun_3", "name": "Arjun", "lang": "en", "phone": None}),
    (c.MePatch, {"lang": "ta"}),
    (c.DeleteMeOut, {"deleted": True, "facts": 4, "utterances": 9}),
    (c.ContactOut, {"person": "p_mei_5", "name": "Mei", "lang": "zh", "render": "your friend Mei", "circle": "friends"}),
    (c.WorldOut, {"me": "p_arjun_3",
                  "people": [{"id": 5, "person": "p_mei_5", "name": "Mei", "render": "your friend Mei", "lang": "zh", "is_user": True, "circle": "friends"}],
                  "ties": [{"src": "p_mei_5", "dst": "p_lin_17", "kind": "friend", "context": "from the Fudan climbing wall"}],
                  "edges": [{"src": "p_arjun_3", "dst": "p_kamala_1", "relation": "child_of"}],
                  "groups": [{"id": 1, "name": "Fudan crew", "members": ["p_mei_5"]}],
                  "things": [{"id": 4, "slug": "pl_fudan_4", "kind": "place", "name": "Fudan", "owner": "p_mei_5"}],
                  "storylines": [{"id": 3, "title": "job search", "status": "open", "states": [{"label": "applied", "at": "2026-09-02"}]}]}),
    (c.RelationsOut, {"social": [{"kind": "friend", "label": "friend"}], "kin": [{"path": "mother.brother", "label": "uncle"}]}),
    (c.PlaceIn, {"name": "Lin", "owner": "p_mei_5", "relation": "friend", "context": "climbing", "call_id": 12}),
    (c.PlaceOut, {"id": 17, "person": "p_lin_17", "name": "Lin", "render": "Mei's friend Lin"}),
    (c.FactsOut, {"about_me": [{"id": 1, "text": "started bouldering", "subject": "p_arjun_3", "speaker": "p_arjun_3",
                                "source_kind": "message", "said_at": "2026-10-01T10:00:00Z", "status": "active",
                                "sensitive_kind": "", "pinned": False, "expires_at": None,
                                "heard_by": [{"person": "p_priya_4", "name": "Priya", "via": "told"}]}], "i_said": []}),
    (c.FactPatch, {"pinned": True}),
    (c.DeletePersonOut, {"deleted_facts": 2, "person_deleted": True}),
    (c.PauseIn, {"paused": True}),
    (c.PauseOut, {"on": False, "paused_by": {"person": "p_priya_4", "name": "Priya"}}),
    (c.FeedbackIn, {"key": "who:p_lin_17", "action": "know"}),
    (c.TextIn, {"text": "我和林去攀岩了"}),
    (c.CallParticipantOut, {"person": "p_mei_5", "identity": "p5", "lang": "zh", "joined_at": "2026-10-24T10:00:00Z", "left_at": None}),
    (c.RtcJoinWorldIn, {}),
    (c.JoinWorldOut, {"call_id": 12, "room": "kin-12", "token": "jwt", "url": "ws://localhost:7880", "identity": "p3",
                      "person": "p_arjun_3", "name": "Arjun", "lang": "en",
                      "participants": [{"identity": "p5", "person": "p_mei_5", "name": "Mei", "lang": "zh"}]}),
    (c.DevSmsIn, {"from": "+15125550101", "body": "started bouldering"}),
    (c.DevSmsOut, {"reply": "Nice, bouldering!", "message_id": 1, "facts": [{"id": 1, "text": "started bouldering"}]}),
    (c.ClockIn, {"offset_days": 42}),
    (c.ClockOut, {"now": "2026-12-05T10:00:00Z"}),
    (c.DevApplyIn, {"speaker": "p_mei_5", "audience": ["p_arjun_3"],
                    "update": {"entities": [], "ties": [], "facts": []}}),
    (c.DevApplyOut, {"facts": [1], "entities": [{"ref": "e1", "id": 17, "slug": "p_lin_17"}]}),
]


@pytest.mark.parametrize("model,body", REST, ids=[m.__name__ for m, _ in REST])
def test_rest_bodies_validate(model, body):
    model.model_validate(body)


def test_dev_sms_from_alias():
    assert c.DevSmsIn.model_validate({"from": "+1", "body": "x"}).from_ == "+1"
    assert len(c.DevSmsIn.model_validate({"from": "+1", "body": "x" * 2000}).body) == 1600


def test_fact_ids_never_reach_clients():
    assert "fact_ids" not in c.GlanceItem.model_fields
    assert "fact_ids" not in c.GlanceItem.model_validate({"key": "bridge:7", "kind": "bridge", "fact_ids": [1]}).model_dump()


def test_bad_feedback_action_rejected():
    with pytest.raises(ValueError):
        c.FeedbackIn.model_validate({"key": "k", "action": "spam"})


def _closed(node):
    if isinstance(node, dict):
        if "properties" in node:
            assert node["additionalProperties"] is False and set(node["required"]) == set(node["properties"])
        assert "default" not in node
        for v in node.values():
            _closed(v)
    elif isinstance(node, list):
        for v in node:
            _closed(v)


@pytest.mark.parametrize("model", [c.WorldUpdateOut, c.SmsOut, c.FormsOut, c.LocalizeOut, c.NewPerson, c.BridgeOut])
def test_llm_schemas_are_strict(model):
    raw = model.model_json_schema()
    # to_strict_schema strips defaults itself, so check the raw schema: a default would let a reply omit the key.
    for node in [raw, *raw.get("$defs", {}).values()]:
        assert set(node.get("required", [])) == set(node["properties"]), node.get("title")
        assert all("default" not in prop for prop in node["properties"].values()), node.get("title")
    schema = to_strict_schema(raw)
    _closed(schema)
    assert "description" not in schema  # no docstring leaks into the prompt schema


def test_world_update_example_validates():
    c.WorldUpdateOut.model_validate({
        "entities": [{"ref": "e1", "name": "Lin", "native": "林", "forms": ["林", "Lin", "Lynn"], "kind": "person", "existing_id": None}],
        "ties": [{"a": "speaker", "b": "e1", "kind": "friend", "context": "from the Fudan climbing wall"}],
        "facts": [{"subject": "e1", "predicate": "tie", "text_en": "Lin is Mei's friend", "text_src": "", "keys": [["climbing", "攀岩"]],
                   "refs": ["e1"], "lines": [0], "sensitive_kind": "", "same_as": None, "contradicts": None,
                   "storyline": {"existing_id": None, "title": "climbing", "state_label": "started", "resolved": False}}],
    })


def test_health_with_stub_routers_mounted():
    from app.api import dev, sms, users, world

    assert (users.router.prefix, world.router.prefix, dev.router.prefix, sms.router.prefix) == ("/api", "/api", "/api/dev", "")
    mounted = {id(getattr(r, "original_router", None)) for r in app.routes}
    assert all(id(m.router) in mounted for m in (users, world, dev, sms))
    with TestClient(app) as cl:
        assert cl.get("/health").status_code == 200


def test_live_world_stub_returns_documented_empties():
    async def emit(identity: str, msg: dict) -> None:
        return None

    loop = asyncio.new_event_loop()
    try:
        w = LiveWorld(1, 2, emit, loop)
        assert w.join("p3", 3, "en") is None
        assert w.on_partial("p3", "hi") == {}
        assert w.on_final("p3", "hi") == FinalResult({}, [])
        assert w.on_translated("p3", 1, "hi", {"zh": "你好"}, [5]) == {}
        assert w.asks("p3", ["p5"], []) == {}
        assert w.render("p5", "p_lin_17") is None
        assert w.roster(["p5"], "p3") == ""
        assert w.keyterms("p3") == []
        with pytest.raises(NotImplementedError):
            w.translator("zh")
        for call in (lambda: w.leave("p3"), lambda: w.feedback("p5", "who:x", "know"), w.refresh, w.close):
            assert call() is None
    finally:
        loop.close()
