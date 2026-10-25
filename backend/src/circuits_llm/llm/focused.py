"""Focused follow-up questions for what weak models reliably get wrong.

Weak models often describe the Arduino logic in prose ("D9 goes high when A0 < 2.3 V")
but omit the ``behavior`` field, or give a sensor an environment that never reaches the
conditions its expectations test. A full repair round tends to reproduce the same
answer; a small, self-contained question fixes the one field reliably. The answer is
injected into the model's JSON, which is then parsed and validated as usual.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, Final, cast

from circuits_llm.domain import CATALOG, Circuit, ComponentKind, Issue, Transient, resolve_kind

from .parsing import find_json_object
from .providers.base import Message, Provider, ProviderError

logger = logging.getLogger(__name__)

MAX_ARDUINOS_FILLED: Final = 2
MAX_SENSORS_FIXED: Final = 2
MAX_INTENT_CHARS: Final = 1_500
BEHAVIOR_KEYS: Final = ("behavior", "behaviour", "behaviors", "behaviours", "program")

_SYSTEM: Final = (
    "You program the pins of an Arduino Uno in a circuit design. Answer with ONE JSON "
    "object only, no prose and no code fences."
)
_RESPONSE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {"behavior": {"type": "array", "items": {"type": "object"}}},
    "required": ["behavior"],
}

Json = dict[str, Any]


def _components(envelope: Json) -> list[Json]:
    circuit: object = envelope.get("circuit", envelope)
    if not isinstance(circuit, dict):
        return []
    items: object = cast(Json, circuit).get("components")
    if not isinstance(items, list):
        return []
    return [cast(Json, c) for c in cast(list[object], items) if isinstance(c, dict)]


def _unprogrammed_arduinos(components: Sequence[Json]) -> list[Json]:
    found: list[Json] = []
    for component in components:
        kind = resolve_kind(str(component.get("kind", "")))
        if kind is ComponentKind.ARDUINO_UNO and not any(k in component for k in BEHAVIOR_KEYS):
            found.append(component)
    return found[:MAX_ARDUINOS_FILLED]


def _wiring(arduino: Json, components: Sequence[Json]) -> list[str]:
    """One line per connected pin: net name and what else is on that net."""
    spec = CATALOG[ComponentKind.ARDUINO_UNO]
    pins = arduino.get("pins")
    if not isinstance(pins, dict):
        return []
    lines: list[str] = []
    for raw_pin, net in cast(dict[str, object], pins).items():
        pin = spec.resolve_pin(str(raw_pin)) or str(raw_pin)
        others = [
            f"{c.get('id')} ({c.get('kind')})"
            for c in components
            if c is not arduino
            and isinstance(c.get("pins"), dict)
            and net in cast(dict[str, object], c["pins"]).values()
        ]
        lines.append(
            f"- {pin} -> net {net}" + (f", shared with {', '.join(others)}" if others else "")
        )
    return lines


def _question(arduino: Json, components: Sequence[Json], intent: str) -> str:
    return "\n".join(
        [
            f"Arduino {arduino.get('id')} is wired like this:",
            *_wiring(arduino, components),
            "",
            f"What the design should do: {intent[:MAX_INTENT_CHARS]}",
            "",
            'Write the pin behaviours: one entry for every connected D pin. "output" is high, '
            'low, blink ("period" in seconds), pwm ("duty" 0..1) or rule (high while "when" '
            'holds; "when" compares an analog pin A0-A5 with volts, e.g. "A0 < 2.3").',
            'Answer exactly like: {"behavior": [{"pin": "D9", "output": "rule", "when": '
            '"A0 < 2.3"}]}',
        ]
    )


async def fill_missing_behaviors(raw: str, provider: Provider) -> str | None:
    """``raw`` with behaviours added to unprogrammed Arduinos, or None if nothing changed."""
    envelope = find_json_object(raw, "circuit") or find_json_object(raw, "components")
    if envelope is None:
        return None
    components = _components(envelope)
    targets = _unprogrammed_arduinos(components)
    if not targets:
        return None
    intent = str(envelope.get("reply") or envelope.get("description") or "")
    changed = False
    for arduino in targets:
        messages = [
            Message("system", _SYSTEM),
            Message("user", _question(arduino, components, intent)),
        ]
        try:
            completion = await provider.complete(messages, response_schema=_RESPONSE_SCHEMA)
        except ProviderError as exc:
            logger.info("behaviour fill for %s failed: %s", arduino.get("id"), exc.kind.value)
            continue
        answer = find_json_object(completion.text, "behavior")
        if answer is not None and isinstance(answer.get("behavior"), list):
            arduino["behavior"] = answer["behavior"]
            changed = True
    return json.dumps(envelope) if changed else None


_STIMULUS_SYSTEM: Final = (
    "You choose how the environment changes during a circuit simulation. Answer with ONE "
    "JSON object only, no prose and no code fences."
)
_STIMULUS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {"stimulus": {"type": "object"}},
    "required": ["stimulus"],
}


def _stop_time(circuit: Circuit) -> float:
    transient = next((a for a in circuit.analyses if isinstance(a, Transient)), None)
    return transient.stop_time if transient is not None else 1.0


def _stimulus_question(sensor_id: str, kind: ComponentKind, reasons: list[str], stop: float) -> str:
    spec = CATALOG[kind].stimulus
    assert spec is not None
    unit = f" in {spec.unit}" if spec.unit else ""
    mid = f"{stop / 2:g}"
    return "\n".join(
        [
            f"Sensor {sensor_id} ({CATALOG[kind].display_name}) senses {spec.quantity}{unit}, "
            f"between {spec.minimum:g} and {spec.maximum:g} ({spec.hint}).",
            f"The transient simulation runs from 0 to {stop:g} s.",
            "These checks need conditions that the current stimulus never reaches:",
            *(f"- {reason}" for reason in reasons),
            f"Give {sensor_id} a stimulus that starts at a normal value and changes over the "
            "run so that every condition above happens.",
            'Answer exactly like: {"stimulus": {"shape": "pwl", "points": '
            f"[[0, <start>], [{mid}, <extreme>], [{stop:g}, <start>]]}}}}",
        ]
    )


async def fix_unreached_stimuli(
    raw: str, issues: Sequence[Issue], circuit: Circuit, provider: Provider
) -> str | None:
    """``raw`` with new stimuli for sensors whose conditions never occurred, or None."""
    envelope = find_json_object(raw, "circuit") or find_json_object(raw, "components")
    if envelope is None:
        return None
    by_id = {str(c.get("id", "")).lower(): c for c in _components(envelope)}
    reasons: dict[str, list[str]] = {}
    for issue in issues:
        if issue.component_id:
            reasons.setdefault(issue.component_id, []).append(issue.message)
    changed = False
    for sensor_id, sensor_reasons in list(reasons.items())[:MAX_SENSORS_FIXED]:
        component = circuit.component(sensor_id)
        target = by_id.get(sensor_id.lower())
        if component is None or target is None or CATALOG[component.kind].stimulus is None:
            continue
        question = _stimulus_question(
            component.id, component.kind, sensor_reasons, _stop_time(circuit)
        )
        messages = [Message("system", _STIMULUS_SYSTEM), Message("user", question)]
        try:
            completion = await provider.complete(messages, response_schema=_STIMULUS_SCHEMA)
        except ProviderError as exc:
            logger.info("stimulus fix for %s failed: %s", sensor_id, exc.kind.value)
            continue
        answer = find_json_object(completion.text, "stimulus")
        if answer is not None and answer.get("stimulus") is not None:
            target.pop("waveform", None)  # weak models put the profile here
            target["stimulus"] = answer["stimulus"]
            changed = True
    return json.dumps(envelope) if changed else None
