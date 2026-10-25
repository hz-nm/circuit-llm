from __future__ import annotations

import json

import pytest

from circuits_llm.domain import AcSweep, ComponentKind, PulseWave, PwlWave, SineWave, Transient
from circuits_llm.domain.arduino import sketch
from circuits_llm.llm import parse_model_output
from circuits_llm.llm.prompts import FEW_SHOT_EXAMPLES, response_schema, system_prompt


@pytest.mark.parametrize("example", [answer for _, answer, _ in FEW_SHOT_EXAMPLES])
def test_few_shot_examples_are_valid(example: dict[str, object]) -> None:
    result = parse_model_output(json.dumps(example))
    assert result.problems == []
    assert result.circuit is not None


def test_prompt_and_schema_follow_the_catalog() -> None:
    prompt = system_prompt()
    assert all(f'"{kind.value}"' in prompt for kind in ComponentKind)
    assert '"2N3904" (default)' in prompt
    assert "$ref" not in json.dumps(response_schema())


def test_messy_prose_fenced_output_is_canonicalised() -> None:
    raw = """Sure! Here is the design:
```json
{
  // envelope with comments, single quotes and trailing commas
  'reply': 'A divider with a filter cap.',
  "circuit": {
    "title": "Divider",
    "components": [
      {"kind": "Battery", "voltage": "9V", "pins": ["VCC", 0]},
      {"type": "res", "id": "R1", "resistance": "4k7", "nodes": {"a": "VCC", "b": "MID"}},
      {"id": "R2", "kind": "resistor", "value": "10 kΩ",
       "pins": [{"pin": "1", "net": "MID"}, {"pin": "2", "net": "ground"}],},
      {"id": "C1", "kind": "cap", "value": "100nF", "pins": {"+": "MID", "-": "GND"}},
    ],
    "analyses": ["operating_point", {"type": "transient", "tstop": "10ms", "tstep": "10us"}],
    "probes": ["V(MID)", "I(R1)", {"net": "VCC"}],
    "extra": True,
  }
}
```
Hope that helps!"""
    result = parse_model_output(raw)
    assert result.problems == []
    circuit = result.circuit
    assert circuit is not None
    assert result.reply == "A divider with a filter cap."
    battery, r1, r2, _ = circuit.components
    assert (battery.id, battery.value, battery.pins) == ("V1", 9.0, {"+": "VCC", "-": "GND"})
    assert r1.value == pytest.approx(4700)
    assert r2.pins == {"1": "MID", "2": "GND"}
    assert isinstance(circuit.analyses[1], Transient)
    assert circuit.analyses[1].stop_time == pytest.approx(10e-3)
    assert [(p.kind, p.target) for p in circuit.probes] == [
        ("voltage", "MID"),
        ("current", "R1"),
        ("voltage", "VCC"),
    ]


def test_bare_circuit_with_spice_style_source_and_analysis() -> None:
    raw = json.dumps(
        {
            "title": "RC",
            "components": [
                {
                    "id": "V1",
                    "kind": "vsource",
                    "value": "DC 0 AC 1 SIN(0 1 1k)",
                    "pins": ["IN", "0"],
                },
                {"id": "R1", "kind": "r", "value": "1k", "pins": ["IN", "OUT"]},
                {"id": "C1", "kind": "c", "value": "10u", "pins": ["OUT", "GND"]},
            ],
            "analyses": [
                ".ac dec 10 1 100k",
                {"type": "frequency_response", "fstart": 1, "fstop": "1Meg"},
            ],
        }
    )
    result = parse_model_output(f"Here you go:\n{raw}")
    assert result.problems == []
    assert result.circuit is not None
    source = result.circuit.components[0]
    assert source.ac_magnitude == 1.0
    assert isinstance(source.waveform, SineWave)
    assert source.waveform.frequency == pytest.approx(1000)
    first = result.circuit.analyses[0]
    assert isinstance(first, AcSweep)
    assert (first.points_per_decade, first.stop_frequency) == (10, pytest.approx(1e5))


def test_square_wave_is_derived_from_frequency_and_duty() -> None:
    raw = json.dumps(
        {
            "reply": "clock",
            "circuit": {
                "title": "Clock into a load",
                "components": [
                    {
                        "id": "V1",
                        "kind": "function_generator",
                        "waveform": {"type": "square", "high": 5, "frequency": "1k", "duty": 25},
                        "pins": {"+": "CLK", "-": "GND"},
                    },
                    {
                        "id": "R1",
                        "kind": "resistor",
                        "value": "1k",
                        "pins": {"1": "CLK", "2": "GND"},
                    },
                ],
                "analyses": [{"type": "tran", "stop_time": "5m"}],
            },
        }
    )
    result = parse_model_output(raw)
    assert result.problems == []
    assert result.circuit is not None
    wave = result.circuit.components[0].waveform
    assert wave is not None and wave.shape == "pulse"
    assert (wave.period, wave.pulsed) == (pytest.approx(1e-3), 5.0)
    assert wave.width == pytest.approx(0.25e-3, rel=1e-3)


def test_all_problems_are_reported_together() -> None:
    raw = json.dumps(
        {
            "reply": "x",
            "circuit": {
                "title": "Broken",
                "components": [
                    {"id": "X1", "kind": "flux_capacitor", "pins": {"1": "A"}},
                    {"id": "R1", "kind": "resistor", "value": "lots", "pins": {"1": "A", "x": "B"}},
                    {"id": "D1", "kind": "led", "pins": {"anode": "A", "cathode": "GND"}},
                ],
                "analyses": [{"type": "tran"}, {"type": "fourier"}],
            },
        }
    )
    result = parse_model_output(raw)
    assert result.circuit is None
    joined = "\n".join(result.problems)
    assert len(result.problems) == 5
    for fragment in ("flux_capacitor", "pin 'x'", "'lots'", "'stop_time' is required", "fourier"):
        assert fragment in joined


def test_erc_errors_and_validation_errors_become_readable_problems() -> None:
    erc = parse_model_output(
        '{"reply": "x", "circuit": {"title": "t", "components": '
        '[{"id": "R1", "kind": "resistor", "value": 1000, "pins": {"1": "A", "2": "B"}}]}}'
    )
    assert any("ground" in p for p in erc.problems)
    pydantic = parse_model_output(
        '{"reply": "x", "circuit": {"title": "t", "components": [{"id": "V1", "kind": "v", '
        '"value": 1, "pins": {"+": "A", "-": "GND"}}, {"id": "R1", "kind": "resistor", '
        '"value": 1, "pins": {"1": "A", "2": "GND"}}], "analyses": '
        '[{"type": "ac", "fstart": "1Meg", "fstop": 10}]}}'
    )
    assert pydantic.problems == [
        "Analysis 1 (ac): stop_frequency must be greater than start_frequency."
    ]


def test_question_only_and_unusable_answers() -> None:
    question = parse_model_output('{"reply": "A pull-up holds the line high.", "circuit": None}')
    assert (question.reply, question.circuit, question.problems) == (
        "A pull-up holds the line high.",
        None,
        [],
    )
    assert "no JSON" in parse_model_output("I think you should use a resistor.").problems[0]
    assert (
        "could not be parsed"
        in parse_model_output(
            '{"reply": "cut off',
        ).problems[0]
    )


def _source_waveform(waveform: object) -> object:
    answer = {
        "reply": "r",
        "circuit": {
            "title": "t",
            "components": [
                {"id": "V1", "kind": "voltage_source", "waveform": waveform, "pins": ["IN", "0"]},
                {"id": "R1", "kind": "resistor", "value": "1k", "pins": ["IN", "0"]},
            ],
        },
    }
    result = parse_model_output(json.dumps(answer))
    assert result.circuit is not None, result.problems
    return result.circuit.components[0].waveform


def test_ramps_profiles_and_bad_pulse_timings_are_accepted() -> None:
    ramp = _source_waveform({"shape": "ramp", "start": 18, "stop": "0", "duration": "5"})
    assert isinstance(ramp, PwlWave) and ramp.points == [(0, 18), (5, 0)]

    profile = _source_waveform({"type": "pwl", "points": [{"t": 0, "v": 18}, {"t": "10m", "v": 0}]})
    assert isinstance(profile, PwlWave) and profile.points[1] == (0.01, 0)

    # Weak models write slow pulses whose edges exceed the period, or zero widths; the intent
    # is clear, so the period is stretched and the width made positive instead of rejecting.
    pulse = _source_waveform(
        {
            "shape": "pulse",
            "initial": 18,
            "pulsed": 0,
            "rise": 5,
            "fall": 5,
            "width": 0,
            "period": 5,
        }
    )
    assert isinstance(pulse, PulseWave) and pulse.width > 0
    assert pulse.period >= pulse.rise + pulse.width + pulse.fall


def test_sensor_stimulus_synonyms_units_and_misplaced_profiles() -> None:
    answer = {
        "reply": "r",
        "circuit": {
            "title": "t",
            "components": [
                {"id": "V1", "kind": "battery", "value": "5V", "pins": ["VCC", "GND"]},
                {"id": "LDR1", "kind": "photoresistor", "light": "500 lux", "pins": ["VCC", "S"]},
                {
                    "id": "TH1",
                    "kind": "NTC",
                    "value": "10k",
                    # weak models put the environment profile under "waveform"
                    "waveform": {"shape": "ramp", "start": "20°C", "stop": 80, "duration": 1},
                    "pins": ["S", "GND"],
                },
                {
                    "id": "RV1",
                    "kind": "pot",
                    "value": "10k",
                    "position": "25%",
                    "pins": ["VCC", "W", "GND"],
                },
            ],
        },
    }
    result = parse_model_output(json.dumps(answer))
    assert result.circuit is not None, result.problems
    ldr, thermistor, pot = result.circuit.components[1:]
    assert ldr.stimulus == 500
    assert isinstance(thermistor.stimulus, PwlWave) and thermistor.waveform is None
    assert thermistor.stimulus.points == [(0, 20), (1, 80)]
    assert pot.stimulus == 0.25


def test_expectations_as_objects_or_sentences_and_bad_signals_are_problems() -> None:
    answer = json.loads(json.dumps(FEW_SHOT_EXAMPLES[0][1]))  # the LED example
    answer["circuit"]["expectations"] = [
        "I(D1) > 12m",
        {"name": "LED on", "signal": "I(D1)", "condition": "> 10m", "while": "V(VCC) > 8"},
    ]
    result = parse_model_output(json.dumps(answer))
    assert result.circuit is not None, result.problems
    first, second = result.circuit.expectations
    assert (first.signal, first.check, first.when) == ("I(D1)", "> 12m", None)
    assert (second.description, second.check, second.when) == ("LED on", "> 10m", "V(VCC) > 8")

    answer["circuit"]["expectations"] = [{"description": "x", "signal": "V(NOPE)", "check": "> 1"}]
    problems = parse_model_output(json.dumps(answer)).problems
    assert any("net 'NOPE' does not exist" in p for p in problems)


def test_arduino_behaviors_from_loose_output_and_generated_sketch() -> None:
    answer = {
        "reply": "r",
        "circuit": {
            "title": "t",
            "components": [
                {
                    "id": "U1",
                    "kind": "Arduino",
                    "pins": {"GND": "GND", "13": "P13", "pin9": "P9", "a0": "S", "5v": "VCC"},
                    # mapping form, synonyms, percent duty
                    "program": {
                        "13": {"output": "toggle", "period": "0.5"},
                        "D9": {"mode": "pwm", "duty": "25%"},
                    },
                },
                {"id": "R1", "kind": "resistor", "value": "1k", "pins": ["P13", "GND"]},
                {"id": "R2", "kind": "resistor", "value": "1k", "pins": ["P9", "GND"]},
                {"id": "R3", "kind": "resistor", "value": "10k", "pins": ["VCC", "S"]},
                {"id": "R4", "kind": "resistor", "value": "10k", "pins": ["S", "GND"]},
            ],
        },
    }
    result = parse_model_output(json.dumps(answer))
    assert result.circuit is not None, result.problems
    arduino = result.circuit.components[0]
    assert arduino.behavior is not None
    blink, pwm = arduino.behavior
    assert (blink.pin, blink.output, blink.period) == ("D13", "blink", 0.5)
    assert (pwm.pin, pwm.output, pwm.duty) == ("D9", "pwm", 0.25)

    code = sketch(arduino)
    assert "analogWrite(9, 64);" in code  # 25% of 255
    assert "digitalWrite(13, (now % 500) < 250 ? HIGH : LOW);" in code
