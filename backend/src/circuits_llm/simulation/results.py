"""Public data contracts of the simulation layer."""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_POINTS_PER_TRACE: Final = 4000


class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Axis(_Result):
    name: str  # e.g. "time", "frequency", "V1"
    unit: str  # e.g. "s", "Hz", "V"
    values: list[float]
    log_scale: bool = False


class Trace(_Result):
    name: str  # e.g. "V(OUT)" or "I(R1)"
    unit: str  # "V" or "A"
    values: list[float]  # real values; for AC analysis the linear magnitude
    phase_deg: list[float] | None = None  # AC analysis only
    net: str | None = None  # the net a voltage trace belongs to (None for currents)
    # True for signals chosen to be plotted (circuit probes, or defaults when there are
    # none); False for the extra node voltages recorded for schematic animation.
    probed: bool = True


class OperatingPointResult(_Result):
    type: Literal["op"] = "op"
    node_voltages: dict[str, float]
    branch_currents: dict[str, float]  # keyed by component id, e.g. "V1", "R1"


class SweepResult(_Result):
    type: Literal["dc", "ac", "tran"]
    x: Axis
    traces: list[Trace]


AnalysisResult = Annotated[OperatingPointResult | SweepResult, Field(discriminator="type")]


class SimulationResult(_Result):
    ok: bool
    analyses: list[AnalysisResult] = Field(default_factory=list[AnalysisResult])
    netlist: str
    error: str | None = None  # concise, human/LLM-readable failure reason
    log: str = ""  # tail of simulator output, for debugging
    duration_ms: int = 0
