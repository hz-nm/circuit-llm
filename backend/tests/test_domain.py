from __future__ import annotations

import pytest

from circuits_llm.domain import (
    GROUND_NET,
    Circuit,
    ValueParseError,
    check_circuit,
    format_si,
    has_errors,
    parse_value,
    to_mermaid,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10k", 10e3),
        ("4.7 kΩ", 4.7e3),
        ("100nF", 100e-9),
        ("2.2uF", 2.2e-6),
        ("1M", 1e6),
        ("1MEG", 1e6),
        ("10m", 10e-3),
        ("10mA", 10e-3),
        ("1MHz", 1e6),
        ("10F", 10.0),
        ("10f", 10e-15),
        ("4k7", 4.7e3),
        ("2R2", 2.2),
        ("1e-3", 1e-3),
        (5, 5.0),
    ],
)
def test_parse_value(raw: str | float, expected: float) -> None:
    assert parse_value(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "abc", "10 parsecs", "nan", True])
def test_parse_value_rejects_garbage(raw: str | bool) -> None:
    with pytest.raises(ValueParseError):
        parse_value(raw)


def test_format_si() -> None:
    assert format_si(4700, "Ω") == "4.7 kΩ"
    assert format_si(1e-7, "F") == "100 nF"


def test_ground_aliases_normalize(led_circuit: Circuit) -> None:
    assert led_circuit.components[2].pins["cathode"] == GROUND_NET


def test_valid_circuit_has_no_errors(led_circuit: Circuit) -> None:
    assert not has_errors(check_circuit(led_circuit))


def test_erc_reports_all_problems_at_once() -> None:
    circuit = Circuit.model_validate(
        {
            "title": "broken",
            "components": [
                {"id": "V1", "kind": "voltage_source", "value": 5, "pins": {"+": "A", "-": "B"}},
                {"id": "V2", "kind": "voltage_source", "value": 3, "pins": {"+": "A", "-": "B"}},
                {"id": "R1", "kind": "resistor", "pins": {"1": "A", "3": "B"}},
                {
                    "id": "Q1",
                    "kind": "npn",
                    "model": "BC999",
                    "pins": {"collector": "A", "base": "B"},
                },
            ],
        }
    )
    codes = {issue.code for issue in check_circuit(circuit)}
    assert {
        "no_ground",
        "voltage_loop",
        "missing_value",
        "unknown_pin",
        "missing_pin",
        "unknown_model",
    } <= codes


def test_erc_detects_floating_gate() -> None:
    circuit = Circuit.model_validate(
        {
            "title": "floating gate",
            "components": [
                {
                    "id": "V1",
                    "kind": "voltage_source",
                    "value": 5,
                    "pins": {"+": "VDD", "-": "GND"},
                },
                {"id": "R1", "kind": "resistor", "value": 1000, "pins": {"1": "VDD", "2": "D"}},
                {"id": "M1", "kind": "nmos", "pins": {"drain": "D", "gate": "G", "source": "GND"}},
                {"id": "C1", "kind": "capacitor", "value": 1e-9, "pins": {"1": "G", "2": "GND"}},
            ],
        }
    )
    issues = check_circuit(circuit)
    assert [i.net for i in issues if i.code == "no_dc_path"] == ["G"]


def test_mermaid_mentions_every_component_and_net(led_circuit: Circuit) -> None:
    diagram = to_mermaid(led_circuit)
    assert diagram.startswith("flowchart LR")
    for token in ("C_V1", "C_R1", "C_D1", "N_VCC", "N_N1", "N_GND"):
        assert token in diagram
