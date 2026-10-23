"""Construct providers for endpoints and run the Settings-page connectivity test."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Final

import httpx

from ..contracts import EndpointTestResult, ModelEndpoint, ProviderKind
from .adapter import HttpAdapter
from .anthropic import AnthropicProvider
from .base import Message, Provider, ProviderError, truncate
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatibleProvider, OpenRouterProvider

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[ModelEndpoint, httpx.AsyncClient], Provider]

_ADAPTERS: Final[dict[ProviderKind, type[HttpAdapter]]] = {
    ProviderKind.ANTHROPIC: AnthropicProvider,
    ProviderKind.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
    ProviderKind.OPENROUTER: OpenRouterProvider,
    ProviderKind.GEMINI: GeminiProvider,
}

_TEST_MESSAGES: Final = (
    Message("system", "You are a connectivity check. Reply with the single word OK."),
    Message("user", "Reply with OK."),
)
MAX_TEST_REPLY_CHARS: Final = 80


def create_provider(endpoint: ModelEndpoint, client: httpx.AsyncClient) -> Provider:
    """Return the adapter for ``endpoint.provider`` bound to ``client``."""
    return _ADAPTERS[endpoint.provider](endpoint, client)


async def test_endpoint(endpoint: ModelEndpoint, client: httpx.AsyncClient) -> EndpointTestResult:
    """Send a tiny round-trip request and report success, latency and a short message."""
    provider = create_provider(endpoint, client)
    started = time.perf_counter()
    try:
        completion = await provider.complete(_TEST_MESSAGES, response_schema=None)
    except ProviderError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        logger.info("endpoint test %s failed: %s", endpoint.id, exc.kind.value)
        return EndpointTestResult(ok=False, latency_ms=latency, message=exc.message)
    latency = int((time.perf_counter() - started) * 1000)
    reply = truncate(completion.text, MAX_TEST_REPLY_CHARS)
    return EndpointTestResult(ok=True, latency_ms=latency, message=f"Model replied: {reply}")
