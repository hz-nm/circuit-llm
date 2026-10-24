"""Circuit -> ngspice deck.

The deck is derived from LLM output, so only validated identifiers and finite
numbers are written into it; the circuit title is the only free text and is
emitted as a single sanitised comment line.

Analyses run from a ``.control`` block: the operating point always runs first
(its node voltages annotate the schematic), then every requested analysis, each
written to its own ASCII raw file so results map back unambiguously.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Final

from circuits_llm.domain import (
    CATALOG,
    GROUND_NET,
    AcSweep,
    Analysis,
    Circuit,
    Component,
    ComponentKind,
    ComponentSpec,
    DcSweep,
    OperatingPoint,
    PulseWave,
    PwlWave,
    SineWave,
    Transient,
)

from .library import (
    LOGIC_FAMILIES,
    LOGIC_KINDS,
    OPAMP_MODELS,
    DeviceModel,
    discrete_model,
    library_text,
    logic_subckt_name,
    opamp_subckt_name,
    zener_model,
)

SPICE_GROUND: Final = "0"
MAX_DEFAULT_TRACES: Final = 8
MAX_NODE_TRACES: Final = 64  # node voltages recorded for schematic animation
MAX_METERED_COMPONENTS: Final = 64  # two-pin parts whose current is always recorded
# Transient output is interpolated onto a grid of at most this many points (the
# solver's maximum internal step is still the requested step_time).
MAX_TRAN_OUTPUT_POINTS: Final = 100_000
MAX_TITLE_LENGTH: Final = 120
OP_RAW_FILE: Final = "op.raw"

_NAME_RE: Final = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_UNPRINTABLE_RE: Final = re.compile(r"[^\x20-\x7e]+")

_ELEMENT_LETTER: Final[dict[ComponentKind, str]] = {
    ComponentKind.RESISTOR: "R",
    ComponentKind.CAPACITOR: "C",
    ComponentKind.INDUCTOR: "L",
    ComponentKind.VOLTAGE_SOURCE: "V",
    ComponentKind.CURRENT_SOURCE: "I",
    ComponentKind.DIODE: "D",
    ComponentKind.LED: "D",
    ComponentKind.ZENER: "D",
    ComponentKind.NPN: "Q",
    ComponentKind.PNP: "Q",
    ComponentKind.NMOS: "M",
    ComponentKind.PMOS: "M",
    ComponentKind.OPAMP: "X",
    ComponentKind.LAMP: "R",
    ComponentKind.NOT_GATE: "X",
    ComponentKind.AND_GATE: "X",
    ComponentKind.OR_GATE: "X",
    ComponentKind.NAND_GATE: "X",
    ComponentKind.NOR_GATE: "X",
    ComponentKind.XOR_GATE: "X",
    ComponentKind.SCHMITT_INVERTER: "X",
}
_PASSIVES: Final = frozenset(
    {ComponentKind.RESISTOR, ComponentKind.CAPACITOR, ComponentKind.INDUCTOR}
)
_OPAMP_SUPPLY_PINS: Final = ("v+", "v-")


class SpiceEmissionError(ValueError):
    """The circuit cannot be expressed as a SPICE deck (it should have failed the ERC)."""


@dataclass(frozen=True, slots=True)
class TraceSpec:
    """A vector to plot for sweep analyses."""

    vector: str  # lower-case ngspice vector name, e.g. "v(out)" or "i(vsense_r1)"
    name: str  # display name, e.g. "V(OUT)" or "I(R1)"
    unit: str  # "V" or "A"
    net: str | None = None  # set for node-voltage traces
    probed: bool = True  # False: recorded only for animation and the multimeter
    component: str | None = None  # set for component-current traces


def _voltage_trace(net: str, *, probed: bool) -> TraceSpec:
    return TraceSpec(f"v({net.lower()})", f"V({net})", "V", net=net, probed=probed)


def _current_trace(vector: str, component: Component, *, probed: bool) -> TraceSpec:
    return TraceSpec(vector, f"I({component.id})", "A", probed=probed, component=component.id)


@dataclass(frozen=True, slots=True)
class PlannedAnalysis:
    analysis: Analysis
    command: str  # ngspice control command, e.g. "tran 1e-06 0.001 0 1e-06"
    raw_file: str
    axis_name: str
    axis_unit: str
    log_scale: bool = False


@dataclass(frozen=True, slots=True)
class SpiceDeck:
    """The deck text plus everything needed to map ngspice output back to the circuit."""

    text: str
    analyses: tuple[PlannedAnalysis, ...]  # operating point first
    traces: tuple[TraceSpec, ...]
    node_voltages: dict[str, str] = field(default_factory=dict[str, str])  # "v(n1)" -> net
    branch_currents: dict[str, str] = field(default_factory=dict[str, str])  # "i(v1)" -> id
    node_names: dict[str, str] = field(default_factory=dict[str, str])  # spice node -> net


# --------------------------------------------------------------------------- helpers


def _num(value: float) -> str:
    if not math.isfinite(value):
        raise SpiceEmissionError(f"non-finite number {value!r} cannot be simulated")
    return f"{value:.12g}"


def _checked_name(name: str, what: str) -> str:
    if _NAME_RE.fullmatch(name) is None:
        raise SpiceEmissionError(f"{what} '{name[:40]}' is not a valid identifier")
    return name


def _sanitize_title(title: str) -> str:
    return _UNPRINTABLE_RE.sub(" ", title).strip()[:MAX_TITLE_LENGTH]


def _unique(base: str, used: set[str]) -> str:
    candidate, suffix = base, 2
    while candidate.lower() in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate.lower())
    return candidate


def _node(net: str) -> str:
    return SPICE_GROUND if net == GROUND_NET else _checked_name(net, "Net name")


# --------------------------------------------------------------------------- naming


@dataclass(slots=True)
class _Names:
    element: dict[str, str]  # component id -> SPICE element name
    sense_source: dict[str, str]  # probed component id -> sense source name
    sense_node: dict[str, str]  # probed component id -> node between sense source and pin


def _assign_names(circuit: Circuit, current_probes: list[Component]) -> _Names:
    seen_ids: set[str] = set()
    used: set[str] = set()
    element: dict[str, str] = {}
    for component in circuit.components:
        _checked_name(component.id, "Component id")
        if component.id.lower() in seen_ids:
            raise SpiceEmissionError(f"duplicate component id '{component.id}'")
        seen_ids.add(component.id.lower())
        letter = _ELEMENT_LETTER[component.kind]
        base = component.id if component.id.upper().startswith(letter) else letter + component.id
        element[component.id] = _unique(base, used)

    used_nodes = {net.lower() for net in circuit.nets()} | {SPICE_GROUND}
    sense_source: dict[str, str] = {}
    sense_node: dict[str, str] = {}
    for component in current_probes:
        name = element[component.id]
        sense_source[component.id] = _unique(f"VSENSE_{name}", used)
        sense_node[component.id] = _unique(f"{name}_sense", used_nodes)
    return _Names(element, sense_source, sense_node)


def _check_net_case(circuit: Circuit) -> None:
    folded: dict[str, str] = {}
    for net in circuit.nets():
        other = folded.setdefault(net.lower(), net)
        if other != net:
            raise SpiceEmissionError(f"nets '{other}' and '{net}' differ only in letter case")


# --------------------------------------------------------------------------- probes


def _current_probe_targets(circuit: Circuit) -> list[Component]:
    targets: dict[str, Component] = {}
    for probe in circuit.probes:
        if probe.kind != "current":
            continue
        component = circuit.component(probe.target)
        if component is None:
            raise SpiceEmissionError(f"current probe target '{probe.target}' is not a component")
        if len(CATALOG[component.kind].pins) != 2:
            raise SpiceEmissionError(
                f"current probes need a two-pin component; '{component.id}' is not"
            )
        targets.setdefault(component.id, component)
    return list(targets.values())


def _metered_components(circuit: Circuit, probed: list[Component]) -> list[Component]:
    """Probed parts plus every other two-pin part (bounded) so the multimeter has currents.

    Voltage sources report their own branch current and need no sense source.
    """
    metered = {c.id: c for c in probed}
    for component in circuit.components:
        if len(metered) >= MAX_METERED_COMPONENTS:
            break
        two_pin = len(CATALOG[component.kind].pins) == 2
        if two_pin and component.kind is not ComponentKind.VOLTAGE_SOURCE:
            metered.setdefault(component.id, component)
    return list(metered.values())


def _current_vector(component: Component, names: _Names) -> str:
    if component.kind is ComponentKind.VOLTAGE_SOURCE:
        return f"i({names.element[component.id].lower()})"
    return f"i({names.sense_source[component.id].lower()})"


def _traces(circuit: Circuit, names: _Names) -> tuple[TraceSpec, ...]:
    """Probed signals first, then every other node voltage (bounded) for animation."""
    nets = [net for net in circuit.nets() if net != GROUND_NET]
    traces: dict[str, TraceSpec] = {}
    if not circuit.probes:
        for net in nets[:MAX_DEFAULT_TRACES]:
            traces[net] = _voltage_trace(net, probed=True)

    for probe in circuit.probes:
        if probe.kind == "voltage":
            net = next((n for n in nets if n.lower() == probe.target.lower()), None)
            if net is None and probe.target.lower() != GROUND_NET.lower():
                raise SpiceEmissionError(f"voltage probe target '{probe.target}' is not a net")
            if net is not None:
                traces.setdefault(net, _voltage_trace(net, probed=True))
            continue
        component = circuit.component(probe.target)
        assert component is not None  # validated by _current_probe_targets
        vector = _current_vector(component, names)
        traces.setdefault(vector, _current_trace(vector, component, probed=True))

    for net in nets[:MAX_NODE_TRACES]:
        traces.setdefault(net, _voltage_trace(net, probed=False))
    for component in circuit.components:
        if component.id in names.sense_source or component.kind is ComponentKind.VOLTAGE_SOURCE:
            vector = _current_vector(component, names)
            traces.setdefault(vector, _current_trace(vector, component, probed=False))
    return tuple(traces.values())


# --------------------------------------------------------------------------- elements


def _pin_nodes(component: Component, spec: ComponentSpec, names: _Names) -> list[str]:
    nodes: list[str] = []
    for index, pin in enumerate(spec.pins):
        net = component.pins.get(pin.name)
        if net is None:
            if pin.optional:
                continue
            raise SpiceEmissionError(f"{component.id}: pin '{pin.name}' is not connected")
        sense = names.sense_node.get(component.id)
        nodes.append(sense if index == 0 and sense is not None else _node(net))
    return nodes


def _source_spec(component: Component) -> str:
    match component.waveform:
        case SineWave() as sine:
            dc = sine.offset
            wave = (
                f" SIN({_num(sine.offset)} {_num(sine.amplitude)} {_num(sine.frequency)} "
                f"{_num(sine.delay)} 0 {_num(sine.phase_deg)})"
            )
        case PulseWave() as pulse:
            dc = pulse.initial
            wave = (
                f" PULSE({_num(pulse.initial)} {_num(pulse.pulsed)} {_num(pulse.delay)} "
                f"{_num(pulse.rise)} {_num(pulse.fall)} {_num(pulse.width)} {_num(pulse.period)})"
            )
        case PwlWave() as pwl:
            dc = pwl.points[0][1]
            pairs = " ".join(f"{_num(t)} {_num(v)}" for t, v in pwl.points)
            wave = f" PWL({pairs})"
        case None:
            dc, wave = 0.0, ""
    if component.value is not None:
        dc = component.value
    ac = f" AC {_num(component.ac_magnitude)}" if component.ac_magnitude is not None else ""
    return f"DC {_num(dc)}{ac}{wave}"


def _model_for(component: Component, spec: ComponentSpec, element: str) -> DeviceModel:
    if component.kind is ComponentKind.ZENER:
        if component.value is None or component.value <= 0:
            raise SpiceEmissionError(f"{component.id}: zener needs a positive breakdown voltage")
        return zener_model(element, component.value)
    model_name = component.model or spec.default_model
    model = discrete_model(component.kind, model_name) if model_name is not None else None
    if model is None:
        raise SpiceEmissionError(f"{component.id}: unknown model '{model_name}'")
    return model


def _opamp_model(component: Component, spec: ComponentSpec) -> tuple[str, bool]:
    model = component.model or spec.default_model
    if model is None or model not in OPAMP_MODELS:
        raise SpiceEmissionError(f"{component.id}: unknown op-amp model '{model}'")
    connected = [pin in component.pins for pin in _OPAMP_SUPPLY_PINS]
    if any(connected) and not all(connected):
        raise SpiceEmissionError(f"{component.id}: connect both supply pins or neither")
    return model, all(connected)


def _logic_model(component: Component, spec: ComponentSpec) -> tuple[str, bool]:
    model = component.model or spec.default_model
    if model is None or model not in LOGIC_FAMILIES:
        raise SpiceEmissionError(f"{component.id}: unknown logic family '{model}'")
    assert spec.supply_pins is not None
    connected = [pin in component.pins for pin in spec.supply_pins]
    if any(connected) and not all(connected):
        raise SpiceEmissionError(f"{component.id}: connect both supply pins or neither")
    return model, all(connected)


def _lamp_resistance(component: Component, spec: ComponentSpec) -> float:
    """A lamp draws its rated power at its rated voltage: R = V^2 / P."""
    rated = component.model or spec.default_model
    if rated is None or not rated.endswith("V"):
        raise SpiceEmissionError(f"{component.id}: unknown lamp rating '{rated}'")
    if component.value is None or component.value <= 0:
        raise SpiceEmissionError(f"{component.id}: lamp power must be a positive number")
    return float(rated[:-1]) ** 2 / component.value


@dataclass(slots=True)
class _Emitted:
    lines: list[str] = field(default_factory=list[str])
    models: list[DeviceModel] = field(default_factory=list[DeviceModel])
    opamps: list[tuple[str, bool]] = field(default_factory=list[tuple[str, bool]])
    logic: list[tuple[ComponentKind, str, bool]] = field(
        default_factory=list[tuple[ComponentKind, str, bool]]
    )


def _emit_component(component: Component, names: _Names, out: _Emitted) -> None:
    spec = CATALOG[component.kind]
    element = names.element[component.id]
    nodes = " ".join(_pin_nodes(component, spec, names))
    if component.kind in _PASSIVES:
        if component.value is None or component.value <= 0:
            raise SpiceEmissionError(f"{component.id}: value must be a positive number")
        out.lines.append(f"{element} {nodes} {_num(component.value)}")
    elif spec.is_source:
        out.lines.append(f"{element} {nodes} {_source_spec(component)}")
    elif component.kind is ComponentKind.OPAMP:
        model, supplies = _opamp_model(component, spec)
        out.opamps.append((model, supplies))
        out.lines.append(f"{element} {nodes} {opamp_subckt_name(model, supplies)}")
    elif component.kind in LOGIC_KINDS:
        model, supplies = _logic_model(component, spec)
        out.logic.append((component.kind, model, supplies))
        out.lines.append(f"{element} {nodes} {logic_subckt_name(component.kind, model, supplies)}")
    elif component.kind is ComponentKind.LAMP:
        out.lines.append(f"{element} {nodes} {_num(_lamp_resistance(component, spec))}")
    else:
        device = _model_for(component, spec, element)
        out.models.append(device)
        out.lines.append(f"{element} {nodes} {device.spice_name}")

    sense = names.sense_source.get(component.id)
    if sense is not None:
        first_net = component.pins[spec.pins[0].name]
        out.lines.append(f"{sense} {_node(first_net)} {names.sense_node[component.id]} DC 0")


# --------------------------------------------------------------------------- analyses


def _plan(analysis: Analysis, index: int, circuit: Circuit, names: _Names) -> PlannedAnalysis:
    raw_file = f"analysis{index}.raw"
    match analysis:
        case OperatingPoint():
            return PlannedAnalysis(analysis, "op", OP_RAW_FILE, "", "")
        case DcSweep():
            source = circuit.component(analysis.source)
            if source is None or not CATALOG[source.kind].is_source:
                raise SpiceEmissionError(f"DC sweep source '{analysis.source}' is not a source")
            step = analysis.step if analysis.stop >= analysis.start else -analysis.step
            unit = "V" if source.kind is ComponentKind.VOLTAGE_SOURCE else "A"
            command = (
                f"dc {names.element[source.id]} {_num(analysis.start)} {_num(analysis.stop)} "
                f"{_num(step)}"
            )
            return PlannedAnalysis(analysis, command, raw_file, source.id, unit)
        case AcSweep():
            command = (
                f"ac dec {analysis.points_per_decade} {_num(analysis.start_frequency)} "
                f"{_num(analysis.stop_frequency)}"
            )
            return PlannedAnalysis(analysis, command, raw_file, "frequency", "Hz", log_scale=True)
        case Transient():
            span = analysis.stop_time - analysis.start_time
            output_step = max(analysis.effective_step, span / MAX_TRAN_OUTPUT_POINTS)
            command = (
                f"tran {_num(output_step)} {_num(analysis.stop_time)} "
                f"{_num(analysis.start_time)} {_num(analysis.effective_step)}"
            )
            return PlannedAnalysis(analysis, command, raw_file, "time", "s")


def _plan_all(circuit: Circuit, names: _Names) -> tuple[PlannedAnalysis, ...]:
    planned = [_plan(OperatingPoint(), 0, circuit, names)]
    sweeps = [a for a in circuit.analyses if not isinstance(a, OperatingPoint)]
    planned += [_plan(a, i, circuit, names) for i, a in enumerate(sweeps, start=1)]
    return tuple(planned)


def _control_block(analyses: tuple[PlannedAnalysis, ...], traces: tuple[TraceSpec, ...]) -> str:
    operating_point, *sweeps = analyses
    lines = [
        ".control",
        "set filetype=ascii",
        operating_point.command,  # saves every vector
        f"write {operating_point.raw_file}",
    ]
    if sweeps and traces:  # sweeps keep only the plotted vectors
        lines.append("save " + " ".join(t.vector for t in traces))
    for planned in sweeps:
        lines += [planned.command, f"write {planned.raw_file}"]
    lines.append(".endc")
    return "\n".join(lines)


# --------------------------------------------------------------------------- public API


def _maps(circuit: Circuit, names: _Names) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    nets = [net for net in circuit.nets() if net != GROUND_NET]
    node_voltages = {f"v({net.lower()})": net for net in nets}
    node_names = {net.lower(): net for net in nets} | {SPICE_GROUND: GROUND_NET}
    for component_id, node in names.sense_node.items():
        component = circuit.component(component_id)
        assert component is not None
        node_names[node.lower()] = component.pins[CATALOG[component.kind].pins[0].name]
    currents = {
        f"i({names.element[c.id].lower()})": c.id
        for c in circuit.components
        if c.kind is ComponentKind.VOLTAGE_SOURCE
    }
    currents |= {f"i({src.lower()})": cid for cid, src in names.sense_source.items()}
    return node_voltages, currents, node_names


def _iter_lines(circuit: Circuit, names: _Names) -> Iterator[str]:
    emitted = _Emitted()
    for component in circuit.components:
        _emit_component(component, names, emitted)
    yield from emitted.lines
    library = library_text(emitted.models, emitted.opamps, emitted.logic)
    if library:
        yield library


def to_spice(circuit: Circuit) -> SpiceDeck:
    """Translate a circuit into an ngspice deck. Raises :class:`SpiceEmissionError`."""
    _check_net_case(circuit)
    metered = _metered_components(circuit, _current_probe_targets(circuit))
    names = _assign_names(circuit, metered)
    traces = _traces(circuit, names)
    analyses = _plan_all(circuit, names)
    node_voltages, currents, node_names = _maps(circuit, names)
    text = "\n".join(
        [
            f"* {_sanitize_title(circuit.title)}",
            *_iter_lines(circuit, names),
            ".options interp",
            _control_block(analyses, traces),
            ".end",
            "",
        ]
    )
    return SpiceDeck(text, analyses, traces, node_voltages, currents, node_names)
