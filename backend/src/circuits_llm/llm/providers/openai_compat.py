"""OpenAI-compatible Chat Completions adapter (``POST /chat/completions``).

Works with OpenAI, vLLM, Ollama, LM Studio, Groq, Together and similar servers.
Two kinds of server differences are handled transparently:

* **Output mode** (``response_format``): downgraded by :class:`HttpAdapter`.
* **Parameters**: OpenAI reasoning models reject ``max_tokens`` (they want
  ``max_completion_tokens``) and sometimes any non-default ``temperature``. When
  a 400 says so, the request is resent with the parameter fixed (bounded) and
  the fix is remembered in the capability cache.

Reasoning models such as gpt-oss may return ``content: null`` with their
thinking in ``reasoning``/``reasoning_content``; an empty answer that hit the
token limit becomes a clear error suggesting a larger output budget.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any, Final

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
    post_json,
    truncate,
)

logger = logging.getLogger(__name__)

MAX_PARAMETER_FIXUPS: Final = 2
SCHEMA_NAME: Final = "circuit_design"

_MAX_TOKENS_RE: Final = re.compile(r"max_completion_tokens|max_tokens", re.IGNORECASE)
_TEMPERATURE_RE: Final = re.compile(r"temperature", re.IGNORECASE)


class OpenAICompatibleProvider(HttpAdapter):
    provider_name = "OpenAI-compatible server"
    auto_modes = (OutputMode.JSON_SCHEMA, OutputMode.JSON_OBJECT, OutputMode.TEXT)

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        key = self.api_key
        if key:
            headers["authorization"] = f"Bearer {key}"
        return headers

    def _body(
        self, messages: Sequence[Message], schema: JsonObject | None, mode: OutputMode
    ) -> JsonObject:
        quirks = self.quirks
        body: JsonObject = {
            "model": self.endpoint.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        tokens_key = "max_completion_tokens" if quirks.use_max_completion_tokens else "max_tokens"
        body[tokens_key] = self.endpoint.max_output_tokens
        if not quirks.omit_temperature:
            body["temperature"] = self.endpoint.temperature
        if mode is OutputMode.JSON_SCHEMA and schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": SCHEMA_NAME, "schema": schema, "strict": False},
            }
        elif mode is OutputMode.JSON_OBJECT:
            body["response_format"] = {"type": "json_object"}
        return body

    async def _complete_with_mode(
        self,
        messages: Sequence[Message],
        response_schema: JsonObject | None,
        mode: OutputMode,
    ) -> Completion:
        url = f"{self.endpoint.effective_base_url}/chat/completions"
        for fixup in range(MAX_PARAMETER_FIXUPS + 1):
            try:
                data = await post_json(
                    self.client,
                    self.endpoint,
                    url,
                    headers=self._headers(),
                    body=self._body(messages, response_schema, mode),
                    mode=mode,
                    provider=self.provider_name,
                )
            except ProviderError as exc:
                if fixup == MAX_PARAMETER_FIXUPS or not self._apply_parameter_fix(exc):
                    raise
                continue
            return self._parse(data)
        raise AssertionError("unreachable: the fixup loop always returns or raises")

    def _apply_parameter_fix(self, exc: ProviderError) -> bool:
        """Adjust cached quirks for a parameter the server rejected; True if anything changed."""
        if exc.status_code != 400 or exc.kind is ErrorKind.OUTPUT_MODE_UNSUPPORTED:
            return False
        quirks = self.quirks
        if (
            "max_completion_tokens" in exc.message
            and _MAX_TOKENS_RE.search(exc.message)
            and not quirks.use_max_completion_tokens
        ):
            quirks.use_max_completion_tokens = True
        elif _TEMPERATURE_RE.search(exc.message) and not quirks.omit_temperature:
            quirks.omit_temperature = True
        else:
            return False
        logger.info("endpoint %s: adjusted request parameters after HTTP 400", self.endpoint.id)
        return True

    def _parse(self, data: JsonObject) -> Completion:
        choices = as_list(data.get("choices"))
        if not choices:
            error = as_object(data.get("error"))
            detail = truncate(str(error.get("message") or data))
            raise ProviderError(
                ErrorKind.SERVER, f"{self.provider_name} returned no choices: {detail}"
            )
        choice = as_object(choices[0])
        message = as_object(choice.get("message"))
        text = _content_text(message.get("content")).strip()
        raw_finish = choice.get("finish_reason")
        finish = raw_finish if isinstance(raw_finish, str) else None
        if not text:
            has_reasoning = bool(message.get("reasoning") or message.get("reasoning_content"))
            if finish == "length":
                raise length_exhausted_error(self.endpoint, self.provider_name)
            if has_reasoning:
                raise ProviderError(
                    ErrorKind.EMPTY_RESPONSE,
                    f"{self.provider_name} returned only reasoning and no final answer "
                    f"(finish reason: {finish or 'unknown'}). If this keeps happening, increase "
                    "'max output tokens' or check the server's reasoning parser settings.",
                    retryable=True,
                )
            raise empty_response_error(self.provider_name, finish)
        usage = as_object(data.get("usage"))
        return Completion(
            text=text,
            finish_reason=finish,
            usage=Usage(as_int(usage.get("prompt_tokens")), as_int(usage.get("completion_tokens"))),
        )


def _content_text(content: Any) -> str:
    """``content`` is a string, null, or (on some servers) a list of typed parts."""
    if isinstance(content, str):
        return content
    parts = [as_object(p) for p in as_list(content)]
    return "".join(str(p.get("text", "")) for p in parts if p.get("type") in ("text", None))


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter: the OpenAI-compatible API plus attribution headers."""

    provider_name = "OpenRouter"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["HTTP-Referer"] = "https://github.com/circuits-llm/circuits-llm"
        headers["X-Title"] = "circuits-llm"
        return headers
