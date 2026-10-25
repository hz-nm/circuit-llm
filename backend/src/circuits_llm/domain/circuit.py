"""Canonical, strictly-typed circuit representation (the netlist).

These models describe the *shape* of a circuit. Electrical sanity (missing pins,
floating nodes, unknown models, ...) is checked separately by :mod:`.erc`, which
reports every problem at once so it can be fed back to an LLM in a single repair turn.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .catalog import ComponentKind

GROUND_NET: Final = "GND"
_GROUND_ALIASES: Final = frozenset({"gnd", "ground", "0", "agnd", "earth", "com", "common"})

MAX_COMPONENTS: Final = 300
MAX_PINS_PER_COMPONENT: Final = 8
MAX_ANALYSES: Final = 6
MAX_PROBES: Final = 24
MAX_PWL_POINTS: Final = 200
MAX_EXPECTATIONS: Final = 6


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


class PwlWave(StrictModel):
    """Piecewise-linear waveform: straight lines through ``(time, value)`` points.

    Holds the last value after the final point. Good for ramps and slow profiles such
    as a solar panel going from day to night.
    """

    shape: Literal["pwl"] = "pwl"
    points: Annotated[
        list[tuple[Annotated[float, Field(ge=0, allow_inf_nan=False)], FiniteFloat]],
        Field(min_length=2, max_length=MAX_PWL_POINTS),
    ]

    @model_validator(mode="after")
    def _increasing_times(self) -> PwlWave:
        times = [t for t, _ in self.points]
        if any(b <= a for a, b in pairwise(times)):
            raise ValueError("point times must be strictly increasing")
        return self


Waveform = Annotated[SineWave | PulseWave | PwlWave, Field(discriminator="shape")]


# --------------------------------------------------------------------------- components


MAX_PIN_BEHAVIORS: Final = 18


class PinBehavior(StrictModel):
    """How a microcontroller drives one output pin (see :mod:`.arduino`).

    ``high``/``low``: constant. ``blink``: on/off with ``period`` seconds and ``duty``
    (fraction on, default 0.5). ``pwm``: ``duty`` 0..1 at ``frequency`` Hz (default 490).
    ``rule``: high while ``when`` holds, e.g. ``"A0 < 2.5"``.
    """

    pin: Annotated[str, Field(min_length=2, max_length=4)]
    output: Literal["high", "low", "blink", "pwm", "rule"]
    period: PositiveFloat | None = None
    duty: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    frequency: PositiveFloat | None = None
    when: Annotated[str, Field(min_length=3, max_length=48)] | None = None


class Component(StrictModel):
    id: Designator
    kind: ComponentKind
    pins: Annotated[dict[str, NetName], Field(min_length=1, max_length=MAX_PINS_PER_COMPONENT)]
    value: FiniteFloat | None = None
    model: Annotated[str, Field(max_length=32)] | None = None
    waveform: Waveform | None = None
    ac_magnitude: FiniteFloat | None = None
    # Sensors only: the environment they sense (light, temperature, ...), as a constant
    # or as a waveform over time. Units are given by the catalog's StimulusSpec.
    stimulus: FiniteFloat | Waveform | None = None
    # Microcontrollers only: what each output pin does.
    behavior: Annotated[list[PinBehavior], Field(max_length=MAX_PIN_BEHAVIORS)] | None = None
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


class Expectation(StrictModel):
    """What the circuit must do, verified on the simulation, e.g. ``I(D1) > 5m``
    ``when`` ``light(LDR1) < 1``. See :mod:`.expectations` for the grammar."""

    description: Annotated[str, Field(min_length=1, max_length=120)]
    signal: Annotated[str, Field(min_length=1, max_length=48)]
    check: Annotated[str, Field(min_length=2, max_length=32)]
    when: Annotated[str, Field(min_length=3, max_length=64)] | None = None


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
    expectations: Annotated[list[Expectation], Field(max_length=MAX_EXPECTATIONS)] = Field(
        default_factory=list[Expectation]
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
