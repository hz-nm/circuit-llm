"""Integration tests that run the real ngspice binary (skipped when it is not installed)."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

import pytest

from circuits_llm.domain import Circuit
from circuits_llm.simulation import (
    NgspiceSimulator,
    OperatingPointResult,
    SimulationResult,
    SweepResult,
    locate_ngspice,
    simulation_issues,
)

NGSPICE = locate_ngspice()
requires_ngspice = pytest.mark.skipif(NGSPICE is None, reason="ngspice not found")


def _vsrc(id_: str, pos: str, neg: str, **extra: Any) -> dict[str, Any]:
    return {"id": id_, "kind": "voltage_source", "pins": {"+": pos, "-": neg}, **extra}


def _two_pin(kind: str, id_: str, a: str, b: str, value: float) -> dict[str, Any]:
    return {"id": id_, "kind": kind, "value": value, "pins": {"1": a, "2": b}}


def _simulate(data: dict[str, Any], timeout_s: float = 30) -> SimulationResult:
    assert NGSPICE is not None
    simulator = NgspiceSimulator(NGSPICE, timeout_s=timeout_s)
    return asyncio.run(simulator.simulate(Circuit.model_validate(data)))


def _op(result: SimulationResult) -> OperatingPointResult:
    assert result.ok, result.error
    op = result.analyses[0]
    assert isinstance(op, OperatingPointResult)
    return op


def _sweep(result: SimulationResult, index: int) -> SweepResult:
    sweep = result.analyses[index]
    assert isinstance(sweep, SweepResult)
    return sweep


@requires_ngspice
def test_led_current(led_circuit: Circuit) -> None:
    op = _op(_simulate(led_circuit.model_dump()))
    assert op.branch_currents["R1"] == pytest.approx(0.0213, rel=0.03)
    assert 1.8 < op.node_voltages["N1"] < 2.1
    assert "GND" not in op.node_voltages


@requires_ngspice
def test_rc_lowpass_corner() -> None:
    result = _simulate(
        {
            "title": "RC low-pass",
            "components": [
                _vsrc("V1", "IN", "GND", value=0, ac_magnitude=1),
                _two_pin("resistor", "R1", "IN", "OUT", 1e3),
                _two_pin("capacitor", "C1", "OUT", "GND", 100e-9),
            ],
            "analyses": [{"type": "ac", "start_frequency": 10, "stop_frequency": 1e6}],
            "probes": [{"kind": "voltage", "target": "OUT"}],
        }
    )
    assert result.ok, result.error
    ac = _sweep(result, 1)
    trace = ac.traces[0]
    assert ac.x.log_scale and trace.phase_deg is not None
    corner = min(range(len(trace.values)), key=lambda i: abs(trace.values[i] - math.sqrt(0.5)))
    assert ac.x.values[corner] == pytest.approx(1591.5, rel=0.1)
    assert trace.phase_deg[corner] == pytest.approx(-45, abs=4)


@requires_ngspice
def test_common_emitter_bias_is_active() -> None:
    op = _op(
        _simulate(
            {
                "title": "CE amplifier",
                "components": [
                    _vsrc("VCC", "VCC", "GND", value=12),
                    _two_pin("resistor", "RB1", "VCC", "B", 47e3),
                    _two_pin("resistor", "RB2", "B", "GND", 10e3),
                    _two_pin("resistor", "RC", "VCC", "C", 4.7e3),
                    _two_pin("resistor", "RE", "E", "GND", 1e3),
                    {
                        "id": "Q1",
                        "kind": "npn",
                        "model": "2N3904",
                        "pins": {"collector": "C", "base": "B", "emitter": "E"},
                    },
                ],
            }
        )
    )
    v = op.node_voltages
    assert 0.6 < v["B"] - v["E"] < 0.75
    assert v["C"] - v["E"] > 1.0  # not saturated


@requires_ngspice
def test_inverting_opamp_gain_and_clipping() -> None:
    result = _simulate(
        {
            "title": "Inverting amplifier",
            "components": [
                _vsrc(
                    "VIN",
                    "IN",
                    "GND",
                    value=0.1,
                    waveform={"shape": "sine", "amplitude": 2, "frequency": 1e3},
                ),
                _vsrc("VP1", "VP", "GND", value=12),
                _vsrc("VN1", "GND", "VN", value=12),
                _two_pin("resistor", "R1", "IN", "INV", 10e3),
                _two_pin("resistor", "R2", "INV", "OUT", 100e3),
                {
                    "id": "U1",
                    "kind": "opamp",
                    "model": "TL072",
                    "pins": {"in+": "GND", "in-": "INV", "out": "OUT", "v+": "VP", "v-": "VN"},
                },
            ],
            "analyses": [{"type": "tran", "stop_time": 2e-3, "step_time": 2e-6}],
            "probes": [{"kind": "voltage", "target": "OUT"}],
        }
    )
    assert _op(result).node_voltages["OUT"] == pytest.approx(-1.0, rel=0.01)  # gain -10
    out = _sweep(result, 1).traces[0].values
    assert 9.5 < max(out) < 12 and -12 < min(out) < -9.5  # clipped near the rails


@requires_ngspice
def test_rc_charging_transient() -> None:
    result = _simulate(
        {
            "title": "RC charging",
            "components": [
                _vsrc(
                    "V1",
                    "IN",
                    "GND",
                    waveform={
                        "shape": "pulse",
                        "initial": 0,
                        "pulsed": 5,
                        "width": 5e-3,
                        "period": 10e-3,
                    },
                ),
                _two_pin("resistor", "R1", "IN", "OUT", 1e3),
                _two_pin("capacitor", "C1", "OUT", "GND", 1e-6),
            ],
            "analyses": [{"type": "tran", "stop_time": 3e-3, "step_time": 1e-6}],
            "probes": [{"kind": "voltage", "target": "OUT"}],
        }
    )
    assert result.ok, result.error
    tran = _sweep(result, 1)
    at_tau = min(range(len(tran.x.values)), key=lambda i: abs(tran.x.values[i] - 1e-3))
    assert tran.traces[0].values[at_tau] == pytest.approx(5 * (1 - math.exp(-1)), rel=0.02)


@requires_ngspice
def test_street_lamp_schmitt_hysteresis() -> None:
    # Panel voltage falls 18 -> 0 V (dusk) then rises back (dawn); a Schmitt inverter on
    # a divider drives a MOSFET switching a 50 W / 12 V lamp.
    dusk_to_dawn = {
        "shape": "pulse", "initial": 18, "pulsed": 0, "rise": 0.4, "fall": 0.4,
        "width": 0.1, "period": 1.0,
    }  # fmt: skip
    result = _simulate(
        {
            "title": "street lamp",
            "components": [
                _vsrc("VBAT", "VBAT", "GND", value=12),
                _vsrc("VSOLAR", "SOLAR", "GND", waveform=dusk_to_dawn),
                _two_pin("resistor", "R1", "SOLAR", "SENSE", 10e3),
                _two_pin("resistor", "R2", "SENSE", "GND", 22e3),
                {
                    "id": "U1",
                    "kind": "schmitt_inverter",
                    "model": "CD4000",  # 74HC would be over its 6 V supply limit at 12 V
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
            "analyses": [{"type": "tran", "stop_time": 1.0, "step_time": 1e-3}],
        }
    )
    assert result.ok, result.error
    assert not [c.message for c in result.checks if c.severity == "error"]  # bench-safe
    tran = _sweep(result, 1)
    time = tran.x.values
    lamp_current = next(t.values for t in tran.traces if t.component == "LA1")

    def lamp_watts(at: float) -> float:
        index = min(range(len(time)), key=lambda i: abs(time[i] - at))
        return lamp_current[index] ** 2 * 2.88  # R = 12^2 / 50

    assert lamp_watts(0.02) < 1  # day: off
    assert lamp_watts(0.5) == pytest.approx(50, rel=0.05)  # night: full power
    assert lamp_watts(0.65) > 45  # dawn at 6.75 V: still on (hysteresis)
    assert lamp_watts(0.85) < 1  # bright again: off


@requires_ngspice
def test_timeout_becomes_issue() -> None:
    assert NGSPICE is not None
    circuit = Circuit.model_validate(
        {
            "title": "Too long",
            "components": [
                _vsrc(
                    "V1", "IN", "GND", waveform={"shape": "sine", "amplitude": 1, "frequency": 1e6}
                ),
                _two_pin("resistor", "R1", "IN", "GND", 1e3),
            ],
            "analyses": [{"type": "tran", "stop_time": 10, "step_time": 1e-9}],
        }
    )
    issues = asyncio.run(simulation_issues(NgspiceSimulator(NGSPICE, timeout_s=1), circuit))
    assert [i.code for i in issues] == ["simulation_failed"]
    assert "timed out" in issues[0].message


def test_missing_binary_does_not_raise(led_circuit: Circuit, tmp_path: Path) -> None:
    simulator = NgspiceSimulator(tmp_path / "no-such-ngspice.exe")
    result = asyncio.run(simulator.simulate(led_circuit))
    assert not result.ok
    assert result.error is not None and "Could not start ngspice" in result.error


LDR_STREET_LAMP: dict[str, Any] = {
    "title": "LDR street lamp",
    "components": [
        _vsrc("VBAT", "VBAT", "GND", value=12),
        {
            "id": "LDR1",
            "kind": "ldr",
            "pins": {"1": "VBAT", "2": "SENSE"},
            # daylight -> night -> daylight
            "stimulus": {"shape": "pwl", "points": [[0, 1000], [0.4, 0.5], [0.6, 0.5], [1, 1000]]},
        },
        _two_pin("resistor", "R1", "SENSE", "GND", 10e3),
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
    "analyses": [{"type": "tran", "stop_time": 1.0, "step_time": 1e-3}],
}


@requires_ngspice
def test_ldr_street_lamp_switches_at_dusk_with_hysteresis() -> None:
    result = _simulate(LDR_STREET_LAMP)
    assert result.ok, result.error
    assert not [c.message for c in result.checks if c.severity == "error"]
    tran = _sweep(result, 1)
    light = next(t.values for t in tran.traces if t.stimulus_of == "LDR1")
    lamp = next(t.values for t in tran.traces if t.component == "LA1")
    on = [abs(i) > 2 for i in lamp]  # 50 W at 12 V is about 4.2 A
    switches = [i for i in range(1, len(on)) if on[i] != on[i - 1]]
    assert len(switches) == 2  # on once at dusk, off once at dawn: no flicker
    turn_on_lux, turn_off_lux = light[switches[0]], light[switches[1]]
    assert 5 < turn_on_lux < 15  # dusk: LDR above ~15k pulls SENSE below VT- (4.7 V)
    assert 20 < turn_off_lux < 45  # dawn needs ~30 lux to pass VT+ (7.1 V): hysteresis
