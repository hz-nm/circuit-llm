"""System prompt, output schema and message assembly for design turns.

The component reference in the system prompt is generated from
:data:`circuits_llm.domain.CATALOG`, so it cannot drift from what the parser,
ERC and simulator accept. The prompt is deliberately short and explicit
(numbered rules, one format spec, two complete examples) because the benchmark
model is gpt-oss-120b, not a frontier model.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from functools import cache
from typing import Any, Final

from circuits_llm.domain import CATALOG, GROUND_NET, Circuit, ComponentSpec, Family

from .contracts import ChatTurn, DesignRequest
from .providers.base import Message

MAX_PROMPT_HISTORY_TURNS: Final = 12
MAX_HISTORY_TURN_CHARS: Final = 4_000
MAX_REPAIR_ECHO_CHARS: Final = 24_000
MAX_REPAIR_PROBLEMS: Final = 40

_FORMAT: Final = """\
{"reply": "<short explanation for the user; markdown allowed>",
 "circuit": null OR {
   "title": "<short title>",
   "description": "<one or two sentences>",
   "components": [
     {"id": "R1", "kind": "resistor", "value": "10k", "pins": {"1": "IN", "2": "OUT"}},
     {"id": "D1", "kind": "led", "model": "red", "pins": {"anode": "N1", "cathode": "GND"}},
     {"id": "V1", "kind": "voltage_source", "value": 0, "ac_magnitude": 1,
      "waveform": {"shape": "sine", "offset": 0, "amplitude": 1, "frequency": "1k"},
      "pins": {"+": "IN", "-": "GND"}}
   ],
   "analyses": [
     {"type": "op"},
     {"type": "dc", "source": "V1", "start": 0, "stop": 5, "step": 0.1},
     {"type": "ac", "start_frequency": 10, "stop_frequency": "1Meg", "points_per_decade": 20},
     {"type": "tran", "stop_time": "5m", "step_time": "5u"}
   ],
   "probes": [{"kind": "voltage", "target": "OUT"}, {"kind": "current", "target": "R1"}]
 }}
A pulse waveform is {"shape": "pulse", "initial": 0, "pulsed": 5, "width": "0.5m", "period": "1m"}
(optional "delay", "rise", "fall"). Use it for clocks and square waves.
A piecewise-linear waveform is {"shape": "pwl", "points": [[0, 18], [0.4, 0], [1, 18]]}: \
[time, value] pairs with increasing times. Use it for ramps and slow changes such as day to \
night.
A current probe target is a two-pin component id; a voltage probe target is a net name.
Sensors take "stimulus": the environment they sense (light in lux, temperature in °C, gas in
ppm, motion 0/1, knob position 0..1), as a constant such as 500 or as a waveform over time
such as {"shape": "pwl", "points": [[0, 1000], [1, 0.5]]} for daylight fading to night."""

_RULES: Final = f"""\
1. Answer with ONE JSON object in exactly the format below and nothing else: no prose outside \
the JSON, no code fences, no comments.
2. Ground is the net "{GROUND_NET}". Every circuit must connect to {GROUND_NET}.
3. Net names use only letters, digits and underscore (e.g. VCC, IN, OUT, N1, VBASE).
4. Every component has a unique "id" using conventional designators: R1, R2, C1, L1, V1, I1, \
D1, Q1, M1, U1.
5. Use only the kinds and pin names listed under COMPONENTS. Connect every required pin.
6. Values are numbers in SI base units (ohm, farad, henry, volt, ampere, second, hertz) or \
engineering strings such as "10k", "4.7u", "100n", "1Meg". "m" is milli, "Meg" is mega.
7. Kinds that list models take "model" (one of the listed models). Give "value" only to \
kinds that list a value.
8. Add the analyses that demonstrate the circuit: "op" for DC levels, "tran" for time-domain \
behaviour, "ac" for filters/amplifier frequency response (then give the input source \
"ac_magnitude": 1), "dc" to sweep a source. Add probes for the interesting signals.
9. Every net needs a DC path to {GROUND_NET} (a capacitor alone is not a DC path).
10. For a follow-up request, return the COMPLETE updated circuit. Keep unchanged components, \
ids and net names exactly as they were.
11. If the user only asks a question and no circuit change is needed, answer in "reply" and \
set "circuit" to null.
12. Keep "reply" short: what the circuit does, key values and why, what to look at in the plots.
    Write maths as plain text such as "f = 1/(2*pi*R*C) = 1.0 kHz"; never use LaTeX or $...$."""

_EXAMPLE_LED_REQUEST: Final = "Light a red LED from a 9 V battery at about 15 mA."
_EXAMPLE_LED: Final[dict[str, Any]] = {
    "reply": (
        "A 9 V battery drives a red LED through a **470 Ω** resistor: "
        "(9 V - 1.8 V) / 470 Ω ≈ 15 mA. The operating point shows the LED current."
    ),
    "circuit": {
        "title": "LED with current-limiting resistor",
        "description": "9 V battery, 470 ohm resistor and a red LED.",
        "components": [
            {"id": "V1", "kind": "voltage_source", "value": 9, "pins": {"+": "VCC", "-": "GND"}},
            {"id": "R1", "kind": "resistor", "value": "470", "pins": {"1": "VCC", "2": "N1"}},
            {
                "id": "D1",
                "kind": "led",
                "model": "red",
                "pins": {"anode": "N1", "cathode": "GND"},
            },
        ],
        "analyses": [{"type": "op"}],
        "probes": [{"kind": "voltage", "target": "N1"}, {"kind": "current", "target": "R1"}],
    },
}

_EXAMPLE_RC_REQUEST: Final = "Design an RC low-pass filter with a cutoff around 1.6 kHz."
_EXAMPLE_RC: Final[dict[str, Any]] = {
    "reply": (
        "An RC low-pass with R = 1 kΩ and C = 100 nF: f_c = 1/(2π·R·C) ≈ 1.59 kHz. "
        "The AC sweep shows the -3 dB point and the 1 kHz sine shows the time response."
    ),
    "circuit": {
        "title": "RC low-pass filter",
        "description": "First-order RC low-pass filter, cutoff about 1.6 kHz.",
        "components": [
            {
                "id": "V1",
                "kind": "voltage_source",
                "value": 0,
                "ac_magnitude": 1,
                "waveform": {"shape": "sine", "offset": 0, "amplitude": 1, "frequency": "1k"},
                "pins": {"+": "IN", "-": "GND"},
            },
            {"id": "R1", "kind": "resistor", "value": "1k", "pins": {"1": "IN", "2": "OUT"}},
            {"id": "C1", "kind": "capacitor", "value": "100n", "pins": {"1": "OUT", "2": "GND"}},
        ],
        "analyses": [
            {
                "type": "ac",
                "start_frequency": 10,
                "stop_frequency": "1Meg",
                "points_per_decade": 20,
            },
            {"type": "tran", "stop_time": "5m", "step_time": "5u"},
        ],
        "probes": [{"kind": "voltage", "target": "IN"}, {"kind": "voltage", "target": "OUT"}],
    },
}

_EXAMPLE_LAMP_REQUEST: Final = (
    "Turn a 12 V, 50 W street lamp on at night, using the solar panel voltage as the sensor."
)
_EXAMPLE_LAMP: Final[dict[str, Any]] = {
    "reply": (
        "A 15k/22k divider scales the 0-18 V panel voltage to at most 10.7 V, inside the "
        "rails of a CD4000-series Schmitt-trigger inverter (rated 3-18 V, so it runs straight "
        "from the 12 V battery; 74HC parts allow only 6 V). In daylight its input is high, so "
        "its output is low and the IRFZ44N MOSFET is off. At dusk the input falls below about "
        "40% of 12 V, the output goes high and the MOSFET switches the 50 W lamp on. The "
        "hysteresis (about 4.7 V to 7.1 V at the input) stops flicker while the light level "
        "hovers. The transient run sweeps the panel from day to night and back."
    ),
    "circuit": {
        "title": "Solar street lamp with Schmitt trigger",
        "description": "Panel-voltage dusk sensor, Schmitt inverter, MOSFET lamp switch.",
        "components": [
            {
                "id": "VBAT",
                "kind": "voltage_source",
                "value": 12,
                "pins": {"+": "VBAT", "-": "GND"},
            },
            {
                "id": "VSOLAR",
                "kind": "voltage_source",
                "waveform": {"shape": "pwl", "points": [[0, 18], [0.4, 0], [0.6, 0], [1, 18]]},
                "pins": {"+": "SOLAR", "-": "GND"},
            },
            {"id": "R1", "kind": "resistor", "value": "15k", "pins": {"1": "SOLAR", "2": "SENSE"}},
            {"id": "R2", "kind": "resistor", "value": "22k", "pins": {"1": "SENSE", "2": "GND"}},
            {
                "id": "U1",
                "kind": "schmitt_inverter",
                "model": "CD4000",
                "pins": {"a": "SENSE", "y": "GATE", "vdd": "VBAT", "vss": "GND"},
            },
            {
                "id": "M1",
                "kind": "nmos",
                "model": "IRFZ44N",
                "pins": {"drain": "DRAIN", "gate": "GATE", "source": "GND"},
            },
            {
                "id": "LA1",
                "kind": "lamp",
                "value": 50,
                "model": "12V",
                "pins": {"1": "VBAT", "2": "DRAIN"},
            },
        ],
        "analyses": [{"type": "tran", "stop_time": 1, "step_time": "1m"}],
        "probes": [
            {"kind": "voltage", "target": "SOLAR"},
            {"kind": "voltage", "target": "GATE"},
            {"kind": "current", "target": "LA1"},
        ],
    },
}

_EXAMPLE_LDR_REQUEST: Final = "Switch a 12 V, 50 W lamp on at dusk using a light sensor."
_EXAMPLE_LDR: Final[dict[str, Any]] = {
    "reply": (
        "An LDR (top) and a 10k resistor (bottom) form a light-dependent divider: bright "
        "light makes the LDR small, so SENSE is high. A CD4000-series Schmitt inverter runs "
        "from the 12 V battery. At dusk (about 10 lux) the LDR rises above 15k, SENSE falls "
        "below 4.7 V, the inverter output goes high and the IRFZ44N switches the 50 W lamp "
        "on. It only switches off again above about 30 lux, so the lamp never flickers. The "
        "light stimulus goes from daylight to night and back."
    ),
    "circuit": {
        "title": "Dusk-to-dawn lamp with LDR",
        "description": "LDR divider, Schmitt inverter, MOSFET lamp switch.",
        "components": [
            {
                "id": "VBAT",
                "kind": "voltage_source",
                "value": 12,
                "pins": {"+": "VBAT", "-": "GND"},
            },
            {
                "id": "LDR1",
                "kind": "ldr",
                "stimulus": {
                    "shape": "pwl",
                    "points": [[0, 1000], [0.4, 0.5], [0.6, 0.5], [1, 1000]],
                },
                "pins": {"1": "VBAT", "2": "SENSE"},
            },
            {"id": "R1", "kind": "resistor", "value": "10k", "pins": {"1": "SENSE", "2": "GND"}},
            {
                "id": "U1",
                "kind": "schmitt_inverter",
                "model": "CD4000",
                "pins": {"a": "SENSE", "y": "GATE", "vdd": "VBAT", "vss": "GND"},
            },
            {
                "id": "M1",
                "kind": "nmos",
                "model": "IRFZ44N",
                "pins": {"drain": "DRAIN", "gate": "GATE", "source": "GND"},
            },
            {
                "id": "LA1",
                "kind": "lamp",
                "value": 50,
                "model": "12V",
                "pins": {"1": "VBAT", "2": "DRAIN"},
            },
        ],
        "analyses": [{"type": "tran", "stop_time": 1, "step_time": "1m"}],
        "probes": [{"kind": "voltage", "target": "SENSE"}, {"kind": "current", "target": "LA1"}],
    },
}

# (request, answer, families the example needs). An example is shown only when every
# family it uses is described in the prompt.
FEW_SHOT_EXAMPLES: Final[tuple[tuple[str, dict[str, Any], frozenset[Family]], ...]] = (
    (_EXAMPLE_LED_REQUEST, _EXAMPLE_LED, frozenset({Family.CORE})),
    (_EXAMPLE_RC_REQUEST, _EXAMPLE_RC, frozenset({Family.CORE})),
    (
        _EXAMPLE_LAMP_REQUEST,
        _EXAMPLE_LAMP,
        frozenset({Family.CORE, Family.LOGIC, Family.TRANSISTORS}),
    ),
    (
        _EXAMPLE_LDR_REQUEST,
        _EXAMPLE_LDR,
        frozenset({Family.CORE, Family.SENSORS, Family.LOGIC, Family.TRANSISTORS}),
    ),
)


def _describe_component(spec: ComponentSpec) -> str:
    pins = ", ".join(f'"{p.name}"' + (" (optional)" if p.optional else "") for p in spec.pins)
    parts = [f'- "{spec.kind.value}" ({spec.designator_prefix}): {spec.description} Pins: {pins}.']
    if spec.value_unit is not None:
        need = "required" if spec.value_required else "optional"
        parts.append(f"value ({need}): {spec.value_description}.")
    if spec.models:
        listed = ", ".join(
            f'"{m}"' + (" (default)" if m == spec.default_model else "") for m in spec.models
        )
        parts.append(f"model: {listed}.")
    return " ".join(parts)


def _compact(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def system_prompt(families: frozenset[Family] = frozenset(Family)) -> str:
    """The system prompt describing only the components of ``families`` (core is implied)."""
    return _system_prompt(frozenset({Family.CORE, *families}))


@cache
def _system_prompt(families: frozenset[Family]) -> str:
    components = "\n".join(
        _describe_component(spec) for spec in CATALOG.values() if spec.family in families
    )
    examples = "\n\n".join(
        f"User: {request}\nAnswer:\n{_compact(answer)}"
        for request, answer, needs in FEW_SHOT_EXAMPLES
        if needs <= families
    )
    return (
        "You are an electronics engineer. You design circuits that are simulated with SPICE.\n\n"
        f"RULES\n{_RULES}\n\n"
        f"FORMAT\n{_FORMAT}\n\n"
        f"COMPONENTS\n{components}\n\n"
        f"EXAMPLES\n{examples}"
    )


# --------------------------------------------------------------------------- schema


def _nullable(type_name: str | list[str]) -> dict[str, Any]:
    types = [type_name] if isinstance(type_name, str) else type_name
    return {"type": [*types, "null"]}


_NUMBER_OR_STRING: Final = {"type": ["number", "string"]}


@cache
def response_schema() -> dict[str, Any]:
    """A deliberately simple JSON schema for the envelope (no ``$ref``, no discriminators)."""
    waveform = {
        "type": ["object", "null"],
        "properties": {
            "shape": {"type": "string", "enum": ["sine", "pulse"]},
            **{
                key: _NUMBER_OR_STRING
                for key in (
                    "offset",
                    "amplitude",
                    "frequency",
                    "delay",
                    "phase_deg",
                    "initial",
                    "pulsed",
                    "rise",
                    "fall",
                    "width",
                    "period",
                )
            },
        },
        "required": ["shape"],
    }
    component = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "kind": {"type": "string", "enum": [kind.value for kind in CATALOG]},
            "value": _nullable(["number", "string"]),
            "model": _nullable("string"),
            "pins": {"type": "object", "additionalProperties": {"type": "string"}},
            "waveform": waveform,
            "ac_magnitude": _nullable("number"),
            "label": _nullable("string"),
        },
        "required": ["id", "kind", "pins"],
    }
    analysis = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["op", "dc", "ac", "tran"]},
            "source": {"type": "string"},
            **{
                key: _NUMBER_OR_STRING
                for key in (
                    "start",
                    "stop",
                    "step",
                    "start_frequency",
                    "stop_frequency",
                    "stop_time",
                    "step_time",
                    "start_time",
                )
            },
            "points_per_decade": {"type": "integer"},
        },
        "required": ["type"],
    }
    probe = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["voltage", "current"]},
            "target": {"type": "string"},
        },
        "required": ["kind", "target"],
    }
    circuit = {
        "type": ["object", "null"],
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "components": {"type": "array", "items": component},
            "analyses": {"type": "array", "items": analysis},
            "probes": {"type": "array", "items": probe},
        },
        "required": ["title", "components", "analyses", "probes"],
    }
    return {
        "type": "object",
        "properties": {"reply": {"type": "string"}, "circuit": circuit},
        "required": ["reply", "circuit"],
    }


# --------------------------------------------------------------------------- messages


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 15] + "\n…(truncated)"


def _history_messages(history: Sequence[ChatTurn]) -> list[Message]:
    turns = list(history[-MAX_PROMPT_HISTORY_TURNS:])
    while turns and turns[0].role == "assistant":  # conversations must start with the user
        turns.pop(0)
    return [Message(t.role, _clip(t.content, MAX_HISTORY_TURN_CHARS)) for t in turns]


def circuit_json(circuit: Circuit) -> str:
    """Compact JSON of a circuit, as shown to the model."""
    return _compact(circuit.model_dump(mode="json", exclude_none=True))


def build_messages(
    request: DesignRequest,
    families: frozenset[Family] = frozenset(Family),
    plan: str = "",
) -> list[Message]:
    """System prompt for ``families``, recent history (reply text only) and the request."""
    plan_text = f"Design plan (follow it):\n{plan}\n\n" if plan else ""
    if request.current_circuit is not None:
        user = (
            f"Current circuit:\n{circuit_json(request.current_circuit)}\n\n"
            f"Request: {request.user_message}\n\n{plan_text}"
            "If the request changes the circuit, return the COMPLETE updated circuit. "
            "Answer with the JSON object only."
        )
    else:
        user = f"Request: {request.user_message}\n\n{plan_text}Answer with the JSON object only."
    return [
        Message("system", system_prompt(families)),
        *_history_messages(request.history),
        Message("user", user),
    ]


def build_repair_messages(
    base: Sequence[Message], raw_output: str, problems: Sequence[str]
) -> list[Message]:
    """``base`` plus the model's last answer and a numbered list of every problem in it.

    Only the latest failed answer is included (not every earlier round) to keep
    the context short for weaker models.
    """
    shown = list(problems[:MAX_REPAIR_PROBLEMS])
    numbered = "\n".join(f"{i}. {problem}" for i, problem in enumerate(shown, start=1))
    if len(problems) > len(shown):
        numbered += f"\n(and {len(problems) - len(shown)} more problems)"
    feedback = (
        f"Your answer has {len(problems)} problem(s):\n{numbered}\n\n"
        "Fix ALL of them and answer again with the complete corrected JSON object "
        '({"reply": ..., "circuit": ...}) only. No prose outside the JSON.'
    )
    echo = _clip(raw_output, MAX_REPAIR_ECHO_CHARS) or "(empty answer)"
    return [*base, Message("assistant", echo), Message("user", feedback)]
