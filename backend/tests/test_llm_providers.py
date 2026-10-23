"""Provider adapters against ``httpx.MockTransport`` (no network)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from circuits_llm.llm import (
    ErrorKind,
    Message,
    ModelEndpoint,
    ProviderError,
    ProviderKind,
    create_provider,
    response_schema,
)
from circuits_llm.llm.providers import reset_capability_cache

Handler = Callable[[httpx.Request], httpx.Response]
MESSAGES = (Message("system", "sys"), Message("user", "hi"))


def _complete(endpoint: ModelEndpoint, handler: Handler) -> str:
    async def go() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = create_provider(endpoint, client)
            completion = await provider.complete(MESSAGES, response_schema=response_schema())
            return completion.text

    return asyncio.run(go())


def _endpoint(provider: ProviderKind, **extra: object) -> ModelEndpoint:
    return ModelEndpoint.model_validate(
        {"id": "e1", "label": "E", "provider": provider, "model": "gpt-oss-120b", **extra}
    )


def test_openai_downgrades_rejected_json_schema_and_remembers_it() -> None:
    reset_capability_cache()
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        mode = body.get("response_format", {}).get("type")
        seen.append(mode)
        if mode == "json_schema":
            return httpx.Response(400, json={"error": "response_format json_schema not supported"})
        message = {"content": '{"reply": "ok", "circuit": null}', "reasoning": "hmm"}
        return httpx.Response(
            200, json={"choices": [{"message": message, "finish_reason": "stop"}]}
        )

    endpoint = _endpoint(ProviderKind.OPENAI_COMPATIBLE, base_url="http://localhost:8000/v1")
    assert _complete(endpoint, handler) == '{"reply": "ok", "circuit": null}'
    assert _complete(endpoint, handler) == '{"reply": "ok", "circuit": null}'
    assert seen == ["json_schema", "json_object", "json_object"]


def test_reasoning_model_that_runs_out_of_tokens_gets_a_clear_error() -> None:
    reset_capability_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        message = {"content": None, "reasoning_content": "Let me think about resistors..."}
        return httpx.Response(
            200, json={"choices": [{"message": message, "finish_reason": "length"}]}
        )

    with pytest.raises(ProviderError) as info:
        _complete(_endpoint(ProviderKind.OPENROUTER), handler)
    assert info.value.kind is ErrorKind.EMPTY_RESPONSE
    assert "max output tokens" in info.value.message


def test_anthropic_request_shape_and_auth_error() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

    endpoint = _endpoint(ProviderKind.ANTHROPIC, model="claude-x", api_key=SecretStr("sk-test"))
    with pytest.raises(ProviderError) as info:
        _complete(endpoint, handler)
    assert (info.value.kind, info.value.retryable) == (ErrorKind.AUTH, False)
    request = captured[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "sk-test"
    assert body["system"] == "sys"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
