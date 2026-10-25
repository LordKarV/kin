"""LLM client: all calls go through app.llm; request shape matches Meta Model API structured output."""
import json
import httpx
import pytest
from pydantic import BaseModel

from app import llm


class Address(BaseModel):
    street: str
    city: str


def _fake_server(handler):
    """Return an httpx transport that records requests and replies with handler(request)."""
    seen = []

    def _h(request: httpx.Request):
        seen.append(request)
        return handler(request, len(seen))

    return httpx.MockTransport(_h), seen


def _chat_reply(content: str, status=200):
    body = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return httpx.Response(status, json=body)


def test_structured_completion_sends_json_schema_and_parses():
    transport, seen = _fake_server(lambda r, n: _chat_reply(json.dumps({"street": "1 Hacker Wy", "city": "Menlo Park"})))
    client = llm.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="muse-spark-1.3", transport=transport)

    out = client.structured(Address, system="extract", user="1 Hacker Wy Menlo Park")

    assert out == Address(street="1 Hacker Wy", city="Menlo Park")
    req = seen[0]
    assert str(req.url) == "https://api.meta.ai/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer k"
    body = json.loads(req.content)
    assert body["model"] == "muse-spark-1.3"
    rf = body["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    schema = rf["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"street", "city"}
    assert body["messages"][0]["role"] == "developer"
    assert "stop" not in body and "n" not in body
    assert body["prompt_cache_key"] == "kin"


def test_structured_completion_falls_back_to_backup_key_on_429():
    def handler(request, n):
        if request.headers["authorization"] == "Bearer primary":
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return _chat_reply(json.dumps({"street": "s", "city": "c"}))

    transport, seen = _fake_server(handler)
    client = llm.LLM(api_key="primary", backup_api_key="backup", base_url="https://api.meta.ai/v1",
                     model="muse-spark-1.3", transport=transport)

    out = client.structured(Address, system="x", user="y")

    assert out.city == "c"
    assert [r.headers["authorization"] for r in seen] == ["Bearer primary", "Bearer backup"]


def test_structured_completion_raises_on_invalid_json_not_silently():
    transport, _ = _fake_server(lambda r, n: _chat_reply("not json"))
    client = llm.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=transport)
    with pytest.raises(llm.StructuredOutputError):
        client.structured(Address, system="x", user="y")


def test_invalid_output_logs_where_it_broke_but_the_raw_text_only_at_debug(caplog):
    transport, _ = _fake_server(lambda r, n: _chat_reply(json.dumps({"street": "my therapist visit"})))
    client = llm.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=transport)
    with caplog.at_level("DEBUG", logger="kin.llm"), pytest.raises(llm.StructuredOutputError) as err:
        client.structured(Address, system="x", user="y")
    assert "therapist" not in str(err.value) and "city" in str(err.value)
    loud = " ".join(r.getMessage() for r in caplog.records if r.levelname != "DEBUG")
    quiet = " ".join(r.getMessage() for r in caplog.records if r.levelname == "DEBUG")
    assert "city: Field required" in loud and "therapist" not in loud and "therapist" in quiet
