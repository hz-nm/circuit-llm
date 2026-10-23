"""Provider-neutral types and HTTP plumbing shared by every adapter.

An adapter turns a list of :class:`Message` objects into one HTTP request and
the response into a :class:`Completion`. Everything that can go wrong is
reported as a :class:`ProviderError` with a machine-readable :class:`ErrorKind`,
so the design loop can decide whether to retry, repair or fail over.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal, Protocol, cast

import httpx

from ..contracts import ModelEndpoint, OutputMode

logger = logging.getLogger(__name__)

MAX_ERROR_BODY_CHARS: Final = 300
MAX_RESPONSE_BYTES: Final = 4_000_000

Role = Literal["system", "user", "assistant"]
JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    finish_reason: str | None = None
    usage: Usage | None = None


class ErrorKind(StrEnum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    BAD_REQUEST = "bad_request"
    TIMEOUT = "timeout"
    SERVER = "server"
    NETWORK = "network"
    EMPTY_RESPONSE = "empty_response"
    OUTPUT_MODE_UNSUPPORTED = "output_mode_unsupported"


_RETRYABLE_KINDS: Final = frozenset(
    {ErrorKind.RATE_LIMIT, ErrorKind.TIMEOUT, ErrorKind.SERVER, ErrorKind.NETWORK}
)


class ProviderError(Exception):
    """A failed completion. ``retryable`` errors may succeed if the same request is resent."""

    def __init__(
        self,
        kind: ErrorKind,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status_code = status_code
        self.retryable = kind in _RETRYABLE_KINDS if retryable is None else retryable


class Provider(Protocol):
    """Anything that can complete a chat. ``response_schema`` enables JSON output modes."""

    async def complete(
        self, messages: Sequence[Message], *, response_schema: JsonObject | None
    ) -> Completion: ...


# --------------------------------------------------------------------------- helpers


def truncate(text: str, limit: int = MAX_ERROR_BODY_CHARS) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def system_text(messages: Sequence[Message]) -> str:
    return "\n\n".join(m.content for m in messages if m.role == "system")


def merge_turns(messages: Sequence[Message]) -> list[Message]:
    """Drop system messages, merge consecutive same-role turns and drop a leading assistant turn.

    Anthropic and Gemini expect a conversation that starts with the user and
    alternates roles.
    """
    merged: list[Message] = []
    for message in messages:
        if message.role == "system":
            continue
        if merged and merged[-1].role == message.role:
            merged[-1] = Message(message.role, f"{merged[-1].content}\n\n{message.content}")
        else:
            merged.append(message)
    while merged and merged[0].role == "assistant":
        merged.pop(0)
    return merged


def as_object(value: object) -> JsonObject:
    return cast(JsonObject, value) if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


_MODE_ERROR_RE: Final = re.compile(
    r"response_format|json_schema|json_object|structured|response_?schema|response_?mime_?type"
    r"|response_?json_?schema|output_config|output_format|\bschema\b|\bjson\b|guided",
    re.IGNORECASE,
)


def error_from_status(status: int, body: str, *, mode: OutputMode, provider: str) -> ProviderError:
    """Map an HTTP error status (and body) to a typed :class:`ProviderError`."""
    detail = truncate(body) or "(empty body)"
    prefix = f"{provider} returned HTTP {status}"
    if status in (400, 422) and mode is not OutputMode.TEXT and _MODE_ERROR_RE.search(body):
        return ProviderError(
            ErrorKind.OUTPUT_MODE_UNSUPPORTED,
            f"{prefix}; output mode '{mode.value}' appears unsupported: {detail}",
            status_code=status,
        )
    if status in (401, 403):
        kind, hint = ErrorKind.AUTH, "check the API key"
    elif status == 429:
        kind, hint = ErrorKind.RATE_LIMIT, "rate limited or out of credits"
    elif status == 408:
        kind, hint = ErrorKind.TIMEOUT, "request timed out"
    elif status >= 500:
        kind, hint = ErrorKind.SERVER, "server error"
    elif status == 404:
        kind, hint = ErrorKind.BAD_REQUEST, "check the base URL and model name"
    else:
        kind, hint = ErrorKind.BAD_REQUEST, "request rejected"
    return ProviderError(kind, f"{prefix} ({hint}): {detail}", status_code=status)


async def post_json(
    client: httpx.AsyncClient,
    endpoint: ModelEndpoint,
    url: str,
    *,
    headers: dict[str, str],
    body: JsonObject,
    mode: OutputMode,
    provider: str,
) -> JsonObject:
    """POST ``body`` and return the decoded JSON object, raising :class:`ProviderError`."""
    logger.debug("POST %s (endpoint=%s, mode=%s)", url, endpoint.id, mode.value)
    try:
        response = await client.post(url, headers=headers, json=body, timeout=endpoint.timeout_s)
    except httpx.TimeoutException as exc:
        raise ProviderError(
            ErrorKind.TIMEOUT,
            f"{provider} did not answer within {endpoint.timeout_s:g} s ({type(exc).__name__}).",
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            ErrorKind.NETWORK, f"Could not reach {provider} at {url}: {truncate(str(exc))}"
        ) from exc

    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ProviderError(ErrorKind.SERVER, f"{provider} response is too large.")
    if response.status_code >= 400:
        logger.info("endpoint %s: HTTP %d", endpoint.id, response.status_code)
        raise error_from_status(response.status_code, response.text, mode=mode, provider=provider)
    try:
        data: object = json.loads(response.content)
    except ValueError as exc:
        raise ProviderError(
            ErrorKind.SERVER, f"{provider} returned invalid JSON: {truncate(response.text)}"
        ) from exc
    if not isinstance(data, dict):
        raise ProviderError(ErrorKind.SERVER, f"{provider} returned an unexpected JSON payload.")
    return cast(JsonObject, data)


def length_exhausted_error(endpoint: ModelEndpoint, provider: str) -> ProviderError:
    return ProviderError(
        ErrorKind.EMPTY_RESPONSE,
        f"{provider} stopped at the output token limit ({endpoint.max_output_tokens}) before "
        "producing an answer (reasoning models can spend the whole budget thinking). Increase "
        "'max output tokens' for this model in Settings.",
        retryable=False,
    )


def empty_response_error(provider: str, finish_reason: str | None) -> ProviderError:
    return ProviderError(
        ErrorKind.EMPTY_RESPONSE,
        f"{provider} returned an empty answer (finish reason: {finish_reason or 'unknown'}).",
        retryable=True,
    )
