"""Parsing and formatting of engineering values such as ``"4.7kΩ"`` or ``"100nF"``.

Prefixes are case-sensitive where it matters: ``M`` is mega and ``m`` is milli
(the way humans and LLMs write values, unlike raw SPICE where ``M`` means milli).
``meg`` in any case is also mega. Units are optional and case-insensitive.
"""

from __future__ import annotations

import math
import re
from typing import Final

_PREFIX_MULTIPLIERS: Final[dict[str, float]] = {
    "T": 1e12,
    "G": 1e9,
    "M": 1e6,
    "meg": 1e6,
    "k": 1e3,
    "K": 1e3,
    "": 1.0,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,  # micro sign
    "μ": 1e-6,  # Greek mu
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}

# Ω is the Greek capital omega, Ω the dedicated ohm sign; LLMs emit both.
_UNITS: Final = (
    r"ohms?|Ω|Ω|farads?|f|henrys?|henries|h|volts?|v|amps?|a|hz|hertz|seconds?|s|watts?|w"
    # sensor stimulus units: light, temperature, gas concentration
    r"|lux|lx|°c|degc|deg c|celsius|ppm"
)

_VALUE_RE: Final = re.compile(
    r"^\s*(?P<number>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s*(?P<prefix>(?i:meg)|[TGMkKmuµμnpf]?)"
    rf"\s*(?P<unit>(?i:{_UNITS}))?\s*$"
)

# "4k7" == 4.7k, "2R2" == 2.2, "1M5" == 1.5M (common on schematics and in LLM output)
_INFIX_RE: Final = re.compile(r"^\s*(?P<whole>\d+)(?P<prefix>[RkKMmunp])(?P<frac>\d+)\s*$")

_FORMAT_PREFIXES: Final = (
    (1e12, "T"),
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "µ"),
    (1e-9, "n"),
    (1e-12, "p"),
    (1e-15, "f"),
)


class ValueParseError(ValueError):
    """Raised when a string cannot be interpreted as an engineering value."""


def parse_value(raw: str | float) -> float:
    """Convert ``raw`` to a float in SI base units.

    Accepts plain numbers, scientific notation, SI prefixes, optional units and
    infix notation, e.g. ``10``, ``1e-6``, ``4.7k``, ``100 nF``, ``1MEG``, ``4k7``.
    """
    if isinstance(raw, bool):
        raise ValueParseError(f"expected a number, got boolean {raw!r}")
    value = float(raw) if isinstance(raw, int | float) else _parse_string(raw)
    if not math.isfinite(value):
        raise ValueParseError(f"value {raw!r} is not a finite number")
    return value


def _parse_string(raw: str) -> float:
    if len(raw) > 64:
        raise ValueParseError("value string is too long")
    text = raw.replace(" ", " ").strip()

    infix = _INFIX_RE.match(text)
    if infix is not None:
        prefix = infix["prefix"]
        multiplier = 1.0 if prefix == "R" else _PREFIX_MULTIPLIERS[prefix]
        return float(f"{infix['whole']}.{infix['frac']}") * multiplier

    match = _VALUE_RE.match(text)
    if match is None:
        raise ValueParseError(
            f"cannot parse {raw!r} as a value; use a number with an optional SI prefix "
            "such as '4.7k', '100n', '2.2u' or '1e-3'"
        )
    prefix = match["prefix"]
    multiplier = _PREFIX_MULTIPLIERS["meg" if prefix.lower() == "meg" else prefix]
    return float(match["number"]) * multiplier


def format_si(value: float, unit: str = "", precision: int = 3) -> str:
    """Format ``value`` with an SI prefix, e.g. ``format_si(4700, "Ω") == "4.7 kΩ"``."""
    if value == 0 or not math.isfinite(value):
        return f"{value:g} {unit}".strip()
    magnitude = abs(value)
    for scale, prefix in _FORMAT_PREFIXES:
        if magnitude >= scale * 0.999_999:
            return f"{value / scale:.{precision}g} {prefix}{unit}".strip()
    scale, prefix = _FORMAT_PREFIXES[-1]
    return f"{value / scale:.{precision}g} {prefix}{unit}".strip()
