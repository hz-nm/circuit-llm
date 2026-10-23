from __future__ import annotations

import pytest

from circuits_llm.domain import Circuit


@pytest.fixture
def led_circuit() -> Circuit:
    """9 V battery driving a red LED through a current-limiting resistor."""
    return Circuit.model_validate(
        {
            "title": "LED with resistor",
            "components": [
                {
                    "id": "V1",
                    "kind": "voltage_source",
                    "value": 9,
                    "pins": {"+": "VCC", "-": "GND"},
                },
                {"id": "R1", "kind": "resistor", "value": 330, "pins": {"1": "VCC", "2": "N1"}},
                {
                    "id": "D1",
                    "kind": "led",
                    "model": "red",
                    "pins": {"anode": "N1", "cathode": "0"},
                },
            ],
            "analyses": [{"type": "op"}],
            "probes": [{"kind": "voltage", "target": "N1"}, {"kind": "current", "target": "R1"}],
        }
    )
