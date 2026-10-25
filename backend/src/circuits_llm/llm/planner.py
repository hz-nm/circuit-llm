"""Planning step: pick the component families a request needs and sketch the design.

The designer prompt then describes only those families, which keeps it short and
focused for weaker models, and the plan gives the designer a head start. Planning
never makes things worse: if the planner's answer is unusable, every family is used.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any, Final, cast

from circuits_llm.domain import CATALOG, Circuit, Family
from circuits_llm.domain.catalog import FAMILY_DESCRIPTIONS

from .contracts import DesignRequest
from .parsing import find_json_object
from .providers.base import Message

MAX_PLAN_CHARS: Final = 1_200
MAX_PLANNER_HISTORY_TURNS: Final = 4
MAX_PLANNER_TURN_CHARS: Final = 600
ALL_FAMILIES: Final = frozenset(Family)

_FAMILY_ALIASES: Final[dict[str, Family]] = {
    "gates": Family.LOGIC,
    "logic_gates": Family.LOGIC,
    "digital": Family.LOGIC,
    "schmitt": Family.LOGIC,
    "transistor": Family.TRANSISTORS,
    "bjt": Family.TRANSISTORS,
    "mosfet": Family.TRANSISTORS,
    "mosfets": Family.TRANSISTORS,
    "amplifier": Family.AMPLIFIERS,
    "opamp": Family.AMPLIFIERS,
    "opamps": Family.AMPLIFIERS,
    "op_amps": Family.AMPLIFIERS,
    "comparator": Family.AMPLIFIERS,
    "sensor": Family.SENSORS,
    "ldr": Family.SENSORS,
    "light_sensor": Family.SENSORS,
    "photoresistor": Family.SENSORS,
    "thermistor": Family.SENSORS,
    "temperature_sensor": Family.SENSORS,
    "gas_sensor": Family.SENSORS,
    "pir": Family.SENSORS,
    "motion_sensor": Family.SENSORS,
    "potentiometer": Family.SENSORS,
    "photodiode": Family.SENSORS,
    "arduino": Family.MICROCONTROLLERS,
    "arduino_uno": Family.MICROCONTROLLERS,
    "microcontroller": Family.MICROCONTROLLERS,
    "mcu": Family.MICROCONTROLLERS,
}


@dataclass(frozen=True, slots=True)
class Plan:
    families: frozenset[Family]
    text: str
    fallback: bool  # True when the planner's answer was unusable and every family is used


def fallback_plan() -> Plan:
    return Plan(families=ALL_FAMILIES, text="", fallback=True)


@cache
def planner_system_prompt() -> str:
    families = "\n".join(
        f'- "{family.value}": {FAMILY_DESCRIPTIONS[family]}'
        + (" (always included)" if family is Family.CORE else "")
        for family in Family
    )
    return f"""\
You plan electronic circuit designs before they are built and simulated with SPICE.
Read the request and decide which component families the circuit needs.

FAMILIES
{families}

Answer with ONE JSON object only, no prose and no code fences:
{{"families": ["<family>", ...], "plan": "<3 to 6 short numbered steps>"}}

The plan names the circuit blocks, the key parts and values, and the analyses that will \
show the circuit working (op, dc, ac or tran). If the request is only a question, answer \
{{"families": [], "plan": "answer the question"}}."""


def planner_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "families": {"type": "array", "items": {"type": "string"}},
            "plan": {"type": "string"},
        },
        "required": ["families", "plan"],
    }


def _circuit_summary(circuit: Circuit) -> str:
    parts = ", ".join(f"{c.id} {c.kind.value}" for c in circuit.components)
    return f"{circuit.title}: {parts}"


def build_planner_messages(request: DesignRequest) -> list[Message]:
    lines: list[str] = []
    for turn in request.history[-MAX_PLANNER_HISTORY_TURNS:]:
        lines.append(f"{turn.role}: {turn.content[:MAX_PLANNER_TURN_CHARS]}")
    if request.current_circuit is not None:
        lines.append(f"Current circuit: {_circuit_summary(request.current_circuit)}")
    lines.append(f"Request: {request.user_message}")
    return [Message("system", planner_system_prompt()), Message("user", "\n".join(lines))]


def families_in(circuit: Circuit | None) -> frozenset[Family]:
    if circuit is None:
        return frozenset()
    return frozenset(CATALOG[c.kind].family for c in circuit.components)


def _resolve_family(raw: object) -> Family | None:
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return Family(key)
    except ValueError:
        return _FAMILY_ALIASES.get(key)


def parse_plan(raw: str, current: Circuit | None) -> Plan:
    """Interpret the planner's answer; unusable answers fall back to every family."""
    data = find_json_object(raw, "families")
    if data is None:
        return fallback_plan()
    raw_families = data.get("families")
    if not isinstance(raw_families, list):
        return fallback_plan()
    items = cast(list[object], raw_families)
    chosen = {family for item in items if (family := _resolve_family(item)) is not None}
    plan = data.get("plan")
    text = (plan if isinstance(plan, str) else json.dumps(plan))[:MAX_PLAN_CHARS].strip()
    families = frozenset({Family.CORE, *chosen, *families_in(current)})
    return Plan(families=families, text=text, fallback=False)


def ordered(families: Sequence[Family] | frozenset[Family]) -> list[str]:
    """Family names in catalog order, for display and stable prompt caching."""
    return [family.value for family in Family if family in families]
