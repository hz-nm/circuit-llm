"""The tiny grammar of circuit expectations, e.g. ``I(D1) > 5m`` when ``light(LDR1) < 1``.

An expectation states what a circuit must do so the simulator can verify it. Signals
are ``V(net)``, ``I(component)`` (two-pin parts and sources) or a sensor's stimulus such
as ``light(LDR1)``; a bare net name means its voltage. Conditions compare a signal with
an engineering value using ``>``, ``>=``, ``<`` or ``<=``. Nothing here is ever passed
to the simulator: expectations are evaluated in Python on its results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal, cast

from .units import ValueParseError, parse_value

Operator = Literal[">", ">=", "<", "<="]
SignalKind = Literal["voltage", "current", "stimulus"]

_SIGNAL_RE: Final = re.compile(r"^\s*([A-Za-z]+)\s*\(\s*([A-Za-z0-9_]+)\s*\)\s*$")
_BARE_NET_RE: Final = re.compile(r"^\s*([A-Za-z0-9_]+)\s*$")
_CONDITION_RE: Final = re.compile(r"^\s*(.+?)\s*(>=|<=|>|<)\s*(.+?)\s*$")
_CHECK_RE: Final = re.compile(r"^\s*(>=|<=|>|<)\s*(.+?)\s*$")


class ExpectationSyntaxError(ValueError):
    """An expectation that does not follow the grammar; the message says how to fix it."""


@dataclass(frozen=True, slots=True)
class Signal:
    kind: SignalKind
    target: str  # net name, component id or sensor id
    quantity: str = ""  # for stimulus signals: "light", "temperature", ...

    def __str__(self) -> str:
        prefix = {"voltage": "V", "current": "I"}.get(self.kind, self.quantity)
        return f"{prefix}({self.target})"


@dataclass(frozen=True, slots=True)
class Comparison:
    operator: Operator
    value: float

    def holds(self, sample: float) -> bool:
        match self.operator:
            case ">":
                return sample > self.value
            case ">=":
                return sample >= self.value
            case "<":
                return sample < self.value
            case "<=":
                return sample <= self.value


def parse_signal(text: str, stimulus_quantities: frozenset[str]) -> Signal:
    """``V(OUT)``, ``I(R1)``, ``light(LDR1)`` or a bare net name such as ``OUT``."""
    match = _SIGNAL_RE.match(text)
    if match is not None:
        function, target = match[1].lower(), match[2]
        if function == "v":
            return Signal("voltage", target)
        if function == "i":
            return Signal("current", target)
        if function in stimulus_quantities:
            return Signal("stimulus", target, function)
        known = ", ".join(sorted({"V", "I", *stimulus_quantities}))
        raise ExpectationSyntaxError(f"unknown signal '{text}'; use one of {known}, e.g. V(OUT)")
    bare = _BARE_NET_RE.match(text)
    if bare is not None:
        return Signal("voltage", bare[1])
    raise ExpectationSyntaxError(f"cannot read signal '{text}'; write it like V(OUT) or I(R1)")


def _value(text: str) -> float:
    try:
        return parse_value(text)
    except ValueParseError as exc:
        raise ExpectationSyntaxError(f"cannot read value '{text}'") from exc


def parse_check(text: str) -> Comparison:
    """``> 5m``, ``<= 0.5`` and so on."""
    match = _CHECK_RE.match(text)
    if match is None:
        raise ExpectationSyntaxError(f"check '{text}' must look like '> 5m' or '< 0.5'")
    return Comparison(cast(Operator, match[1]), _value(match[2]))


def parse_condition(text: str, stimulus_quantities: frozenset[str]) -> tuple[Signal, Comparison]:
    """``light(LDR1) < 1`` -> (signal, comparison)."""
    match = _CONDITION_RE.match(text)
    if match is None:
        raise ExpectationSyntaxError(f"condition '{text}' must look like 'light(LDR1) < 1'")
    comparison = Comparison(cast(Operator, match[2]), _value(match[3]))
    return parse_signal(match[1], stimulus_quantities), comparison
