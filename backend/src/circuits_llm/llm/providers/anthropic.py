"""Anthropic Messages API adapter (``POST /v1/messages``).

Claude follows a JSON format given in the prompt reliably, so ``auto`` uses
plain text. An explicit ``json_schema`` mode sends the schema as a structured
output format; Anthropic has no separate "JSON object" mode, so ``json_object``
is sent as plain text.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from ..contracts import OutputMode
from .adapter import HttpAdapter
from .base import (
    Completion,
    ErrorKind,
    JsonObject,
    Message,
    ProviderError,
    Usage,
    as_int,
    as_list,
    as_object,
    empty_response_error,
    length_exhausted_error,
    merge_turns,
    post_json,
    system_text,
)

ANTHROPIC_VERSION: Final = "2023-06-01"


class AnthropicProvider(HttpAdapter):
    provider_name = "Anthropic"
    auto_modes = (OutputMode.TEXT,)

    def _url(self) -> str:
        base = self.endpoint.effective_base_url
        return f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"

    def _headers(self) -> dict[str, str]:
        headers = {"anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
        key = self.api_key
        if key:
            headers["x-api-key"] = key
        return headers

    def _body(
        self, messages: Sequence[Message], schema: JsonObject | None, mode: OutputMode
    ) -> JsonObject:
        body: JsonObject = {
            "model": self.endpoint.model,
            "max_tokens": self.endpoint.max_output_tokens,
            "temperature": self.endpoint.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in merge_turns(messages)],
        }
        system = system_text(messages)
        if system:
            body["system"] = system
        if mode is OutputMode.JSON_SCHEMA and schema is not None:
            body["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        return body

    async def _complete_with_mode(
        self,
        messages: Sequence[Message],
        response_schema: JsonObject | None,
        mode: OutputMode,
    ) -> Completion:
        data = await post_json(
            self.client,
            self.endpoint,
            self._url(),
            headers=self._headers(),
            body=self._body(messages, response_schema, mode),
            mode=mode,
            provider=self.provider_name,
        )
        return self._parse(data)

    def _parse(self, data: JsonObject) -> Completion:
        blocks = [as_object(b) for b in as_list(data.get("content"))]
        text = "".join(str(b.get("text", "")) for b in blocks if b.get("type") == "text").strip()
        stop = data.get("stop_reason")
        finish = stop if isinstance(stop, str) else None
        if finish == "refusal":
            raise ProviderError(
                ErrorKind.BAD_REQUEST, "Anthropic declined to answer this request (refusal)."
            )
        if not text:
            if finish == "max_tokens":
                raise length_exhausted_error(self.endpoint, self.provider_name)
            raise empty_response_error(self.provider_name, finish)
        usage = as_object(data.get("usage"))
        return Completion(
            text=text,
            finish_reason=finish,
            usage=Usage(as_int(usage.get("input_tokens")), as_int(usage.get("output_tokens"))),
        )
