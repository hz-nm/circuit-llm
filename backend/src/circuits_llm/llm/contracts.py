"""Public data contracts of the LLM layer: endpoint configuration and design events.

The API and storage layers depend only on this module; the implementation
(providers, prompts, parsing, repair loop) lives in the rest of the package.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from circuits_llm.domain import Circuit, Issue

MAX_HISTORY_TURNS: Final = 20


class ProviderKind(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENROUTER = "openrouter"
    GEMINI = "gemini"


DEFAULT_BASE_URLS: Final[dict[ProviderKind, str]] = {
    ProviderKind.ANTHROPIC: "https://api.anthropic.com",
    ProviderKind.OPENAI_COMPATIBLE: "https://api.openai.com/v1",
    ProviderKind.OPENROUTER: "https://openrouter.ai/api/v1",
    ProviderKind.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
}


class OutputMode(StrEnum):
    """How strictly the provider is asked to emit JSON.

    ``auto`` picks the strongest mode the provider is known to support and
    degrades gracefully (schema -> JSON mode -> plain text) when it is rejected.
    """

    AUTO = "auto"
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"
    TEXT = "text"


class ModelEndpoint(BaseModel):
    """One user-configured model. An ordered list of these forms the fallback chain."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    provider: ProviderKind
    model: Annotated[str, Field(min_length=1, max_length=200)]
    api_key: SecretStr | None = None
    base_url: Annotated[str, Field(max_length=500)] | None = None
    output_mode: OutputMode = OutputMode.AUTO
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.2
    max_output_tokens: Annotated[int, Field(ge=256, le=65_536)] = 16_384
    timeout_s: Annotated[float, Field(gt=0, le=600)] = 180.0
    enabled: bool = True

    @property
    def effective_base_url(self) -> str:
        return (self.base_url or DEFAULT_BASE_URLS[self.provider]).rstrip("/")


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: Annotated[str, Field(max_length=20_000)]


class DesignRequest(BaseModel):
    """Everything needed for one design turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_message: Annotated[str, Field(min_length=1, max_length=8_000)]
    history: Annotated[list[ChatTurn], Field(max_length=MAX_HISTORY_TURNS)] = Field(
        default_factory=list[ChatTurn]
    )
    current_circuit: Circuit | None = None


# --------------------------------------------------------------------------- events


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttemptStarted(_Event):
    type: Literal["attempt_started"] = "attempt_started"
    endpoint_id: str
    endpoint_label: str
    model: str
    attempt: int
    max_attempts: int


class ValidationFailed(_Event):
    """The model answered but its circuit failed parsing or ERC; a repair turn follows."""

    type: Literal["validation_failed"] = "validation_failed"
    endpoint_id: str
    attempt: int
    problems: list[str]


class EndpointFailed(_Event):
    """The endpoint errored or exhausted its attempts; the next endpoint is tried."""

    type: Literal["endpoint_failed"] = "endpoint_failed"
    endpoint_id: str
    error: str


class DesignCompleted(_Event):
    type: Literal["completed"] = "completed"
    reply: str
    circuit: Circuit | None
    warnings: list[Issue] = Field(default_factory=list[Issue])
    endpoint_id: str
    model: str


class DesignFailed(_Event):
    type: Literal["failed"] = "failed"
    error: str


DesignEvent = Annotated[
    AttemptStarted | ValidationFailed | EndpointFailed | DesignCompleted | DesignFailed,
    Field(discriminator="type"),
]


class EndpointTestResult(BaseModel):
    ok: bool
    latency_ms: int
    message: str
