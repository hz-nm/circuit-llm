"""Simulation layer: SPICE netlist generation and the ngspice runner.

``results.py`` holds the public data contracts; ``to_spice`` builds decks and
``NgspiceSimulator`` runs them.
"""

from .library import DISCRETE_MODELS, OPAMP_MODELS, DeviceModel, OpAmpSpec
from .ngspice import (
    DEFAULT_TIMEOUT_S,
    ENV_VAR,
    NgspiceSimulator,
    Simulator,
    locate_ngspice,
    simulation_issues,
)
from .raw import RawParseError, RawPlot, parse_raw
from .results import (
    MAX_POINTS_PER_TRACE,
    AnalysisResult,
    Axis,
    ExpectationResult,
    ExploreResult,
    OperatingPointResult,
    SimulationResult,
    SweepResult,
    Trace,
)
from .spice import (
    PlannedAnalysis,
    SpiceDeck,
    SpiceEmissionError,
    StimulusSweep,
    TraceSpec,
    to_spice,
)

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "DISCRETE_MODELS",
    "ENV_VAR",
    "MAX_POINTS_PER_TRACE",
    "OPAMP_MODELS",
    "AnalysisResult",
    "Axis",
    "DeviceModel",
    "ExpectationResult",
    "ExploreResult",
    "NgspiceSimulator",
    "OpAmpSpec",
    "OperatingPointResult",
    "PlannedAnalysis",
    "RawParseError",
    "RawPlot",
    "SimulationResult",
    "Simulator",
    "SpiceDeck",
    "SpiceEmissionError",
    "StimulusSweep",
    "SweepResult",
    "Trace",
    "TraceSpec",
    "locate_ngspice",
    "parse_raw",
    "simulation_issues",
    "to_spice",
]
