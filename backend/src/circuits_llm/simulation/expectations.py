"""Verify a circuit's expectations (what it must do) on its simulation results.

Each expectation is checked on the first analysis that records its signals, preferring
the transient, then a DC sweep, then the operating point. Only samples where the
``when`` condition holds count, and 90% of them must pass so that switching edges and
settling do not cause false failures. Currents are compared as magnitudes, so the
model never has to reason about SPICE sign conventions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from circuits_llm.domain import CATALOG, Circuit, Expectation, Issue, Severity, format_si
from circuits_llm.domain.erc import stimulus_quantities
from circuits_llm.domain.expectations import (
    Comparison,
    ExpectationSyntaxError,
    Signal,
    parse_check,
    parse_condition,
    parse_signal,
)

from .results import (
    AnalysisResult,
    ExpectationResult,
    OperatingPointResult,
    SimulationResult,
)

PASS_FRACTION: Final = 0.9
_ANALYSIS_ORDER: Final = ("tran", "dc", "op")
_ANALYSIS_NAMES: Final = {"tran": "transient", "dc": "DC sweep", "op": "operating point"}


@dataclass(frozen=True, slots=True)
class _Samples:
    analysis: str
    x_name: str
    x_unit: str
    x: Sequence[float]
    series: dict[tuple[str, str], Sequence[float]]  # (kind, target lower-case) -> values

    def get(self, signal: Signal) -> Sequence[float] | None:
        values = self.series.get((signal.kind, signal.target.lower()))
        if values is None or signal.kind != "current":
            return values
        return [abs(v) for v in values]


def _samples(analysis: AnalysisResult) -> _Samples | None:
    if isinstance(analysis, OperatingPointResult):
        series: dict[tuple[str, str], Sequence[float]] = {}
        series |= {("voltage", n.lower()): [v] for n, v in analysis.node_voltages.items()}
        series |= {("current", c.lower()): [i] for c, i in analysis.branch_currents.items()}
        return _Samples("op", "", "", [0.0], series)
    if analysis.type == "ac":
        return None
    series = {}
    for trace in analysis.traces:
        if trace.net:
            series[("voltage", trace.net.lower())] = trace.values
        elif trace.component:
            series[("current", trace.component.lower())] = trace.values
        elif trace.stimulus_of:
            series[("stimulus", trace.stimulus_of.lower())] = trace.values
    return _Samples(analysis.type, analysis.x.name, analysis.x.unit, analysis.x.values, series)


def _unit(circuit: Circuit, signal: Signal) -> str:
    if signal.kind == "voltage":
        return "V"
    if signal.kind == "current":
        return "A"
    component = circuit.component(signal.target)
    spec = CATALOG[component.kind].stimulus if component is not None else None
    return spec.unit if spec is not None else ""


def check_expectations(
    circuit: Circuit, result: SimulationResult
) -> tuple[list[ExpectationResult], list[Issue]]:
    """Results for the UI, plus an ERROR issue per failed expectation for the repair loop."""
    if not result.ok or not circuit.expectations:
        return [], []
    available = [s for a in result.analyses if (s := _samples(a)) is not None]
    available.sort(key=lambda s: _ANALYSIS_ORDER.index(s.analysis))
    outcomes = [_evaluate(circuit, e, available) for e in circuit.expectations]
    issues = [
        Issue(
            severity=Severity.ERROR,
            code="expectation_failed",
            message=f"Expectation '{o.description}' failed: {o.detail}",
        )
        for o in outcomes
        if not o.passed
    ]
    return outcomes, issues


def _evaluate(
    circuit: Circuit, expectation: Expectation, available: Sequence[_Samples]
) -> ExpectationResult:
    def outcome(passed: bool, detail: str) -> ExpectationResult:
        return ExpectationResult(description=expectation.description, passed=passed, detail=detail)

    quantities = stimulus_quantities()
    try:
        signal = parse_signal(expectation.signal, quantities)
        check = parse_check(expectation.check)
        when = (
            parse_condition(expectation.when, quantities) if expectation.when is not None else None
        )
    except ExpectationSyntaxError as exc:
        return outcome(False, str(exc))

    needed = [signal] if when is None else [signal, when[0]]
    samples = next((s for s in available if all(s.get(n) is not None for n in needed)), None)
    if samples is None:
        return outcome(
            False,
            f"{', '.join(map(str, needed))} is not recorded by any analysis; add a 'tran' "
            "(or 'op') analysis that covers it.",
        )
    values = samples.get(signal) or []
    selected = _select(values, samples, when)
    analysis = _ANALYSIS_NAMES[samples.analysis]
    condition = f" while {expectation.when}" if expectation.when else ""
    if not selected:
        return outcome(
            False,
            f"'{expectation.when}' never happens in the {analysis}; make the stimulus or "
            "sweep reach that condition.",
        )
    unit = _unit(circuit, signal)
    passing = sum(check.holds(v) for _, v in selected)
    wanted = f"{check.operator} {format_si(check.value, unit)}"
    if passing >= PASS_FRACTION * len(selected):
        return outcome(True, f"{signal} stayed {wanted}{condition}.")
    index, worst = _worst(selected, check)
    at = _location(samples, index)
    return outcome(
        False,
        f"{signal} was {format_si(worst, unit)} (needs {wanted}){condition}{at}, in the "
        f"{analysis}. Change the circuit so it does this.",
    )


def _select(
    values: Sequence[float], samples: _Samples, when: tuple[Signal, Comparison] | None
) -> list[tuple[int, float]]:
    if when is None:
        return list(enumerate(values))
    condition_values = samples.get(when[0]) or []
    return [
        (i, v)
        for i, (v, c) in enumerate(zip(values, condition_values, strict=False))
        if when[1].holds(c)
    ]


def _worst(selected: Sequence[tuple[int, float]], check: Comparison) -> tuple[int, float]:
    if check.operator in (">", ">="):
        return min(selected, key=lambda item: item[1])
    return max(selected, key=lambda item: item[1])


def _location(samples: _Samples, index: int) -> str:
    if samples.analysis == "op" or index >= len(samples.x):
        return ""
    name = "t" if samples.analysis == "tran" else samples.x_name
    return f" (e.g. at {name} = {format_si(samples.x[index], samples.x_unit)})"
