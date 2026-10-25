"""Electrical rule check (ERC).

``check_circuit`` returns *every* problem it finds rather than stopping at the
first one, so a single repair round-trip to the LLM can fix them all. Messages
are written to be directly actionable by a language model.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from enum import StrEnum
from typing import Final

from .arduino import rule_condition
from .catalog import ARDUINO_DIGITAL_PINS, ARDUINO_PWM_PINS, CATALOG, ComponentKind, ComponentSpec
from .circuit import (
    GROUND_NET,
    AcSweep,
    Circuit,
    Component,
    DcSweep,
    PulseWave,
    PwlWave,
    SineWave,
    StrictModel,
    Transient,
    Waveform,
)
from .expectations import (
    ExpectationSyntaxError,
    Signal,
    parse_check,
    parse_condition,
    parse_signal,
)

MAX_TRANSIENT_POINTS: Final = 200_000
MAX_DC_POINTS: Final = 10_000
_POINT_TOLERANCE: Final = 1 + 1e-9  # so exactly-at-limit requests survive float rounding
_TWO_PIN_KINDS: Final = frozenset(k for k, s in CATALOG.items() if len(s.pins) == 2)
_METERED_THREE_PIN: Final = frozenset(
    {ComponentKind.NPN, ComponentKind.PNP, ComponentKind.NMOS, ComponentKind.PMOS}
)


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Issue(StrictModel):
    severity: Severity
    code: str
    message: str
    component_id: str | None = None
    net: str | None = None


def has_errors(issues: Iterable[Issue]) -> bool:
    return any(issue.severity is Severity.ERROR for issue in issues)


def check_circuit(circuit: Circuit) -> list[Issue]:
    issues = [
        *_check_components(circuit),
        *_check_nets(circuit),
        *_check_dc_paths(circuit),
        *_check_voltage_loops(circuit),
        *_check_analyses(circuit),
        *_check_probes(circuit),
        *_check_expectations(circuit),
    ]
    return sorted(issues, key=lambda i: i.severity is not Severity.ERROR)


def _error(
    code: str, message: str, *, component: str | None = None, net: str | None = None
) -> Issue:
    return Issue(
        severity=Severity.ERROR, code=code, message=message, component_id=component, net=net
    )


def _warning(
    code: str, message: str, *, component: str | None = None, net: str | None = None
) -> Issue:
    return Issue(
        severity=Severity.WARNING, code=code, message=message, component_id=component, net=net
    )


def _quoted(names: Iterable[str]) -> str:
    return ", ".join(f"'{n}'" for n in names)


# --------------------------------------------------------------------------- components


def _check_components(circuit: Circuit) -> Iterator[Issue]:
    seen: set[str] = set()
    for component in circuit.components:
        key = component.id.lower()
        if key in seen:
            yield _error(
                "duplicate_id",
                f"Component id '{component.id}' is used more than once; ids must be unique "
                "(case-insensitive).",
                component=component.id,
            )
        seen.add(key)
        yield from _check_component(component, CATALOG[component.kind])


def _check_component(c: Component, spec: ComponentSpec) -> Iterator[Issue]:
    name = f"{c.id} ({spec.display_name.lower()})"

    unknown = [p for p in c.pins if p not in spec.pin_names]
    if unknown:
        yield _error(
            "unknown_pin",
            f"{name}: pin(s) {_quoted(unknown)} do not exist; valid pins are "
            f"{_quoted(spec.pin_names)}.",
            component=c.id,
        )
    missing = [p for p in spec.required_pins if p not in c.pins]
    if missing:
        yield _error(
            "missing_pin",
            f"{name}: pin(s) {_quoted(missing)} are not connected; every one of "
            f"{_quoted(spec.required_pins)} must be connected to a net.",
            component=c.id,
        )

    if spec.value_required and c.value is None:
        yield _error(
            "missing_value",
            f"{name}: a value is required ({spec.value_description}).",
            component=c.id,
        )
    if spec.value_required and c.value is not None and c.value <= 0:
        yield _error(
            "non_positive_value", f"{name}: value must be greater than zero.", component=c.id
        )
    if spec.value_unit is None and c.value is not None:
        yield _warning(
            "unused_value",
            f"{name}: this kind takes no value (it is set by 'model'); the value is ignored.",
            component=c.id,
        )

    if spec.models:
        if c.model is not None and c.model not in spec.models:
            yield _error(
                "unknown_model",
                f"{name}: model '{c.model}' is not available; "
                f"choose one of {_quoted(spec.models)}.",
                component=c.id,
            )
    elif c.model is not None:
        yield _warning(
            "unused_model", f"{name}: this kind has no models; 'model' is ignored.", component=c.id
        )

    if spec.is_source:
        if c.value is None and c.waveform is None and c.ac_magnitude is None:
            yield _error(
                "source_without_value",
                f"{name}: give the source a DC 'value', a 'waveform', or an 'ac_magnitude'.",
                component=c.id,
            )
        if c.waveform is not None and c.value not in (None, 0.0):
            yield _warning(
                "value_and_waveform",
                f"{name}: both a DC value and a waveform are set; the waveform takes precedence "
                "in transient analysis.",
                component=c.id,
            )
    elif c.waveform is not None or c.ac_magnitude is not None:
        hint = (
            " An arduino_uno is programmed with 'behavior' instead; the environment goes on "
            "the sensor as its 'stimulus'."
            if c.kind is ComponentKind.ARDUINO_UNO
            else " Sensors take a 'stimulus' instead."
        )
        yield _error(
            "waveform_on_non_source",
            f"{name}: remove 'waveform': only voltage_source and current_source may have "
            f"'waveform' or 'ac_magnitude'.{hint}",
            component=c.id,
        )

    yield from _check_stimulus(c, spec, name)
    yield from _check_behavior(c, name)

    connected = [net for pin, net in c.pins.items() if pin in spec.pin_names]
    if len(connected) >= 2 and len(set(connected)) == 1:
        shorted_error = c.kind is ComponentKind.VOLTAGE_SOURCE
        yield (_error if shorted_error else _warning)(
            "shorted_component",
            f"{name}: all pins are connected to the same net '{connected[0]}', so it is shorted.",
            component=c.id,
            net=connected[0],
        )

    if spec.supply_pins is not None:
        positive, negative = spec.supply_pins
        if (positive in c.pins) != (negative in c.pins):
            yield _error(
                "partial_supply",
                f"{name}: connect both supply pins '{positive}' and '{negative}' (use GND for "
                f"'{negative}' on a single supply), or neither for an ideal part.",
                component=c.id,
            )


def _check_behavior(c: Component, name: str) -> Iterator[Issue]:
    if c.kind is not ComponentKind.ARDUINO_UNO:
        if c.behavior:
            yield _error(
                "behavior_on_non_microcontroller",
                f"{name}: only an arduino_uno takes 'behavior'; remove it.",
                component=c.id,
            )
        return
    seen: set[str] = set()
    for b in c.behavior or []:
        where = f"{name} pin '{b.pin}'"
        if b.pin not in ARDUINO_DIGITAL_PINS:
            yield _error(
                "bad_behavior_pin",
                f"{where}: behaviours drive digital pins D2-D13 (analog pins A0-A5 are "
                "inputs read by a 'rule').",
                component=c.id,
            )
            continue
        if b.pin in seen:
            yield _error(
                "duplicate_behavior", f"{where}: has more than one behaviour.", component=c.id
            )
        seen.add(b.pin)
        if b.pin not in c.pins:
            yield _warning(
                "behavior_on_unconnected_pin",
                f"{where}: has a behaviour but is not connected.",
                component=c.id,
            )
        if b.output == "pwm" and b.pin not in ARDUINO_PWM_PINS:
            yield _error(
                "not_a_pwm_pin",
                f"{where}: PWM works only on D3, D5, D6, D9, D10 and D11.",
                component=c.id,
            )
        if b.output == "blink" and b.period is None:
            yield _error(
                "missing_period", f"{where}: a blink needs 'period' in seconds.", component=c.id
            )
        if b.output == "pwm" and b.duty is None:
            yield _error(
                "missing_duty", f"{where}: PWM needs 'duty' between 0 and 1.", component=c.id
            )
        if b.output == "rule":
            try:
                signal, _, _ = rule_condition(b)
            except ExpectationSyntaxError as exc:
                yield _error("bad_rule", f"{where}: {exc}.", component=c.id)
                continue
            if signal.target not in c.pins:
                yield _error(
                    "rule_input_unconnected",
                    f"{where}: its rule reads {signal.target}, which is not connected.",
                    component=c.id,
                )
    for pin in ARDUINO_DIGITAL_PINS:
        if pin in c.pins and pin not in seen:
            yield _error(
                "pin_without_behavior",
                f"{name} pin '{pin}' is connected but has no behaviour, so it does nothing. "
                f'Inside the "{c.id}" component object add the key "behavior", for example '
                f'"behavior": [{{"pin": "{pin}", "output": "rule", "when": "A0 < 2.3"}}] '
                "(pick the analog input and the threshold in volts it should react to), or "
                'use "output": "high", "blink" or "pwm".',
                component=c.id,
            )


def stimulus_extremes(stimulus: float | Waveform) -> tuple[float, float]:
    """The lowest and highest value a stimulus reaches."""
    match stimulus:
        case SineWave():
            return stimulus.offset - abs(stimulus.amplitude), stimulus.offset + abs(
                stimulus.amplitude
            )
        case PulseWave():
            return min(stimulus.initial, stimulus.pulsed), max(stimulus.initial, stimulus.pulsed)
        case PwlWave():
            values = [v for _, v in stimulus.points]
            return min(values), max(values)
        case _:
            return stimulus, stimulus


def _check_stimulus(c: Component, spec: ComponentSpec, name: str) -> Iterator[Issue]:
    if c.stimulus is None:
        return
    if spec.stimulus is None:
        yield _error(
            "stimulus_on_non_sensor",
            f"{name}: only sensors take a 'stimulus'; remove it.",
            component=c.id,
        )
        return
    low, high = stimulus_extremes(c.stimulus)
    allowed = spec.stimulus
    if low < allowed.minimum or high > allowed.maximum:
        unit = f" {allowed.unit}" if allowed.unit else ""
        yield _error(
            "stimulus_out_of_range",
            f"{name}: the {allowed.quantity} stimulus must stay between {allowed.minimum:g} "
            f"and {allowed.maximum:g}{unit} ({allowed.hint}); it reaches {low:g}..{high:g}.",
            component=c.id,
        )


# --------------------------------------------------------------------------- nets


def _check_nets(circuit: Circuit) -> Iterator[Issue]:
    nets = circuit.nets()
    if GROUND_NET not in nets:
        yield _error(
            "no_ground",
            f"No component is connected to ground. Connect the circuit's reference node to the "
            f"net '{GROUND_NET}'.",
        )

    by_folded: dict[str, list[str]] = {}
    for net in nets:
        by_folded.setdefault(net.lower(), []).append(net)
    for spellings in by_folded.values():
        if len(spellings) > 1:
            yield _error(
                "net_case_conflict",
                f"Nets {_quoted(spellings)} differ only in letter case; the simulator treats "
                "them as one net. Use a single spelling.",
                net=spellings[0],
            )

    for net, refs in nets.items():
        if len(refs) == 1 and net != GROUND_NET:
            ref = refs[0]
            yield _warning(
                "dangling_net",
                f"Net '{net}' is only connected to {ref.component_id}.{ref.pin}; it may be a "
                "typo or a missing connection.",
                component=ref.component_id,
                net=net,
            )


class _DisjointSet:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self._parent.setdefault(item, item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:  # path compression
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> bool:
        """Join the sets of ``a`` and ``b``; return False if they were already joined."""
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return False
        self._parent[root_a] = root_b
        return True


def _check_dc_paths(circuit: Circuit) -> Iterator[Issue]:
    """Every net needs a DC path to ground, otherwise the simulator's matrix is singular."""
    if GROUND_NET not in circuit.nets():
        return  # already reported as `no_ground`; every net would be flagged otherwise
    groups = _DisjointSet()
    for component in circuit.components:
        spec = CATALOG[component.kind]
        for a, b in spec.dc_paths:
            if a in component.pins and b in component.pins:
                groups.union(component.pins[a], component.pins[b])
        for pin in spec.driven_pins:
            if pin in component.pins:
                groups.union(component.pins[pin], GROUND_NET)

    ground = groups.find(GROUND_NET)
    for net in circuit.nets():
        if groups.find(net) != ground:
            yield _error(
                "no_dc_path",
                f"Net '{net}' has no DC path to {GROUND_NET} (it only connects through "
                "capacitors, current sources, MOSFET gates or op-amp inputs). Add a bias or "
                "bleed resistor (e.g. 1M to GND) or connect it properly.",
                net=net,
            )


def _check_voltage_loops(circuit: Circuit) -> Iterator[Issue]:
    """Voltage sources and inductors may not form a loop (e.g. two sources in parallel)."""
    groups = _DisjointSet()
    for component in circuit.components:
        if component.kind not in (ComponentKind.VOLTAGE_SOURCE, ComponentKind.INDUCTOR):
            continue
        nets = list(component.pins.values())
        if len(nets) != 2 or nets[0] == nets[1]:
            continue  # reported as missing pin / shorted component
        if not groups.union(nets[0], nets[1]):
            yield _error(
                "voltage_loop",
                f"{component.id} closes a loop made only of voltage sources and/or inductors "
                "(e.g. sources in parallel or a source shorted by an inductor). Add a series "
                "resistor or remove the redundant element.",
                component=component.id,
            )


# --------------------------------------------------------------------------- analyses


def _check_analyses(circuit: Circuit) -> Iterator[Issue]:
    sources = [c for c in circuit.components if CATALOG[c.kind].is_source]
    for analysis in circuit.analyses:
        match analysis:
            case DcSweep():
                target = circuit.component(analysis.source)
                if target is None or not CATALOG[target.kind].is_source:
                    yield _error(
                        "bad_sweep_source",
                        f"DC sweep source '{analysis.source}' must be the id of a voltage_source "
                        "or current_source; available: "
                        f"{_quoted(c.id for c in sources) or 'none'}.",
                    )
                points = abs(analysis.stop - analysis.start) / analysis.step
                if points > MAX_DC_POINTS * _POINT_TOLERANCE:
                    yield _error(
                        "sweep_too_fine",
                        f"DC sweep has {points:.0f} points (max {MAX_DC_POINTS}); increase 'step'.",
                    )
            case AcSweep():
                if not any(c.ac_magnitude for c in sources):
                    yield _error(
                        "ac_without_source",
                        "AC analysis needs at least one source with a non-zero 'ac_magnitude' "
                        "(typically 1) on the input signal source.",
                    )
            case Transient():
                points = (analysis.stop_time - analysis.start_time) / analysis.effective_step
                if points > MAX_TRANSIENT_POINTS * _POINT_TOLERANCE:
                    yield _error(
                        "transient_too_fine",
                        f"Transient analysis would produce {points:.0f} points (max "
                        f"{MAX_TRANSIENT_POINTS}); increase 'step_time' or reduce 'stop_time'.",
                    )
            case _:
                pass


def _check_probes(circuit: Circuit) -> Iterator[Issue]:
    nets = circuit.nets()
    for probe in circuit.probes:
        if probe.kind == "voltage":
            if probe.target not in nets:
                yield _error(
                    "unknown_probe_net",
                    f"Voltage probe target '{probe.target}' is not a net in the circuit; "
                    f"nets are {_quoted(sorted(nets))}.",
                    net=probe.target,
                )
            continue
        component = circuit.component(probe.target)
        if component is None:
            yield _error(
                "unknown_probe_component",
                f"Current probe target '{probe.target}' is not a component id.",
            )
        elif component.kind not in _TWO_PIN_KINDS and component.kind not in _METERED_THREE_PIN:
            # A plot request is cosmetic: skip it rather than fail the design.
            yield _warning(
                "unsupported_current_probe",
                f"Current probes work on two-pin components and transistors; '{probe.target}' "
                f"is a {CATALOG[component.kind].display_name.lower()}, so this probe is "
                "skipped. Probe a series resistor instead.",
                component=component.id,
            )


# --------------------------------------------------------------------------- expectations


def stimulus_quantities() -> frozenset[str]:
    return frozenset(s.stimulus.quantity for s in CATALOG.values() if s.stimulus is not None)


def _signal_problem(circuit: Circuit, signal: Signal) -> str | None:
    """Why ``signal`` cannot be measured in ``circuit``, or None if it can."""
    nets = circuit.nets()
    if signal.kind == "voltage":
        if signal.target.lower() in (n.lower() for n in nets):
            return None
        return f"net '{signal.target}' does not exist; nets are {_quoted(sorted(nets))}"
    component = circuit.component(signal.target)
    if component is None:
        return f"component '{signal.target}' does not exist"
    spec = CATALOG[component.kind]
    if signal.kind == "current":
        if len(spec.pins) == 2 or component.kind in _METERED_THREE_PIN:
            return None
        return f"the current of '{signal.target}' is not measured; use a series resistor"
    if spec.stimulus is None or spec.stimulus.quantity != signal.quantity:
        return f"'{signal.target}' has no {signal.quantity} stimulus"
    return None


def _check_expectations(circuit: Circuit) -> Iterator[Issue]:
    quantities = stimulus_quantities()
    for index, expectation in enumerate(circuit.expectations, start=1):
        where = f"Expectation {index} ('{expectation.description}')"
        try:
            signals = [parse_signal(expectation.signal, quantities)]
            parse_check(expectation.check)
            if expectation.when is not None:
                signals.append(parse_condition(expectation.when, quantities)[0])
        except ExpectationSyntaxError as exc:
            yield _error("bad_expectation", f"{where}: {exc}.")
            continue
        for signal in signals:
            problem = _signal_problem(circuit, signal)
            if problem is not None:
                yield _error("bad_expectation", f"{where}: {problem}.")
    if circuit.expectations and not circuit.analyses:
        yield _warning(
            "expectations_without_analysis",
            "Expectations are checked on the analyses; add an 'op' or 'tran' analysis.",
        )
