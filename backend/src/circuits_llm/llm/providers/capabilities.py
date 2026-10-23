"""Per-process cache of what each endpoint turned out to support.

This is the only module-level mutable state in the LLM layer. It remembers
downgrades learned at runtime (e.g. "this vLLM server rejects ``json_schema``")
so later requests skip the failing attempt. It is keyed by everything that
affects compatibility, so editing an endpoint's model or URL starts afresh.
It is bounded and safe to lose: a restart just re-learns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..contracts import ModelEndpoint, OutputMode

MAX_CACHE_ENTRIES: Final = 256


@dataclass(slots=True)
class EndpointQuirks:
    output_mode: OutputMode | None = None  # strongest mode known to work in ``auto``
    use_max_completion_tokens: bool = False  # OpenAI reasoning models reject ``max_tokens``
    omit_temperature: bool = False  # some models only accept the default temperature


_CACHE: dict[tuple[str, str, str, str], EndpointQuirks] = {}


def _key(endpoint: ModelEndpoint) -> tuple[str, str, str, str]:
    return (endpoint.id, endpoint.provider.value, endpoint.model, endpoint.effective_base_url)


def quirks_for(endpoint: ModelEndpoint) -> EndpointQuirks:
    """Return the (mutable) quirks record for ``endpoint``, creating it if needed."""
    key = _key(endpoint)
    quirks = _CACHE.get(key)
    if quirks is None:
        if len(_CACHE) >= MAX_CACHE_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)))  # evict the oldest entry
        quirks = _CACHE[key] = EndpointQuirks()
    return quirks


def reset_capability_cache() -> None:
    """Forget everything learned (used by tests)."""
    _CACHE.clear()
