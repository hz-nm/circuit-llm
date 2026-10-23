"""Base class for HTTP adapters: output-mode selection and automatic downgrade.

With ``OutputMode.AUTO`` an adapter tries the strongest mode in its ladder; if
the provider rejects it (``ErrorKind.OUTPUT_MODE_UNSUPPORTED``) the request is
resent once with the next weaker mode, and the downgrade is remembered in the
capability cache so subsequent requests start there.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

import httpx

from ..contracts import ModelEndpoint, OutputMode
from .base import Completion, ErrorKind, JsonObject, Message, ProviderError
from .capabilities import EndpointQuirks, quirks_for

logger = logging.getLogger(__name__)


class HttpAdapter(ABC):
    """Shared behaviour of all adapters. Subclasses implement :meth:`_complete_with_mode`."""

    #: Human-readable provider name used in error messages.
    provider_name: ClassVar[str]
    #: Modes tried by ``auto``, strongest first. Always ends with ``TEXT``.
    auto_modes: ClassVar[tuple[OutputMode, ...]]

    def __init__(self, endpoint: ModelEndpoint, client: httpx.AsyncClient) -> None:
        self.endpoint = endpoint
        self.client = client

    @property
    def quirks(self) -> EndpointQuirks:
        return quirks_for(self.endpoint)

    @property
    def api_key(self) -> str | None:
        key = self.endpoint.api_key
        return key.get_secret_value() if key is not None else None

    def candidate_modes(self, response_schema: JsonObject | None) -> tuple[OutputMode, ...]:
        """Modes to try, in order. Without a schema the caller wants plain text."""
        if response_schema is None:
            return (OutputMode.TEXT,)
        if self.endpoint.output_mode is not OutputMode.AUTO:
            return (self.endpoint.output_mode,)
        ladder = self.auto_modes
        learned = self.quirks.output_mode
        if learned is not None and learned in ladder:
            ladder = ladder[ladder.index(learned) :]
        return ladder

    async def complete(
        self, messages: Sequence[Message], *, response_schema: JsonObject | None
    ) -> Completion:
        modes = self.candidate_modes(response_schema)
        for index, mode in enumerate(modes):  # bounded by the ladder length (<= 3)
            try:
                return await self._complete_with_mode(messages, response_schema, mode)
            except ProviderError as exc:
                is_last = index == len(modes) - 1
                if exc.kind is not ErrorKind.OUTPUT_MODE_UNSUPPORTED or is_last:
                    raise
                weaker = modes[index + 1]
                logger.info(
                    "endpoint %s rejected output mode %s; downgrading to %s",
                    self.endpoint.id,
                    mode.value,
                    weaker.value,
                )
                self.quirks.output_mode = weaker
        raise AssertionError("unreachable: the mode ladder is never empty")

    @abstractmethod
    async def _complete_with_mode(
        self,
        messages: Sequence[Message],
        response_schema: JsonObject | None,
        mode: OutputMode,
    ) -> Completion: ...
