"""Pure domain layer: circuit models, component catalog, value parsing, ERC and Mermaid.

Nothing in this package performs I/O; everything else in the application builds on it.
"""

from .catalog import (
    CATALOG,
    Category,
    ComponentKind,
    ComponentSpec,
    Family,
    PinSpec,
    resolve_kind,
    resolve_model,
    spec_for,
)
from .circuit import (
    GROUND_NET,
    AcSweep,
    Analysis,
    Circuit,
    Component,
    DcSweep,
    Expectation,
    OperatingPoint,
    PinRef,
    Probe,
    PulseWave,
    PwlWave,
    SineWave,
    Transient,
    Waveform,
    normalize_net,
)
from .erc import Issue, Severity, check_circuit, has_errors
from .mermaid import component_summary, to_mermaid
from .units import ValueParseError, format_si, parse_value

__all__ = [
    "CATALOG",
    "GROUND_NET",
    "AcSweep",
    "Analysis",
    "Category",
    "Circuit",
    "Component",
    "ComponentKind",
    "ComponentSpec",
    "DcSweep",
    "Expectation",
    "Family",
    "Issue",
    "OperatingPoint",
    "PinRef",
    "PinSpec",
    "Probe",
    "PulseWave",
    "PwlWave",
    "Severity",
    "SineWave",
    "Transient",
    "ValueParseError",
    "Waveform",
    "check_circuit",
    "component_summary",
    "format_si",
    "has_errors",
    "normalize_net",
    "parse_value",
    "resolve_kind",
    "resolve_model",
    "spec_for",
    "to_mermaid",
]
