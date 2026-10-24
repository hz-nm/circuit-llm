"""Lenient parsing of raw model output into the strict domain model.

Weak models get the *shape* of the answer roughly right but the details wrong:
JSON wrapped in prose or code fences, trailing commas, Python literals, kind
and pin aliases, SPICE-style positional pins, engineering-notation strings,
analysis names like ``"transient"``, probes written as ``"V(OUT)"``... All of
that is canonicalised here. Whatever cannot be fixed becomes a problem string
written for the model to act on; *all* problems are collected so one repair
round-trip can fix them together.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

from pydantic import ValidationError

from circuits_llm.domain import (
    CATALOG,
    Circuit,
    ComponentKind,
    ComponentSpec,
    Issue,
    Severity,
    ValueParseError,
    check_circuit,
    normalize_net,
    parse_value,
    resolve_kind,
    resolve_model,
)
from circuits_llm.domain.circuit import MAX_ANALYSES, MAX_COMPONENTS, MAX_PROBES, MAX_PWL_POINTS

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS: Final = 200_000
MAX_JSON_CANDIDATES: Final = 32
MAX_PROBLEMS: Final = 60
MAX_REPLY_CHARS: Final = 8_000
MAX_NET_CHARS: Final = 48
MAX_ID_CHARS: Final = 32

Json = dict[str, object]

# --------------------------------------------------------------------------- result


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Outcome of parsing one model answer.

    ``circuit`` is only set when ``problems`` is empty. ``circuit is None`` with no
    problems means the model deliberately answered without a circuit.
    """

    reply: str
    circuit: Circuit | None
    problems: list[str] = field(default_factory=list[str])
    warnings: list[Issue] = field(default_factory=list[Issue])

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_model_output(raw: str) -> ParseResult:
    """Extract, canonicalise, validate and ERC-check a model answer."""
    if len(raw) > MAX_INPUT_CHARS:
        return ParseResult("", None, [f"The answer is too long (max {MAX_INPUT_CHARS} chars)."])
    found = _find_envelope(raw)
    if found is None:
        return ParseResult("", None, [_no_json_problem(raw)])
    data, json_text = found
    prose = _prose_outside(raw, json_text)
    return _interpret_envelope(data, prose)


def _no_json_problem(raw: str) -> str:
    if "{" in raw:
        return (
            "The JSON object could not be parsed (it is incomplete, was cut off, or is not valid "
            "JSON). Answer with one complete, valid JSON object."
        )
    return 'The answer contains no JSON object. Answer with {"reply": ..., "circuit": ...}.'


# --------------------------------------------------------------------------- JSON extraction

_FENCE_RE: Final = re.compile(r"```[A-Za-z0-9_-]*[ \t]*\r?\n(.*?)```", re.DOTALL)
_PY_LITERALS: Final = {"True": "true", "False": "false", "None": "null"}


def _find_envelope(raw: str) -> tuple[Json, str] | None:
    """Return the best JSON object in ``raw`` and the text it was parsed from."""
    fallback: tuple[Json, str] | None = None
    for candidate in _json_candidates(raw):
        parsed = _loads_lenient(candidate)
        if not isinstance(parsed, dict):
            continue
        data = _lower_keys(cast(Json, parsed))
        if "circuit" in data or "components" in data:
            return data, candidate
        if fallback is None and "reply" in data:
            fallback = (data, candidate)
    return fallback


def find_json_object(raw: str, *required_keys: str) -> Json | None:
    """The first JSON object in ``raw`` (fenced, wrapped in prose, or sloppy) with all of
    ``required_keys``, with keys lower-cased."""
    for candidate in _json_candidates(raw[:MAX_INPUT_CHARS]):
        parsed = _loads_lenient(candidate)
        if isinstance(parsed, dict):
            data = _lower_keys(cast(Json, parsed))
            if all(key in data for key in required_keys):
                return data
    return None


def _json_candidates(text: str) -> Iterator[str]:
    yield text.strip()
    for match in _FENCE_RE.finditer(text):
        yield match.group(1).strip()
    position = 0
    for _ in range(MAX_JSON_CANDIDATES):
        start = text.find("{", position)
        if start < 0:
            return
        end = _balanced_end(text, start)
        if end is None:
            return  # unbalanced: the answer was probably cut off
        yield text[start : end + 1]
        position = end + 1


def _balanced_end(text: str, start: int) -> int | None:
    """Index of the ``}`` closing the object opened at ``start`` (string-aware)."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return index
    return None


def _loads_lenient(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return json.loads(_clean_json(text))
    except ValueError:
        return None


def _clean_json(text: str) -> str:
    """Remove comments and trailing commas; convert Python literals and single-quoted strings."""
    out: list[str] = []
    index, length = 0, len(text)
    while index < length:  # every branch advances ``index``
        char = text[index]
        if char == '"':
            end = _string_end(text, index, '"')
            out.append(text[index:end])
            index = end
        elif char == "'":
            end = _string_end(text, index, "'")
            inner = text[index + 1 : end - 1].replace("\\'", "'")
            out.append(json.dumps(inner))
            index = end
        elif text.startswith("//", index) or char == "#":
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
        elif text.startswith("/*", index):
            close = text.find("*/", index + 2)
            index = length if close < 0 else close + 2
        elif char == ",":
            if not _closes_next(text, index + 1):
                out.append(char)
            index += 1
        elif char.isalpha() or char == "_":
            end = index
            while end < length and (text[end].isalnum() or text[end] == "_"):
                end += 1
            word = text[index:end]
            out.append(_PY_LITERALS.get(word, word))
            index = end
        else:
            out.append(char)
            index += 1
    return "".join(out)


def _closes_next(text: str, start: int) -> bool:
    """True if the next non-whitespace character at or after ``start`` is ``}`` or ``]``."""
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    return index < len(text) and text[index] in "}]"


def _string_end(text: str, start: int, quote: str) -> int:
    """Index just past the string literal starting at ``start``."""
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
        elif text[index] == quote:
            return index + 1
        else:
            index += 1
    return len(text)


def _prose_outside(raw: str, json_text: str) -> str:
    position = raw.find(json_text)
    remainder = raw if position < 0 else raw[:position] + raw[position + len(json_text) :]
    remainder = re.sub(r"```[A-Za-z0-9_-]*", "", remainder)
    return remainder.strip()[:MAX_REPLY_CHARS]


# --------------------------------------------------------------------------- generic helpers


def _lower_keys(data: Json) -> Json:
    return {str(k).strip().lower(): v for k, v in data.items()}


def _as_dict(value: object) -> Json | None:
    return _lower_keys(cast(Json, value)) if isinstance(value, dict) else None


def _pick(data: Json, *keys: str) -> object:
    """First non-null value among ``keys`` (already lower-case)."""
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _text(value: object, limit: int) -> str:
    return "" if value is None else str(value).strip()[:limit]


_ID_CHARS_RE: Final = re.compile(r"[^A-Za-z0-9_]")
_NET_SIGN_RE: Final = (("+", "pos"), ("-", "neg"))


def _sanitize_net(raw: object) -> str | None:
    if isinstance(raw, bool) or not isinstance(raw, str | int | float):
        return None
    text = str(int(raw)) if isinstance(raw, float) and raw.is_integer() else str(raw).strip()
    for sign, word in _NET_SIGN_RE:
        text = text.replace(sign, word)
    text = re.sub(r"_+", "_", _ID_CHARS_RE.sub("_", text)).strip("_")
    return normalize_net(text[:MAX_NET_CHARS]) if text else None


def _sanitize_id(raw: object) -> str | None:
    if not isinstance(raw, str | int):
        return None
    text = re.sub(r"_+", "_", _ID_CHARS_RE.sub("_", str(raw).strip())).strip("_")
    return text[:MAX_ID_CHARS] or None


# --------------------------------------------------------------------------- envelope


def _interpret_envelope(data: Json, prose: str) -> ParseResult:
    reply = _text(_pick(data, "reply", "message", "explanation", "answer", "response"), 8_000)
    if "circuit" in data:
        raw_circuit = data["circuit"]
        if isinstance(raw_circuit, str):
            stripped = raw_circuit.strip()
            raw_circuit = (
                None
                if stripped.lower() in ("", "null", "none")
                else (_loads_lenient(stripped) or raw_circuit)
            )
    elif "components" in data:
        raw_circuit = data  # a bare circuit without the envelope
    else:
        raw_circuit = None
    reply = reply or prose

    if raw_circuit is None:
        if not reply:
            return ParseResult("", None, ['"reply" is empty; explain your answer in "reply".'])
        return ParseResult(reply, None)

    circuit_data = _as_dict(raw_circuit)
    if circuit_data is None:
        return ParseResult(reply, None, ['"circuit" must be a JSON object or null.'])
    builder = _CircuitBuilder()
    circuit = builder.build(circuit_data)
    problems = builder.problems
    warnings: list[Issue] = []
    if circuit is not None and not problems:
        issues = check_circuit(circuit)
        problems = [i.message for i in issues if i.severity is Severity.ERROR]
        warnings = [i for i in issues if i.severity is Severity.WARNING]
    if problems:
        return ParseResult(reply, None, problems[:MAX_PROBLEMS])
    assert circuit is not None
    if not reply:
        reply = circuit.description or f"Here is the circuit: {circuit.title}."
    return ParseResult(reply, circuit, [], warnings)


# --------------------------------------------------------------------------- aliases

_ANALYSIS_ALIASES: Final[dict[str, str]] = {
    **dict.fromkeys(
        ("op", "operating_point", "dc_op", "dcop", "bias", "dc_operating_point", "bias_point"),
        "op",
    ),
    **dict.fromkeys(("dc", "dc_sweep", "sweep", "dcsweep", "dc_analysis"), "dc"),
    **dict.fromkeys(
        (
            "ac",
            "ac_sweep",
            "ac_analysis",
            "frequency_response",
            "freq_response",
            "frequency_sweep",
            "bode",
            "small_signal",
        ),
        "ac",
    ),
    **dict.fromkeys(
        ("tran", "transient", "transient_analysis", "time", "time_domain", "tran_analysis"),
        "tran",
    ),
}

_PWL_SHAPES: Final = frozenset({"pwl", "piecewise", "piecewise_linear", "profile", "points"})
_RAMP_SHAPES: Final = frozenset({"ramp", "linear_ramp", "slope"})
_SINE_SHAPES: Final = frozenset({"sine", "sin", "sinusoidal", "sinusoid", "ac", "sinewave"})
_PULSE_SHAPES: Final = frozenset(
    {"pulse", "square", "clock", "squarewave", "pwm", "rectangular", "rect", "pulse_train"}
)

_SOURCE_VALUE_KEYS: Final[dict[ComponentKind, tuple[str, ...]]] = {
    ComponentKind.RESISTOR: ("resistance", "ohms", "r"),
    ComponentKind.CAPACITOR: ("capacitance", "c"),
    ComponentKind.INDUCTOR: ("inductance", "l"),
    ComponentKind.VOLTAGE_SOURCE: ("voltage", "dc", "dc_value", "dc_voltage", "v"),
    ComponentKind.CURRENT_SOURCE: ("current", "dc", "dc_value", "dc_current", "i"),
    ComponentKind.ZENER: ("breakdown_voltage", "zener_voltage", "voltage", "vz"),
}

_SPICE_WAVE_RE: Final = re.compile(r"\b(sin|sine|pulse|pwl)\s*\(([^)]*)\)", re.IGNORECASE)
_SPICE_AC_RE: Final = re.compile(r"\bac\s+([^\s,()]+)", re.IGNORECASE)
_PROBE_RE: Final = re.compile(r"^\s*([VvIi])\s*\(\s*([^)]*?)\s*\)\s*$")

_PREFIX_KINDS: Final[dict[str, ComponentKind]] = {
    prefix: kinds[0]
    for prefix in {s.designator_prefix for s in CATALOG.values()}
    if len(kinds := [s.kind for s in CATALOG.values() if s.designator_prefix == prefix]) == 1
}


# --------------------------------------------------------------------------- builder


class _CircuitBuilder:
    """Canonicalises one raw circuit dict, collecting every problem found."""

    def __init__(self) -> None:
        self.problems: list[str] = []
        self._ids: list[str] = []

    def problem(self, message: str) -> None:
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append(message)

    def number(self, raw: object, where: str) -> float | None:
        """Parse a number or engineering string; report a problem and return None on failure."""
        if isinstance(raw, str):
            raw = raw.strip()
        if isinstance(raw, bool) or not isinstance(raw, str | int | float):
            self.problem(f"{where}: expected a number or a value like '10k', got {raw!r}.")
            return None
        try:
            return parse_value(raw)
        except ValueParseError as exc:
            self.problem(f"{where}: {exc}.")
            return None

    def optional_number(self, data: Json, keys: Sequence[str], where: str) -> float | None:
        raw = _pick(data, *keys)
        return None if raw is None else self.number(raw, f"{where} '{keys[0]}'")

    # ----------------------------------------------------------------- circuit

    def build(self, data: Json) -> Circuit | None:
        raw_components = _pick(data, "components", "parts", "elements", "netlist")
        components = self._components(raw_components)
        analyses = self._analyses(_pick(data, "analyses", "analysis", "simulations", "simulation"))
        probes = self._probes(_pick(data, "probes", "outputs", "measurements", "plots", "signals"))
        candidate: Json = {
            "title": _text(_pick(data, "title", "name"), 120) or "Untitled circuit",
            "description": _text(_pick(data, "description", "summary"), 4000),
            "components": components,
            "analyses": analyses,
            "probes": probes,
        }
        try:
            circuit = Circuit.model_validate(candidate)
        except ValidationError as exc:
            for message in _validation_messages(exc, self._ids):
                self.problem(message)
            return None
        return None if self.problems else circuit

    # ----------------------------------------------------------------- components

    def _components(self, raw: object) -> list[Json]:
        if isinstance(raw, dict):  # {"R1": {...}, "C1": {...}}
            items: list[object] = []
            for key, value in cast(Json, raw).items():
                entry = _as_dict(value)
                items.append({"id": key, **entry} if entry is not None else value)
        elif isinstance(raw, list):
            items = list(cast(list[object], raw))
        else:
            self.problem('"components" must be a non-empty list of component objects.')
            return []
        if not items:
            self.problem('"components" is empty; a circuit needs at least one component.')
        if len(items) > MAX_COMPONENTS:
            self.problem(f"Too many components ({len(items)}); the maximum is {MAX_COMPONENTS}.")
            items = items[:MAX_COMPONENTS]

        entries = [_as_dict(item) for item in items]
        ids = self._assign_ids(entries)
        built: list[Json] = []
        for index, (entry, component_id) in enumerate(zip(entries, ids, strict=True)):
            if entry is None:
                self.problem(f"components[{index}] must be an object, got {items[index]!r:.60}.")
                continue
            component = self._component(entry, component_id)
            if component is not None:
                built.append(component)
                self._ids.append(component_id)
        return built

    def _assign_ids(self, entries: Sequence[Json | None]) -> list[str]:
        """Sanitised explicit ids, plus fresh designators for components without one."""
        explicit = [
            _sanitize_id(_pick(e, "id", "designator", "ref", "refdes", "name")) if e else None
            for e in entries
        ]
        used = {i.lower() for i in explicit if i}
        result: list[str] = []
        for entry, given in zip(entries, explicit, strict=True):
            if given is not None:
                result.append(given if given[0].isalpha() else f"X{given}")
                continue
            spec = _spec_of(entry) if entry else None
            prefix = spec.designator_prefix if spec else "X"
            fresh = next(
                f"{prefix}{n}"
                for n in range(1, MAX_COMPONENTS + 2)
                if f"{prefix}{n}".lower() not in used
            )
            used.add(fresh.lower())
            result.append(fresh)
        return result

    def _component(self, data: Json, component_id: str) -> Json | None:
        raw_kind = _pick(data, "kind", "type", "component", "part", "device", "element")
        spec = _spec_of(data) or _spec_from_prefix(component_id, raw_kind)
        if spec is None:
            valid = ", ".join(k.value for k in CATALOG)
            shown = f"'{raw_kind}'" if raw_kind is not None else "missing"
            self.problem(f"{component_id}: kind {shown} is not supported; use one of: {valid}.")
            return None
        name = f"{component_id} ({spec.kind.value})"
        result: Json = {"id": component_id, "kind": spec.kind.value}
        result["pins"] = self._pins(
            _pick(data, "pins", "connections", "nodes", "nets", "terminals"), spec, name
        )
        self._component_value(data, spec, name, result)
        model = _pick(data, "model", "part_number", "partnumber", "color", "colour")
        if model is not None:
            text = _text(model, 32)
            canonical = resolve_model(spec.kind, text) if spec.models else None
            result["model"] = canonical or text
        waveform = _pick(data, "waveform", "signal", "wave", "source_type")
        if waveform is not None and "waveform" not in result:
            parsed = self._waveform(waveform, name)
            if parsed is not None:
                result["waveform"] = parsed
        ac = _pick(data, "ac_magnitude", "ac_mag", "acmag", "ac_amplitude", "ac")
        if ac is not None and "ac_magnitude" not in result:
            result["ac_magnitude"] = 1.0 if ac is True else self.number(ac, f"{name} ac_magnitude")
        label = _pick(data, "label", "note", "comment", "description")
        if label is not None:
            result["label"] = _text(label, 120)
        return result

    def _component_value(self, data: Json, spec: ComponentSpec, name: str, out: Json) -> None:
        raw = _pick(data, "value", *_SOURCE_VALUE_KEYS.get(spec.kind, ()))
        if raw is None:
            return
        if spec.is_source and isinstance(raw, str) and re.search(r"[a-z(]{2,}", raw, re.I):
            self._spice_source_value(raw, name, out)
            return
        out["value"] = self.number(raw, f"{name} value")

    def _spice_source_value(self, raw: str, name: str, out: Json) -> None:
        """Interpret SPICE-like source strings such as ``"DC 0 AC 1 SIN(0 1 1k)"``."""
        rest = raw
        wave = _SPICE_WAVE_RE.search(rest)
        if wave is not None:
            parsed = self._waveform(wave.group(0), name)
            if parsed is not None:
                out["waveform"] = parsed
            rest = rest.replace(wave.group(0), " ")
        ac = _SPICE_AC_RE.search(rest)
        if ac is not None:
            out["ac_magnitude"] = self.number(ac.group(1), f"{name} ac_magnitude")
            rest = rest.replace(ac.group(0), " ")
        rest = re.sub(r"\bdc\b", " ", rest, flags=re.IGNORECASE).strip()
        if rest:
            out["value"] = self.number(rest, f"{name} value")
        elif wave is None and ac is None:
            self.problem(f"{name} value: cannot interpret {raw!r}; use a number like 5.")

    # ----------------------------------------------------------------- pins

    def _pins(self, raw: object, spec: ComponentSpec, name: str) -> dict[str, str]:
        pairs = self._pin_pairs(raw, spec, name)
        pins: dict[str, str] = {}
        valid = ", ".join(f"'{p}'" for p in spec.pin_names)
        for raw_pin, raw_net in pairs:
            pin = spec.resolve_pin(str(raw_pin))
            if pin is None:
                self.problem(f"{name}: pin '{raw_pin}' does not exist; valid pins are {valid}.")
                continue
            net_value = _as_dict(raw_net)
            if net_value is not None:
                raw_net = _pick(net_value, "net", "node", "name")
            net = _sanitize_net(raw_net)
            if net is None:
                self.problem(f"{name}: pin '{pin}' has an invalid net name {raw_net!r}.")
            elif pin in pins and pins[pin] != net:
                self.problem(f"{name}: pin '{pin}' is connected twice ('{pins[pin]}', '{net}').")
            else:
                pins[pin] = net
        return pins

    def _pin_pairs(
        self, raw: object, spec: ComponentSpec, name: str
    ) -> list[tuple[object, object]]:
        if isinstance(raw, dict):
            return list(cast(Json, raw).items())
        if not isinstance(raw, list) or not raw:
            order = ", ".join(f'"{p}"' for p in spec.pin_names)
            self.problem(f'{name}: "pins" is missing; map each pin ({order}) to a net name.')
            return []
        items = cast(list[object], raw)
        if all(isinstance(item, dict) for item in items):
            pairs: list[tuple[object, object]] = []
            for item in items:
                entry = _as_dict(item) or {}
                pairs.append(
                    (_pick(entry, "pin", "name", "terminal"), _pick(entry, "net", "node", "to"))
                )
            return pairs
        if len(items) > len(spec.pins):  # positional, SPICE-style, in catalog pin order
            self.problem(
                f"{name}: {len(items)} nets given but it has only {len(spec.pins)} pins "
                f"({', '.join(spec.pin_names)})."
            )
        return list(zip(spec.pin_names, items, strict=False))

    # ----------------------------------------------------------------- waveforms

    def _waveform(self, raw: object, name: str) -> Json | None:
        where = f"{name} waveform"
        if isinstance(raw, str):
            match = _SPICE_WAVE_RE.search(raw)
            if match is None:
                self.problem(f'{where}: give an object such as {{"shape": "sine", ...}}.')
                return None
            values = [v for v in re.split(r"[\s,]+", match.group(2).strip()) if v]
            return self._spice_waveform(match.group(1).lower(), values, where)
        data = _as_dict(raw)
        if data is None:
            self.problem(f"{where}: must be an object or null.")
            return None
        shape = _text(_pick(data, "shape", "type", "kind", "waveform", "function"), 40).lower()
        if shape in _SINE_SHAPES:
            return self._sine(data, where)
        if shape in _PULSE_SHAPES:
            return self._pulse(data, where)
        if shape in _RAMP_SHAPES:
            return self._ramp(data, where)
        if shape in _PWL_SHAPES or "points" in data:
            return self._pwl(_pick(data, "points", "values", "pwl", "data"), where)
        self.problem(f"{where}: shape '{shape}' is not supported; use 'sine', 'pulse' or 'pwl'.")
        return None

    def _pwl(self, raw: object, where: str) -> Json | None:
        """Points as [[t, v], ...], [{"time": t, "value": v}, ...] or a flat [t, v, t, v]."""
        items = _as_items(raw)
        if items and not isinstance(items[0], list | tuple | dict):
            items = [items[i : i + 2] for i in range(0, len(items) - 1, 2)]
        points: dict[float, float] = {}
        for item in items[: MAX_PWL_POINTS * 2]:
            pair: Sequence[object] | None = None
            if isinstance(item, list | tuple):
                pair = cast(Sequence[object], item)
            elif isinstance(item, dict):
                entry = _lower_keys(cast(Json, item))
                pair = (_pick(entry, "time", "t"), _pick(entry, "value", "v", "voltage"))
            if pair is None or len(pair) != 2:
                self.problem(f"{where}: every point must be a [time, value] pair.")
                return None
            time, value = self.number(pair[0], where), self.number(pair[1], where)
            if time is None or value is None:
                return None
            points[max(time, 0.0)] = value  # a repeated time keeps the last value
        ordered = sorted(points.items())[:MAX_PWL_POINTS]
        if len(ordered) < 2:
            self.problem(f"{where}: a pwl needs at least two points, e.g. [[0, 18], [5, 0]].")
            return None
        return {"shape": "pwl", "points": [list(point) for point in ordered]}

    def _ramp(self, data: Json, where: str) -> Json | None:
        """A single ramp from ``start`` to ``stop`` over ``duration``, as a pwl."""

        def number(keys: Sequence[str]) -> float | None:
            return self.optional_number(data, keys, where)

        start = number(("start", "from", "initial", "v1", "start_value"))
        stop = number(("stop", "to", "final", "end", "v2", "stop_value", "end_value"))
        duration = number(("duration", "ramp_time", "time", "rise", "length"))
        if start is None or stop is None or duration is None or duration <= 0:
            self.problem(f"{where}: a ramp needs 'start', 'stop' and a positive 'duration'.")
            return None
        delay = max(number(("delay", "td")) or 0.0, 0.0)
        points = [[0.0, start], [delay, start]] if delay > 0 else [[0.0, start]]
        return {"shape": "pwl", "points": [*points, [delay + duration, stop]]}

    def _spice_waveform(self, shape: str, values: Sequence[str], where: str) -> Json | None:
        if shape == "pwl":
            return self._pwl(list(values), where)
        fields = (
            ("offset", "amplitude", "frequency", "delay", "damping", "phase")
            if shape in ("sin", "sine")
            else ("initial", "pulsed", "delay", "rise", "fall", "width", "period")
        )
        data: Json = dict(zip(fields, values, strict=False))
        data.pop("damping", None)
        return self._sine(data, where) if shape in ("sin", "sine") else self._pulse(data, where)

    def _sine(self, data: Json, where: str) -> Json | None:
        def number(keys: Sequence[str]) -> float | None:
            return self.optional_number(data, keys, where)

        amplitude = number(("amplitude", "amp", "va", "vamp", "peak"))
        if amplitude is None:
            peak_to_peak = number(("vpp", "peak_to_peak", "amplitude_pp"))
            amplitude = None if peak_to_peak is None else peak_to_peak / 2
        frequency = number(("frequency", "freq", "f"))
        if amplitude is None or frequency is None:
            self.problem(f"{where}: a sine needs 'amplitude' and 'frequency'.")
            return None
        return {
            "shape": "sine",
            "offset": number(("offset", "dc_offset", "vo", "voffset", "dc")) or 0.0,
            "amplitude": amplitude,
            "frequency": frequency,
            "delay": number(("delay", "td")) or 0.0,
            "phase_deg": number(("phase_deg", "phase")) or 0.0,
        }

    def _pulse(self, data: Json, where: str) -> Json | None:
        def number(keys: Sequence[str]) -> float | None:
            return self.optional_number(data, keys, where)

        initial = number(("initial", "v1", "low", "vlow", "min", "initial_value", "vmin"))
        pulsed = number(("pulsed", "v2", "high", "vhigh", "max", "pulsed_value", "vmax"))
        if pulsed is None:
            amplitude = number(("amplitude", "amp"))
            offset = number(("offset",))
            if amplitude is not None and offset is not None:
                initial, pulsed = offset - amplitude, offset + amplitude
            elif amplitude is not None:
                pulsed = amplitude
        rise = number(("rise", "tr", "rise_time")) or 1e-9
        fall = number(("fall", "tf", "fall_time")) or 1e-9
        period = number(("period", "per", "t"))
        frequency = number(("frequency", "freq", "f"))
        if period is None and frequency is not None and frequency > 0:
            period = 1.0 / frequency
        width = number(("width", "pw", "pulse_width", "on_time"))
        if width is None and period is not None:
            duty = number(("duty", "duty_cycle", "dutycycle")) or 0.5
            duty = duty / 100 if duty > 1 else duty
            width = max(period * duty - rise, period * 1e-3)
            width = min(width, period - rise - fall) if period - rise - fall > 0 else width
        if pulsed is None or period is None or width is None:
            self.problem(
                f"{where}: a pulse needs 'pulsed' (high level), and 'period' or 'frequency' "
                "(plus 'width' or 'duty')."
            )
            return None
        # Repair timings whose intent is clear instead of bouncing them back to the model.
        rise, fall = abs(rise) or 1e-9, abs(fall) or 1e-9
        if width <= 0:
            width = max(period * 1e-3, 1e-9)
        period = max(period, rise + width + fall)
        return {
            "shape": "pulse",
            "initial": initial or 0.0,
            "pulsed": pulsed,
            "delay": number(("delay", "td")) or 0.0,
            "rise": rise,
            "fall": fall,
            "width": width,
            "period": period,
        }

    # ----------------------------------------------------------------- analyses

    def _analyses(self, raw: object) -> list[Json]:
        items = _as_items(raw)
        if len(items) > MAX_ANALYSES:
            self.problem(f"Too many analyses ({len(items)}); the maximum is {MAX_ANALYSES}.")
            items = items[:MAX_ANALYSES]
        built: list[Json] = []
        for index, item in enumerate(items, start=1):
            analysis = self._analysis(item, f"Analysis {index}")
            if analysis is not None:
                built.append(analysis)
        return built

    def _analysis(self, raw: object, where: str) -> Json | None:
        data = _spice_directive(raw) if isinstance(raw, str) else _as_dict(raw)
        if data is None:
            self.problem(f'{where}: must be an object such as {{"type": "op"}}.')
            return None
        raw_type = _text(_pick(data, "type", "kind", "analysis", "name", "mode"), 40)
        key = raw_type.lower().lstrip(".").replace(" ", "_").replace("-", "_")
        kind = _ANALYSIS_ALIASES.get(key)
        if kind is None:
            self.problem(f"{where}: type '{raw_type}' is not supported; use op, dc, ac or tran.")
            return None
        where = f"{where} ({kind})"
        if kind == "op":
            return {"type": "op"}
        if kind == "dc":
            return self._dc(data, where)
        if kind == "ac":
            return self._ac(data, where)
        return self._tran(data, where)

    def _required(self, data: Json, keys: Sequence[str], where: str, example: str) -> float | None:
        raw = _pick(data, *keys)
        if raw is None:
            self.problem(f"{where}: '{keys[0]}' is required (e.g. {example}).")
            return None
        return self.number(raw, f"{where} '{keys[0]}'")

    def _dc(self, data: Json, where: str) -> Json | None:
        source = _sanitize_id(_pick(data, "source", "src", "sweep_source", "source_id", "element"))
        start = self._required(data, ("start", "from", "vstart", "min"), where, "0")
        stop = self._required(data, ("stop", "to", "end", "vstop", "max"), where, "5")
        step = self.optional_number(data, ("step", "increment", "inc", "vstep", "delta"), where)
        if source is None:
            self.problem(f"{where}: 'source' (the id of the swept source, e.g. 'V1') is required.")
        if source is None or start is None or stop is None:
            return None
        if step is None:
            points = self.optional_number(data, ("points", "num_points", "npoints"), where)
            step = abs(stop - start) / max((points or 101) - 1, 1)
        return {"type": "dc", "source": source, "start": start, "stop": stop, "step": abs(step)}

    def _ac(self, data: Json, where: str) -> Json | None:
        start = self._required(
            data,
            ("start_frequency", "fstart", "f_start", "start_freq", "freq_start", "fmin", "start"),
            where,
            "10",
        )
        stop = self._required(
            data,
            ("stop_frequency", "fstop", "f_stop", "stop_freq", "freq_stop", "fmax", "stop", "end"),
            where,
            '"1Meg"',
        )
        points = self.optional_number(
            data, ("points_per_decade", "points", "ppd", "num_points", "npoints", "n"), where
        )
        if start is None or stop is None:
            return None
        result: Json = {"type": "ac", "start_frequency": start, "stop_frequency": stop}
        if points is not None:
            result["points_per_decade"] = min(max(round(points), 1), 200)
        return result

    def _tran(self, data: Json, where: str) -> Json | None:
        stop = self._required(
            data,
            ("stop_time", "tstop", "t_stop", "stop", "duration", "end_time", "end", "time"),
            where,
            '"10m"',
        )
        step = self.optional_number(
            data, ("step_time", "tstep", "t_step", "step", "timestep", "time_step"), where
        )
        start = self.optional_number(data, ("start_time", "tstart", "t_start", "start"), where)
        if stop is None:
            return None
        result: Json = {"type": "tran", "stop_time": stop}
        if step is not None:
            result["step_time"] = step
        if start is not None:
            result["start_time"] = start
        return result

    # ----------------------------------------------------------------- probes

    def _probes(self, raw: object) -> list[Json]:
        built: list[Json] = []
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(_as_items(raw), start=1):
            probe = self._probe(item, f"Probe {index}")
            if probe is None:
                continue
            key = (str(probe["kind"]), str(probe["target"]).lower())
            if key not in seen and len(built) < MAX_PROBES:
                seen.add(key)
                built.append(probe)
        return built

    def _probe(self, raw: object, where: str) -> Json | None:
        if isinstance(raw, str):
            return self._probe_from_text(raw, None, where)
        data = _as_dict(raw)
        if data is None:
            self.problem(f'{where}: use {{"kind": "voltage", "target": "OUT"}}.')
            return None
        kind = _text(_pick(data, "kind", "type", "quantity"), 20).lower() or None
        if kind is None:
            kind = "current" if _pick(data, "component", "element") is not None else None
        target = _pick(data, "target", "net", "node", "component", "element", "id", "name")
        if target is None:
            self.problem(f"{where}: 'target' is missing.")
            return None
        return self._probe_from_text(str(target), kind, where)

    def _probe_from_text(self, text: str, kind: str | None, where: str) -> Json | None:
        match = _PROBE_RE.match(text)
        if match is not None:
            kind = "voltage" if match.group(1).lower() == "v" else "current"
            text = match.group(2)
            if "," in text:
                self.problem(
                    f"{where}: differential probes like V(A,B) are not supported; "
                    "probe each net separately."
                )
                return None
        kind = {"v": "voltage", "i": "current", None: "voltage"}.get(kind, kind)
        if kind not in ("voltage", "current"):
            self.problem(f"{where}: kind '{kind}' is not supported; use 'voltage' or 'current'.")
            return None
        target = _sanitize_net(text) if kind == "voltage" else _sanitize_id(text)
        if target is None:
            self.problem(f"{where}: target {text!r} is not a valid net name or component id.")
            return None
        return {"kind": kind, "target": target}


# --------------------------------------------------------------------------- module helpers


def _spec_of(data: Json) -> ComponentSpec | None:
    for key in ("kind", "type", "component", "part", "device", "element"):
        value = data.get(key)
        if isinstance(value, str):
            kind = resolve_kind(value)
            if kind is not None:
                return CATALOG[kind]
    return None


def _spec_from_prefix(component_id: str, raw_kind: object) -> ComponentSpec | None:
    """Infer the kind from an unambiguous designator prefix when no kind was given."""
    if raw_kind is not None:
        return None
    prefix = re.match(r"[A-Za-z]+", component_id)
    kind = _PREFIX_KINDS.get(prefix.group(0).upper()) if prefix else None
    return CATALOG[kind] if kind is not None else None


def _as_items(raw: object) -> list[object]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return list(cast(list[object], raw))
    return [raw]


def _spice_directive(text: str) -> Json | None:
    """Turn ``".tran 1u 10m"``, ``".ac dec 20 10 1meg"``, ``".dc V1 0 5 0.1"`` into dicts."""
    tokens = text.strip().lstrip(".").split()
    if not tokens:
        return None
    head, args = tokens[0].lower(), tokens[1:]
    if head == "tran" and args:
        return dict(
            zip(("type", "step_time", "stop_time", "start_time"), [head, *args], strict=False)
        )
    if head == "ac" and len(args) >= 4:
        return {"type": "ac", "points": args[1], "fstart": args[2], "fstop": args[3]}
    if head == "dc" and len(args) >= 4:
        return dict(zip(("type", "source", "start", "stop", "step"), [head, *args], strict=False))
    return {"type": text}


def _validation_messages(exc: ValidationError, ids: Sequence[str]) -> list[str]:
    """Readable one-line messages for each pydantic error."""
    messages: list[str] = []
    for error in exc.errors(include_url=False):
        location = list(error["loc"])
        where = _location_text(location, ids)
        message = str(error["msg"]).removeprefix("Value error, ")
        messages.append(f"{where}: {message}." if where else f"{message}.")
    return messages


_SECTION_LABELS: Final = {"analyses": "Analysis", "probes": "Probe"}


def _location_text(location: list[int | str], ids: Sequence[str]) -> str:
    if len(location) >= 2 and isinstance(location[1], int):
        section, index, rest = str(location[0]), location[1], location[2:]
        if section == "components" and index < len(ids):
            head = ids[index]
        else:
            head = f"{_SECTION_LABELS.get(section, section)} {index + 1}"
        if section == "analyses" and rest:  # the first part is the analysis type tag
            head, rest = f"{head} ({rest[0]})", rest[1:]
        return " ".join([head, ".".join(str(part) for part in rest)]).strip()
    return ".".join(str(part) for part in location)
