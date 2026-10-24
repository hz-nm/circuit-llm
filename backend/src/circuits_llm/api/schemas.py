"""HTTP request/response models that are not plain domain or storage records."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from circuits_llm.domain import Category, Circuit, ComponentKind, Issue
from circuits_llm.llm.contracts import (
    AttemptStarted,
    DesignCompleted,
    DesignFailed,
    EndpointFailed,
    ModelEndpoint,
    OutputMode,
    Planned,
    ProviderKind,
    ValidationFailed,
)
from circuits_llm.storage import MessageRecord, ProjectRecord, VersionRecord, VersionSummary


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- system


class NgspiceStatus(_Schema):
    available: bool
    path: str | None


class HealthOut(_Schema):
    version: str
    ngspice: NgspiceStatus


class PinOut(_Schema):
    name: str
    description: str
    optional: bool


class ComponentSpecOut(_Schema):
    kind: ComponentKind
    display_name: str
    category: Category
    designator_prefix: str
    description: str
    pins: list[PinOut]
    value_unit: str | None
    value_required: bool
    models: list[str]
    default_model: str | None


# --------------------------------------------------------------------------- model endpoints


class EndpointIn(_Schema):
    """Create or update a model endpoint.

    On update, ``api_key`` of ``None`` keeps the stored key and ``""`` clears it.
    """

    label: Annotated[str, Field(min_length=1, max_length=80)]
    provider: ProviderKind
    model: Annotated[str, Field(min_length=1, max_length=200)]
    api_key: Annotated[str, Field(max_length=500)] | None = None
    base_url: Annotated[str, Field(max_length=500)] | None = None
    output_mode: OutputMode = OutputMode.AUTO
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.2
    max_output_tokens: Annotated[int, Field(ge=256, le=65_536)] = 16_384
    timeout_s: Annotated[float, Field(gt=0, le=600)] = 180.0
    enabled: bool = True


class EndpointOut(_Schema):
    id: str
    label: str
    provider: ProviderKind
    model: str
    base_url: str | None
    effective_base_url: str
    output_mode: OutputMode
    temperature: float
    max_output_tokens: int
    timeout_s: float
    enabled: bool
    has_api_key: bool
    api_key_hint: str | None

    @classmethod
    def from_endpoint(cls, endpoint: ModelEndpoint) -> EndpointOut:
        key = endpoint.api_key.get_secret_value() if endpoint.api_key else ""
        return cls(
            id=endpoint.id,
            label=endpoint.label,
            provider=endpoint.provider,
            model=endpoint.model,
            base_url=endpoint.base_url,
            effective_base_url=endpoint.effective_base_url,
            output_mode=endpoint.output_mode,
            temperature=endpoint.temperature,
            max_output_tokens=endpoint.max_output_tokens,
            timeout_s=endpoint.timeout_s,
            enabled=endpoint.enabled,
            has_api_key=bool(key),
            api_key_hint=f"…{key[-4:]}" if len(key) >= 8 else None,
        )


class EndpointOrder(_Schema):
    ids: Annotated[list[str], Field(max_length=64)]


# --------------------------------------------------------------------------- projects


class ProjectCreate(_Schema):
    title: Annotated[str, Field(min_length=1, max_length=120)] = "Untitled circuit"


class ProjectRename(_Schema):
    title: Annotated[str, Field(min_length=1, max_length=120)]


class VersionOut(_Schema):
    number: int
    source: str
    created_at: str
    circuit: Circuit
    issues: list[Issue]
    mermaid: str

    @classmethod
    def from_record(cls, record: VersionRecord, issues: list[Issue], mermaid: str) -> VersionOut:
        return cls(
            number=record.number,
            source=record.source,
            created_at=record.created_at.isoformat(),
            circuit=record.circuit,
            issues=issues,
            mermaid=mermaid,
        )


class ProjectDetail(_Schema):
    project: ProjectRecord
    messages: list[MessageRecord]
    versions: list[VersionSummary]
    latest: VersionOut | None


class MessageIn(_Schema):
    content: Annotated[str, Field(min_length=1, max_length=8_000)]


class CircuitIn(_Schema):
    circuit: Circuit


class SimulateOptions(_Schema):
    """Run-bar overrides for a transient simulation; omitted fields keep the circuit's own."""

    stop_time: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    step_time: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None


# --------------------------------------------------------------------------- streaming


class TurnSaved(_Schema):
    """Final stream event: what was persisted for this turn."""

    type: Literal["saved"] = "saved"
    user_message: MessageRecord
    assistant_message: MessageRecord
    version: VersionOut | None


StreamEvent = Annotated[
    Planned
    | AttemptStarted
    | ValidationFailed
    | EndpointFailed
    | DesignCompleted
    | DesignFailed
    | TurnSaved,
    Field(discriminator="type"),
]
