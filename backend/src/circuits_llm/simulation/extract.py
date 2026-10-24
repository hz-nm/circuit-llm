"""Map parsed ngspice raw plots back onto the circuit's names (nets and component ids)."""

from __future__ import annotations

import math
from typing import Final

from circuits_llm.domain import AcSweep, DcSweep, OperatingPoint, Transient

from .downsample import decimation_indices, take
from .raw import RawPlot
from .results import MAX_POINTS_PER_TRACE, Axis, OperatingPointResult, SweepResult, Trace
from .spice import PlannedAnalysis, SpiceDeck, TraceSpec

# A transient that stops short of stop_time by more than this fraction is truncated.
TRAN_END_TOLERANCE: Final = 1e-6

_EXPECTED_PLOTNAME: Final = {
    OperatingPoint: "operating point",
    DcSweep: "dc transfer characteristic",
    AcSweep: "ac analysis",
    Transient: "transient analysis",
}


class ExtractionError(ValueError):
    """The raw plot does not contain what the planned analysis should have produced."""


def _check_plot(plot: RawPlot, planned: PlannedAnalysis) -> None:
    expected = _EXPECTED_PLOTNAME[type(planned.analysis)]
    if not plot.plotname.lower().startswith(expected):
        raise ExtractionError(f"expected a '{expected}' plot, got '{plot.plotname}'")
    if plot.points == 0:
        raise ExtractionError("the analysis produced no data points")
    if isinstance(planned.analysis, Transient):
        reached, stop = plot.real[0][-1], planned.analysis.stop_time
        if reached < stop * (1 - TRAN_END_TOLERANCE):
            raise ExtractionError(f"transient analysis stopped early at t = {reached:.4g} s")


def operating_point(plot: RawPlot, deck: SpiceDeck) -> OperatingPointResult:
    _check_plot(plot, deck.analyses[0])
    voltages: dict[str, float] = {}
    currents: dict[str, float] = {}
    for column, name in enumerate(plot.names):
        if (net := deck.node_voltages.get(name)) is not None:
            voltages[net] = plot.real[column][0]
        elif (component_id := deck.branch_currents.get(name)) is not None:
            currents[component_id] = plot.real[column][0]
    return OperatingPointResult(node_voltages=voltages, branch_currents=currents)


def _magnitude_phase(plot: RawPlot, column: int) -> tuple[list[float], list[float]]:
    assert plot.imag is not None
    pairs = zip(plot.real[column], plot.imag[column], strict=True)
    magnitude: list[float] = []
    phase: list[float] = []
    for re_value, im_value in pairs:
        magnitude.append(math.hypot(re_value, im_value))
        phase.append(math.degrees(math.atan2(im_value, re_value)))
    return magnitude, phase


def sweep(plot: RawPlot, planned: PlannedAnalysis, deck: SpiceDeck) -> SweepResult:
    """Build a sweep result, decimating to ``MAX_POINTS_PER_TRACE`` points."""
    _check_plot(plot, planned)
    x_values = list(plot.real[0])
    found: list[tuple[TraceSpec, list[float], list[float] | None]] = []
    for spec in deck.traces:
        column = plot.index(spec.vector)
        if column is None:
            continue
        if plot.is_complex:
            magnitude, phase = _magnitude_phase(plot, column)
            found.append((spec, magnitude, phase))
        else:
            found.append((spec, list(plot.real[column]), None))

    # Decimate on the probed signals so their spikes survive; the extra node voltages
    # only drive the schematic animation and follow the same time grid.
    probed = [values for spec, values, _ in found if spec.probed]
    series = probed or [values for _, values, _ in found] or [x_values]
    keep = decimation_indices(series, MAX_POINTS_PER_TRACE)
    traces = [
        Trace(
            name=spec.name,
            unit=spec.unit,
            values=take(values, keep),
            phase_deg=take(phase, keep) if phase is not None else None,
            net=spec.net,
            component=spec.component,
            pin=spec.pin,
            probed=spec.probed,
        )
        for spec, values, phase in found
    ]
    axis = Axis(
        name=planned.axis_name,
        unit=planned.axis_unit,
        values=take(x_values, keep),
        log_scale=planned.log_scale,
    )
    sweep_type = planned.analysis.type
    assert sweep_type != "op"
    return SweepResult(type=sweep_type, x=axis, traces=traces)
