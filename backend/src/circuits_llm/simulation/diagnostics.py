"""Translate ngspice log output into concise, actionable failure reasons."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

MAX_REASON_LENGTH: Final = 300

_SINGULAR_RE: Final = re.compile(r"singular matrix:\s*check node\s+(\S+)", re.IGNORECASE)
_TIMESTEP_RE: Final = re.compile(r"timestep too small", re.IGNORECASE)
_TROUBLE_NODE_RE: Final = re.compile(r'trouble with node\s+"?([^"\s]+)"?', re.IGNORECASE)
_MODEL_RE: Final = re.compile(r"can't find model '([^']+)'", re.IGNORECASE)
_SUBCKT_RE: Final = re.compile(r"unknown subckt:\s*(.+)", re.IGNORECASE)
_CONVERGENCE_RE: Final = re.compile(
    r"(gmin stepping failed|source stepping failed|dc solution failed|no convergence|"
    r"iteration limit reached)",
    re.IGNORECASE,
)
_ERROR_LINE_RE: Final = re.compile(r"^\s*error:?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_TRAN_OP_RE: Final = re.compile(r"doAnalyses:\s*OP", re.IGNORECASE)


def _net(node: str, node_names: Mapping[str, str]) -> str:
    """Original net name for an ngspice node (internal nodes are reported as-is)."""
    return node_names.get(node.lower().strip("'\"."), node)


def _clip(reason: str) -> str:
    return reason if len(reason) <= MAX_REASON_LENGTH else reason[: MAX_REASON_LENGTH - 3] + "..."


def timeout_reason(timeout_s: float) -> str:
    return (
        f"Simulation timed out after {timeout_s:g} s. Shorten the transient stop_time, "
        "increase step_time, reduce sweep points or simplify the circuit."
    )


def _library_reason(log: str) -> str | None:
    if (match := _MODEL_RE.search(log)) is not None:
        return f"Internal error: the simulator could not find device model '{match[1]}'."
    if (match := _SUBCKT_RE.search(log)) is not None:
        return f"Internal error: the simulator could not find a subcircuit ({match[1].strip()})."
    return None


def _timestep_reason(log: str, node_names: Mapping[str, str]) -> str | None:
    if _TIMESTEP_RE.search(log) is None:
        return None
    trouble = _TROUBLE_NODE_RE.search(log)
    where = f" (trouble at net '{_net(trouble[1], node_names)}')" if trouble else ""
    if _TRAN_OP_RE.search(log) is not None:
        return (
            f"The DC operating point did not converge{where}. Check for unrealistic component "
            "values, missing bias resistors or runaway positive feedback."
        )
    return (
        f"Transient analysis failed: timestep too small{where}. Add series resistance to "
        "ideal switching paths, use non-zero rise/fall times or a larger step_time."
    )


def diagnose(log: str, node_names: Mapping[str, str]) -> str:
    """Best explanation for a failed simulation, given the ngspice output."""
    reason = _library_reason(log) or _timestep_reason(log, node_names)
    if reason is None and (match := _SINGULAR_RE.search(log)) is not None:
        reason = (
            f"Singular matrix at net '{_net(match[1], node_names)}': the net is floating or has "
            "no DC path to GND (e.g. it only connects through capacitors, current sources or "
            "op-amp/MOSFET inputs). Add a resistor to GND or fix the connection."
        )
    if reason is None and _CONVERGENCE_RE.search(log) is not None:
        reason = (
            "The DC operating point did not converge. Check for unrealistic component values, "
            "missing bias resistors or runaway positive feedback."
        )
    if reason is None and (match := _ERROR_LINE_RE.search(log)) is not None:
        reason = f"ngspice error: {match[1].strip()}"
    return _clip(reason or "ngspice did not produce results for this analysis.")
