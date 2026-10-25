"""The only place that talks to the LLM.

OpenAI-compatible client pointed at Meta Model API (or anything else via env).
Structured outputs use Chat Completions `response_format={"type":"json_schema",...}` with strict=True,
which requires additionalProperties:false and every key listed in `required` (VERIFIED dev.meta.ai docs).
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Iterable, Type, TypeVar

import httpx
import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from .config import get_settings

log = logging.getLogger("kin.llm")
T = TypeVar("T", bound=BaseModel)

# Parameters Meta Model API rejects with HTTP 400 (never send them).
# Runs hedged requests; the losing request finishes in the background and is dropped (bounded by the client timeout).
_HEDGE_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="kin-llm-hedge")

_REJECTED = {"stop", "logit_bias", "prediction", "web_search_options", "modalities", "audio", "verbosity", "logprobs", "max_output_tokens"}


class StructuredOutputError(RuntimeError):
    """The model returned something that is not valid JSON for the requested schema."""


def to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a Pydantic JSON schema acceptable to strict mode: every object closed, every key required."""

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                props = node.get("properties", {})
                node["additionalProperties"] = False
                node["required"] = list(props.keys())
            for k, v in list(node.items()):
                if k == "default":
                    node.pop(k)  # strict mode rejects defaults on required keys
                else:
                    node[k] = walk(v)
            return node
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(json.loads(json.dumps(schema)))


class LLM:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        backup_api_key: str = "",
        reasoning_effort: str = "low",
        timeout_s: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._timeout = timeout_s
        http = httpx.Client(transport=transport) if transport else None
        self._clients = [OpenAI(api_key=api_key, base_url=base_url, http_client=http, timeout=timeout_s, max_retries=0)]
        if backup_api_key:
            self._clients.append(OpenAI(api_key=backup_api_key, base_url=base_url, http_client=http, timeout=timeout_s, max_retries=0))

    # -- public -------------------------------------------------------------

    def structured(
        self,
        schema_model: Type[T],
        system: str,
        user: str,
        history: Iterable[dict[str, str]] = (),
        reasoning_effort: str | None = None,
        max_completion_tokens: int = 3000,
        prompt_cache_key: str = "kin",
        hedge_after_s: float | None = None,
    ) -> T:
        """One structured completion, validated with Pydantic. Raises StructuredOutputError on bad JSON.

        prompt_cache_key: one key per shared prompt prefix (automatic prefix caching).
        hedge_after_s: if no reply by then, fire ONE duplicate (backup key if configured) and take the first success.
        """
        messages = [{"role": "developer", "content": system}, *history, {"role": "user", "content": user}]
        schema = to_strict_schema(schema_model.model_json_schema())
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": {"name": schema_model.__name__, "strict": True, "schema": schema}},
            reasoning_effort=reasoning_effort or self.reasoning_effort,
            max_completion_tokens=max_completion_tokens,
            prompt_cache_key=prompt_cache_key,
        )
        assert not (_REJECTED & kwargs.keys())
        t0 = time.perf_counter()
        content, finish = self._hedged(kwargs, hedge_after_s) if hedge_after_s else self._complete(kwargs)
        self.last_latency_ms = (time.perf_counter() - t0) * 1000
        if finish == "length":
            # VERIFIED live 2026-10-24: Muse Spark's reasoning tokens count against max_completion_tokens (medium effort ≈ 1000-1200)
            log.error("structured output truncated for %s at max_completion_tokens=%s (reasoning uses the budget)", schema_model.__name__, kwargs["max_completion_tokens"])
            raise StructuredOutputError(f"truncated at max_completion_tokens={kwargs['max_completion_tokens']}; raise the budget")
        try:
            return schema_model.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as e:
            # The output restates private facts and SMS text: ERROR (and the raised message, which callers log) gets
            # only where it broke; the raw text is at DEBUG.
            why = ("; ".join(f"{'.'.join(map(str, d['loc']))}: {d['msg']}"
                             for d in e.errors(include_url=False, include_input=False))
                   if isinstance(e, ValidationError) else str(e))
            log.error("structured output invalid for %s: %s (%d chars)", schema_model.__name__, why, len(content))
            log.debug("structured output raw for %s: %r", schema_model.__name__, content[:500])
            raise StructuredOutputError(why) from e

    def text(self, system: str, user: str, reasoning_effort: str | None = None, max_completion_tokens: int = 2500) -> str:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=[{"role": "developer", "content": system}, {"role": "user", "content": user}],
            reasoning_effort=reasoning_effort or self.reasoning_effort,
            max_completion_tokens=max_completion_tokens,
            prompt_cache_key="kin",
        )
        return self._complete(kwargs)[0]

    # -- internals ----------------------------------------------------------

    def _hedged(self, kwargs: dict[str, Any], after_s: float) -> tuple[str, str | None]:
        """Tail hedge: latency is dominated by reasoning tokens and varies 2x run to run, so a late reply is better raced than waited on."""
        first = _HEDGE_POOL.submit(self._complete, kwargs)
        try:
            return first.result(timeout=after_s)
        except FuturesTimeout:
            pass
        log.info("LLM hedge: no reply after %.1f s; firing one duplicate request", after_s)
        pending = {first, _HEDGE_POOL.submit(self._complete, kwargs, self._clients[-1:])}
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            winners = [f for f in done if f.exception() is None]
            if winners:
                return winners[0].result()
        raise next(iter(done)).exception()  # both failed: surface the last error

    def _complete(self, kwargs: dict[str, Any], clients: list[OpenAI] | None = None) -> tuple[str, str | None]:
        clients = clients or self._clients
        last: Exception | None = None
        for i, client in enumerate(clients):
            try:
                resp = client.chat.completions.create(**kwargs)
                ch = resp.choices[0]
                return ch.message.content or "", ch.finish_reason
            except (openai.RateLimitError, openai.AuthenticationError, openai.PermissionDeniedError) as e:
                last = e
                if i + 1 < len(clients):
                    log.warning("LLM key %d failed (%s); failing over to backup key", i, type(e).__name__)
                    continue
                raise
        raise last  # pragma: no cover


_default: LLM | None = None


def get_llm() -> LLM:
    global _default
    if _default is None:
        s = get_settings()
        _default = LLM(
            api_key=s.model_api_key or "missing",
            backup_api_key=s.model_api_key_backup,
            base_url=s.llm_base_url,
            model=s.llm_model,
            reasoning_effort=s.llm_reasoning_effort,
            timeout_s=s.llm_timeout_s,
        )
    return _default


def reset_llm() -> None:
    global _default
    _default = None
