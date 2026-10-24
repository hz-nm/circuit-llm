"""Post-simulation sanity checks: would the circuit survive on a real bench?

The ERC checks wiring; this module checks physics. Each component's simulated
currents, voltages and power are compared with datasheet ratings. Errors (a part
would be destroyed or is outside its supply range) go back to the LLM for repair;
warnings (e.g. a resistor needing a higher power rating) are shown to the user.

Operating-point and DC-sweep points are steady states, so they are compared with
continuous ratings. Transients use time-averaged current and power (thermal
limits) and peak current (pulse limits), so a brief turn-on spike is not an error.
AC results are small-signal and are not checked.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from circuits_llm.domain import (
    CATALOG,
    GROUND_NET,
    Circuit,
    Component,
    ComponentKind,
    Issue,
    Severity,
    format_si,
)

from .results import OperatingPointResult, SimulationResult

RESISTOR_DEFAULT_WATTS: Final = 0.25
LAMP_OVERLOAD: Final = 1.2  # tolerated power above rating before calling it overdriven
CMOS_INPUT_MARGIN_V: Final = 0.5  # input beyond the rails before clamp diodes conduct
_RESISTOR_WATT_STEPS: Final = (0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0)


@dataclass(frozen=True, slots=True)
class Rating:
    """Datasheet limits. ``None`` means not checked."""

    current: float | None = None  # continuous forward / collector / drain current (A)
    peak_current: float | None = None  # pulse or surge current (A)
    voltage: float | None = None  # reverse voltage (diodes), V_CE / V_DS (transistors)
    power: float | None = None  # dissipation without a heatsink (W)
    power_heatsunk: float | None = None  # with a heatsink; above `power` is only a warning
    gate_voltage: float | None = None  # |V_GS| for MOSFETs
    supply: tuple[float, float] | None = None  # allowed supply range for ICs (V)


_LED = Rating(current=0.030, peak_current=0.100, voltage=5.0)
_TO92_NPN = {
    "2N3904": Rating(current=0.200, voltage=40, power=0.625),
    "2N2222": Rating(current=0.600, voltage=40, power=0.625),
    "BC547": Rating(current=0.100, voltage=45, power=0.5),
}
_TO92_PNP = {
    "2N3906": Rating(current=0.200, voltage=40, power=0.625),
    "2N2907": Rating(current=0.600, voltage=60, power=0.625),
    "BC557": Rating(current=0.100, voltage=45, power=0.5),
}

RATINGS: Final[dict[ComponentKind, dict[str, Rating]]] = {
    ComponentKind.LED: {colour: _LED for colour in ("red", "green", "yellow", "blue", "white")},
    ComponentKind.DIODE: {
        "1N4148": Rating(current=0.300, peak_current=2.0, voltage=100, power=0.5),
        "1N4007": Rating(current=1.0, peak_current=30, voltage=1000),
        "1N5819": Rating(current=1.0, peak_current=25, voltage=40),
    },
    ComponentKind.NPN: _TO92_NPN,
    ComponentKind.PNP: _TO92_PNP,
    ComponentKind.NMOS: {
        "2N7000": Rating(current=0.200, peak_current=0.5, voltage=60, power=0.4, gate_voltage=20),
        "BS170": Rating(current=0.500, peak_current=1.2, voltage=60, power=0.83, gate_voltage=20),
        "IRFZ44N": Rating(
            current=49, peak_current=160, voltage=55, power=2.0, power_heatsunk=94, gate_voltage=20
        ),
        "IRLZ44N": Rating(
            current=47, peak_current=160, voltage=55, power=2.0, power_heatsunk=110, gate_voltage=16
        ),
    },
    ComponentKind.PMOS: {
        "BS250": Rating(current=0.180, peak_current=0.6, voltage=45, power=0.83, gate_voltage=20),
        "IRF9540": Rating(
            current=23, peak_current=72, voltage=100, power=2.0, power_heatsunk=140, gate_voltage=20
        ),
    },
    ComponentKind.OPAMP: {
        "LM358": Rating(supply=(3, 32)),
        "TL072": Rating(supply=(6, 36)),
    },
}
_LOGIC_SUPPLY: Final = {"74HC": (2.0, 6.0), "CD4000": (3.0, 18.0)}
ZENER_WATTS: Final = 0.5

_TRANSISTORS: Final = frozenset(
    {ComponentKind.NPN, ComponentKind.PNP, ComponentKind.NMOS, ComponentKind.PMOS}
)


# --------------------------------------------------------------------------- signals


@dataclass(frozen=True, slots=True)
class _Signals:
    """Node voltages and component currents of one analysis, on a shared x axis."""

    label: str  # "at the operating point", "in the DC sweep", "during the transient"
    transient: bool
    time: Sequence[float]  # the x axis: time, or the swept source value
    voltages: dict[str, Sequence[float]]
    currents: dict[str, Sequence[float]]
    sweep: tuple[str, str] | None = None  # (source id, unit) for a DC sweep

    def where(self, values: Sequence[float]) -> str:
        """Where the worst |value| occurs, e.g. "in the DC sweep (worst at VG = 2.6 V)"."""
        if self.sweep is None or not values:
            return self.label
        index = max(range(min(len(values), self.points)), key=lambda i: abs(values[i]))
        source, unit = self.sweep
        return f"{self.label} (worst at {source} = {format_si(self.time[index], unit)})"

    @property
    def points(self) -> int:
        return len(self.time)

    def v(self, net: str) -> Sequence[float]:
        if net == GROUND_NET:
            return [0.0] * self.points
        return self.voltages.get(net, ())

    def current(self, component_id: str) -> Sequence[float]:
        return self.currents.get(component_id, ())


def _signals(result: SimulationResult) -> Iterator[_Signals]:
    for analysis in result.analyses:
        if isinstance(analysis, OperatingPointResult):
            yield _Signals(
                label="at the operating point",
                transient=False,
                time=[0.0],
                voltages={net: [v] for net, v in analysis.node_voltages.items()},
                currents={cid: [i] for cid, i in analysis.branch_currents.items()},
            )
        elif analysis.type in ("dc", "tran"):
            yield _Signals(
                label="during the transient" if analysis.type == "tran" else "in the DC sweep",
                transient=analysis.type == "tran",
                time=analysis.x.values,
                voltages={t.net: t.values for t in analysis.traces if t.net},
                currents={t.component: t.values for t in analysis.traces if t.component},
                sweep=(analysis.x.name, analysis.x.unit) if analysis.type == "dc" else None,
            )


def _difference(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x - y for x, y in zip(a, b, strict=False)]


def _product(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x * y for x, y in zip(a, b, strict=False)]


def _sustained(signals: _Signals, values: Sequence[float]) -> float:
    """Worst steady value, or the time-weighted mean of |values| for a transient."""
    if not values:
        return 0.0
    if not signals.transient or len(values) < 2:
        return max(abs(v) for v in values)
    time = signals.time
    area = sum(
        (time[i + 1] - time[i]) * (abs(values[i]) + abs(values[i + 1])) / 2
        for i in range(min(len(values), len(time)) - 1)
    )
    span = time[min(len(values), len(time)) - 1] - time[0]
    return area / span if span > 0 else max(abs(v) for v in values)


def _peak(values: Sequence[float]) -> float:
    return max((abs(v) for v in values), default=0.0)


# --------------------------------------------------------------------------- checks


@dataclass(frozen=True, slots=True)
class _Finding:
    severity: Severity
    code: str
    message: str


def check_ratings(circuit: Circuit, result: SimulationResult) -> list[Issue]:
    """Every rating problem in ``result``, at most one per component and rule."""
    if not result.ok:
        return []
    worst: dict[tuple[str, str], tuple[float, _Finding]] = {}
    for signals in _signals(result):
        for component in circuit.components:
            for score, finding in _check_component(component, signals):
                key = (component.id, finding.code)
                if key not in worst or score > worst[key][0]:
                    worst[key] = (score, finding)
    issues = [
        Issue(severity=f.severity, code=f.code, message=f.message, component_id=cid)
        for (cid, _), (_, f) in worst.items()
    ]
    return sorted(issues, key=lambda i: i.severity is not Severity.ERROR)


def _check_component(component: Component, s: _Signals) -> Iterator[tuple[float, _Finding]]:
    """(severity score, finding) pairs; the score picks the worst analysis per rule."""
    kind = component.kind
    model = component.model or CATALOG[kind].default_model
    rating = RATINGS.get(kind, {}).get(model or "")
    pins = component.pins
    name = f"{component.id} ({model + ' ' if model else ''}{CATALOG[kind].display_name.lower()})"

    if kind in (ComponentKind.LED, ComponentKind.DIODE, ComponentKind.ZENER):
        yield from _diode_checks(component, name, rating, s)
    elif kind is ComponentKind.RESISTOR:
        yield from _resistor_checks(component, name, s)
    elif kind is ComponentKind.LAMP:
        yield from _lamp_checks(component, name, s)
    elif kind in _TRANSISTORS and rating is not None:
        yield from _transistor_checks(component, name, rating, s)
    elif kind is ComponentKind.OPAMP and rating is not None and rating.supply and "v+" in pins:
        yield from _supply_checks(name, rating.supply, s.v(pins["v+"]), s.v(pins["v-"]), s)
    elif model in _LOGIC_SUPPLY and "vdd" in pins and "vss" in pins:
        vdd, vss = s.v(pins["vdd"]), s.v(pins["vss"])
        yield from _supply_checks(name, _LOGIC_SUPPLY[model], vdd, vss, s, model)
        yield from _logic_input_checks(component, name, vdd, vss, s)


def _diode_checks(
    component: Component, name: str, rating: Rating | None, s: _Signals
) -> Iterator[tuple[float, _Finding]]:
    current = s.current(component.id)
    if not current:
        return
    anode, cathode = s.v(component.pins["anode"]), s.v(component.pins["cathode"])
    forward = [max(i, 0.0) for i in current]
    if component.kind is ComponentKind.ZENER:
        power = _product(_difference(anode, cathode), current)
        watts = _sustained(s, power)
        if watts > ZENER_WATTS:
            yield (
                watts,
                _Finding(
                    Severity.ERROR,
                    "zener_overpower",
                    f"{name} dissipates {format_si(watts, 'W')} {s.where(power)}, above its "
                    f"{format_si(ZENER_WATTS, 'W')} rating. Increase its series resistor.",
                ),
            )
        return
    if rating is None:
        return
    sustained, peak = _sustained(s, forward), _peak(forward)
    if rating.current is not None and sustained > rating.current:
        fix = (
            "Add or increase the series resistor: R = (supply - forward voltage) / 20 mA. "
            "For a light load above about 1 W use a 'lamp' instead."
            if component.kind is ComponentKind.LED
            else "Use a diode rated for more current."
        )
        yield (
            sustained / rating.current,
            _Finding(
                Severity.ERROR,
                "overcurrent",
                f"{name} carries {format_si(sustained, 'A')} {s.where(forward)}, above its "
                f"{format_si(rating.current, 'A')} rating. {fix}",
            ),
        )
    if rating.peak_current is not None and s.transient and peak > rating.peak_current:
        yield (
            peak / rating.peak_current,
            _Finding(
                Severity.ERROR,
                "peak_overcurrent",
                f"{name} peaks at {format_si(peak, 'A')} {s.label}, above its "
                f"{format_si(rating.peak_current, 'A')} pulse rating. Limit the current.",
            ),
        )
    reverse_v = _difference(cathode, anode)
    reverse = max(reverse_v, default=0.0)
    if rating.voltage is not None and reverse > rating.voltage:
        severity = Severity.WARNING if component.kind is ComponentKind.LED else Severity.ERROR
        yield (
            reverse / rating.voltage,
            _Finding(
                severity,
                "reverse_voltage",
                f"{name} sees {format_si(reverse, 'V')} in reverse {s.where(reverse_v)}, above its "
                f"{format_si(rating.voltage, 'V')} rating. Check its orientation or add a "
                "protection diode.",
            ),
        )


def _resistor_checks(
    component: Component, name: str, s: _Signals
) -> Iterator[tuple[float, _Finding]]:
    current = s.current(component.id)
    if not current:
        return
    across = _difference(s.v(component.pins["1"]), s.v(component.pins["2"]))
    power = _product(across, current)
    watts = _sustained(s, power)
    if watts > RESISTOR_DEFAULT_WATTS:
        needed = next((w for w in _RESISTOR_WATT_STEPS if w >= 2 * watts), None)
        advice = (
            f"use a {format_si(needed, 'W')} (or larger) resistor"
            if needed is not None
            else "this is a load, not a resistor: model it as a 'lamp' or reduce the current"
        )
        yield (
            watts,
            _Finding(
                Severity.WARNING,
                "resistor_power",
                f"{name} dissipates {format_si(watts, 'W')} {s.where(power)}; "
                f"a standard resistor is "
                f"rated {format_si(RESISTOR_DEFAULT_WATTS, 'W')}, so {advice}.",
            ),
        )


def _lamp_checks(component: Component, name: str, s: _Signals) -> Iterator[tuple[float, _Finding]]:
    current = s.current(component.id)
    rated_watts = component.value
    if not current or rated_watts is None or rated_watts <= 0:
        return
    across = _difference(s.v(component.pins["1"]), s.v(component.pins["2"]))
    power = _product(across, current)
    watts = _sustained(s, power)
    if watts > rated_watts * LAMP_OVERLOAD:
        yield (
            watts / rated_watts,
            _Finding(
                Severity.ERROR,
                "lamp_overdriven",
                f"{name} draws {format_si(watts, 'W')} {s.where(power)}, "
                f"{watts / rated_watts:.1f}x its "
                f"{format_si(rated_watts, 'W')} rating: it sees more than its rated "
                f"{component.model} supply. Power it from its rated voltage.",
            ),
        )


def _transistor_checks(
    component: Component, name: str, rating: Rating, s: _Signals
) -> Iterator[tuple[float, _Finding]]:
    mos = component.kind in (ComponentKind.NMOS, ComponentKind.PMOS)
    main, control, common = ("drain", "gate", "source") if mos else ("collector", "base", "emitter")
    label_i, label_v = ("drain current", "V_DS") if mos else ("collector current", "V_CE")
    v_main = _difference(s.v(component.pins[main]), s.v(component.pins[common]))
    current = s.current(component.id)  # into the drain / collector

    if rating.voltage is not None and _peak(v_main) > rating.voltage:
        peak_v = _peak(v_main)
        yield (
            peak_v / rating.voltage,
            _Finding(
                Severity.ERROR,
                "overvoltage",
                f"{name} sees {label_v} = {format_si(peak_v, 'V')} {s.where(v_main)}, above its "
                f"{format_si(rating.voltage, 'V')} rating. Choose a higher-voltage part.",
            ),
        )
    if mos and rating.gate_voltage is not None:
        v_gs = _difference(s.v(component.pins[control]), s.v(component.pins[common]))
        v_gate = _peak(v_gs)
        if v_gate > rating.gate_voltage:
            yield (
                v_gate / rating.gate_voltage,
                _Finding(
                    Severity.ERROR,
                    "gate_overvoltage",
                    f"{name} sees |V_GS| = {format_si(v_gate, 'V')} {s.where(v_gs)}, above the "
                    f"{format_si(rating.gate_voltage, 'V')} gate limit. Clamp the gate with a "
                    "zener or drive it from a lower voltage.",
                ),
            )
    if not current:
        return
    sustained = _sustained(s, current)
    if rating.current is not None and sustained > rating.current:
        yield (
            sustained / rating.current,
            _Finding(
                Severity.ERROR,
                "overcurrent",
                f"{name} {label_i} is {format_si(sustained, 'A')} {s.where(current)}, above its "
                f"{format_si(rating.current, 'A')} rating. Use a bigger transistor (e.g. IRFZ44N "
                "for loads above a few hundred mA) or reduce the load current.",
            ),
        )
    if rating.peak_current is not None and s.transient and _peak(current) > rating.peak_current:
        yield (
            _peak(current) / rating.peak_current,
            _Finding(
                Severity.ERROR,
                "peak_overcurrent",
                f"{name} {label_i} peaks at {format_si(_peak(current), 'A')} {s.label}, above its "
                f"{format_si(rating.peak_current, 'A')} pulse rating.",
            ),
        )
    if rating.power is not None:
        power = _product(v_main, current)
        watts = _sustained(s, power)
        limit = rating.power_heatsunk or rating.power
        if watts > limit:
            yield (
                watts / limit,
                _Finding(
                    Severity.ERROR,
                    "overpower",
                    f"{name} dissipates {format_si(watts, 'W')} {s.where(power)}, above its "
                    f"{format_si(limit, 'W')} limit. Drive it fully on (as a switch) or use a "
                    "bigger part.",
                ),
            )
        elif watts > rating.power:
            yield (
                watts / rating.power,
                _Finding(
                    Severity.WARNING,
                    "needs_heatsink",
                    f"{name} dissipates {format_si(watts, 'W')} {s.where(power)}; above "
                    f"{format_si(rating.power, 'W')} it needs a heatsink.",
                ),
            )


def _supply_checks(
    name: str,
    allowed: tuple[float, float],
    positive: Sequence[float],
    negative: Sequence[float],
    s: _Signals,
    model: str | None = None,
) -> Iterator[tuple[float, _Finding]]:
    supply = _difference(positive, negative)
    if not supply:
        return
    low, high = allowed
    peak = max(supply)
    if peak > high:
        alternative = " Use model CD4000 (3-18 V) or a lower supply." if model == "74HC" else ""
        yield (
            peak / high,
            _Finding(
                Severity.ERROR,
                "supply_overvoltage",
                f"{name} is powered from {format_si(peak, 'V')} {s.where(supply)}, "
                f"but it allows at most "
                f"{format_si(high, 'V')}.{alternative}",
            ),
        )
    elif max(supply) < low:
        yield (
            1.0,
            _Finding(
                Severity.WARNING,
                "supply_too_low",
                f"{name} is powered from only {format_si(max(supply), 'V')} "
                f"{s.where(supply)}; it needs "
                f"at least {format_si(low, 'V')} to work.",
            ),
        )


def _logic_input_checks(
    component: Component,
    name: str,
    vdd: Sequence[float],
    vss: Sequence[float],
    s: _Signals,
) -> Iterator[tuple[float, _Finding]]:
    for pin in ("a", "b"):
        if pin not in component.pins:
            continue
        signal = s.v(component.pins[pin])
        above = max((x - top for x, top in zip(signal, vdd, strict=False)), default=0.0)
        below = max((bottom - x for x, bottom in zip(signal, vss, strict=False)), default=0.0)
        excess = max(above, below)
        if excess > CMOS_INPUT_MARGIN_V:
            yield (
                excess,
                _Finding(
                    Severity.WARNING,
                    "input_beyond_rails",
                    f"{name} input '{pin}' goes {format_si(excess, 'V')} beyond its supply rails "
                    f"{s.where(signal)}; its protection diodes would conduct. "
                    "Scale the input down or add "
                    "a series resistor of at least 10 k.",
                ),
            )
