"""Canonical, strictly-typed circuit representation (the netlist).

These models describe the *shape* of a circuit. Electrical sanity (missing pins,
floating nodes, unknown models, ...) is checked separately by :mod:`.erc`, which
reports every problem at once so it can be fed back to an LLM in a single repair turn.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .catalog import ComponentKind

GROUND_NET: Final = "GND"
_GROUND_ALIASES: Final = frozenset({"gnd", "ground", "0", "agnd", "earth", "com", "common"})

MAX_COMPONENTS: Final = 300
MAX_PINS_PER_COMPONENT: Final = 8
MAX_ANALYSES: Final = 6
MAX_PROBES: Final = 24


def normalize_net(name: str) -> str:
    """Return the canonical spelling of a net name, collapsing ground aliases to ``GND``."""
    stripped = name.strip()
    return GROUND_NET if stripped.lower() in _GROUND_ALIASES else stripped


NetName = Annotated[
    str,
    Field(min_length=1, max_length=48, pattern=r"^[A-Za-z0-9_]+$"),
    AfterValidator(normalize_net),
]
Designator = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# --------------------------------------------------------------------------- sources


class SineWave(StrictModel):
    shape: Literal["sine"] = "sine"
    offset: FiniteFloat = 0.0
    amplitude: FiniteFloat
    frequency: PositiveFloat
    delay: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    phase_deg: FiniteFloat = 0.0


class PulseWave(StrictModel):
    shape: Literal["pulse"] = "pulse"
    initial: FiniteFloat
    pulsed: FiniteFloat
    delay: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    rise: PositiveFloat = 1e-9
    fall: PositiveFloat = 1e-9
    width: PositiveFloat
    period: PositiveFloat

    @model_validator(mode="after")
    def _period_fits_pulse(self) -> PulseWave:
        if self.rise + self.width + self.fall > self.period:
            raise ValueError("rise + width + fall must not exceed period")
        return self


Waveform = Annotated[SineWave | PulseWave, Field(discriminator="shape")]


# --------------------------------------------------------------------------- components


class Component(StrictModel):
    id: Designator
    kind: ComponentKind
    pins: Annotated[dict[str, NetName], Field(min_length=1, max_length=MAX_PINS_PER_COMPONENT)]
    value: FiniteFloat | None = None
    model: Annotated[str, Field(max_length=32)] | None = None
    waveform: Waveform | None = None
    ac_magnitude: FiniteFloat | None = None
    label: Annotated[str, Field(max_length=120)] | None = None


# --------------------------------------------------------------------------- analyses


class OperatingPoint(StrictModel):
    type: Literal["op"] = "op"


class DcSweep(StrictModel):
    type: Literal["dc"] = "dc"
    source: Designator
    start: FiniteFloat
    stop: FiniteFloat
    step: PositiveFloat


class AcSweep(StrictModel):
    type: Literal["ac"] = "ac"
    start_frequency: PositiveFloat
    stop_frequency: PositiveFloat
    points_per_decade: Annotated[int, Field(ge=1, le=200)] = 20

    @model_validator(mode="after")
    def _ordered(self) -> AcSweep:
        if self.stop_frequency <= self.start_frequency:
            raise ValueError("stop_frequency must be greater than start_frequency")
        return self


class Transient(StrictModel):
    type: Literal["tran"] = "tran"
    stop_time: PositiveFloat
    step_time: PositiveFloat | None = None
    start_time: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0

    @model_validator(mode="after")
    def _ordered(self) -> Transient:
        if self.start_time >= self.stop_time:
            raise ValueError("start_time must be less than stop_time")
        return self

    @property
    def effective_step(self) -> float:
        return self.step_time if self.step_time is not None else self.stop_time / 1000


Analysis = Annotated[OperatingPoint | DcSweep | AcSweep | Transient, Field(discriminator="type")]


class Probe(StrictModel):
    """A signal to plot: a net voltage (relative to GND) or the current through a component."""

    kind: Literal["voltage", "current"]
    target: Annotated[str, Field(min_length=1, max_length=48)]


# --------------------------------------------------------------------------- circuit


class PinRef(StrictModel):
    component_id: str
    pin: str


class Circuit(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=4000)] = ""
    components: Annotated[list[Component], Field(min_length=1, max_length=MAX_COMPONENTS)]
    analyses: Annotated[list[Analysis], Field(max_length=MAX_ANALYSES)] = Field(
        default_factory=list[Analysis]
    )
    probes: Annotated[list[Probe], Field(max_length=MAX_PROBES)] = Field(
        default_factory=list[Probe]
    )

    def component(self, component_id: str) -> Component | None:
        needle = component_id.lower()
        return next((c for c in self.components if c.id.lower() == needle), None)

    def nets(self) -> dict[str, list[PinRef]]:
        """Map each net name to the pins attached to it, in component order."""
        nets: defaultdict[str, list[PinRef]] = defaultdict(list)
        for component in self.components:
            for pin, net in component.pins.items():
                nets[net].append(PinRef(component_id=component.id, pin=pin))
        return dict(nets)
