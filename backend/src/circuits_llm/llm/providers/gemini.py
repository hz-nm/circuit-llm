"""Google Gemini adapter (``POST /models/{model}:generateContent``).

``auto`` uses JSON mode (``responseMimeType: application/json``), which every
Gemini model supports; an explicit ``json_schema`` also sends the schema as
``responseJsonSchema``.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import quote

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


class GeminiProvider(HttpAdapter):
    provider_name = "Gemini"
    auto_modes = (OutputMode.JSON_OBJECT, OutputMode.TEXT)

    def _url(self) -> str:
        model = self.endpoint.model.removeprefix("models/")
        return (
            f"{self.endpoint.effective_base_url}/models/{quote(model, safe='-._')}:generateContent"
        )

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        key = self.api_key
        if key:
            headers["x-goog-api-key"] = key
        return headers

    def _body(
        self, messages: Sequence[Message], schema: JsonObject | None, mode: OutputMode
    ) -> JsonObject:
        config: JsonObject = {
            "temperature": self.endpoint.temperature,
            "maxOutputTokens": self.endpoint.max_output_tokens,
        }
        if mode in (OutputMode.JSON_OBJECT, OutputMode.JSON_SCHEMA):
            config["responseMimeType"] = "application/json"
        if mode is OutputMode.JSON_SCHEMA and schema is not None:
            config["responseJsonSchema"] = schema
        body: JsonObject = {
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in merge_turns(messages)
            ],
            "generationConfig": config,
        }
        system = system_text(messages)
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
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
        candidates = as_list(data.get("candidates"))
        if not candidates:
            block = as_object(data.get("promptFeedback")).get("blockReason")
            reason = f" (blocked: {block})" if block else ""
            raise ProviderError(ErrorKind.BAD_REQUEST, f"Gemini returned no candidates{reason}.")
        candidate = as_object(candidates[0])
        parts = [as_object(p) for p in as_list(as_object(candidate.get("content")).get("parts"))]
        text = "".join(str(p.get("text", "")) for p in parts if not p.get("thought")).strip()
        raw_finish = candidate.get("finishReason")
        finish = raw_finish if isinstance(raw_finish, str) else None
        if not text:
            if finish == "MAX_TOKENS":
                raise length_exhausted_error(self.endpoint, self.provider_name)
            raise empty_response_error(self.provider_name, finish)
        usage = as_object(data.get("usageMetadata"))
        return Completion(
            text=text,
            finish_reason=finish,
            usage=Usage(
                as_int(usage.get("promptTokenCount")), as_int(usage.get("candidatesTokenCount"))
            ),
        )
