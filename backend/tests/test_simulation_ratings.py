from __future__ import annotations

from circuits_llm.domain import Circuit, Severity
from circuits_llm.simulation import OperatingPointResult, SimulationResult, SweepResult
from circuits_llm.simulation.ratings import check_ratings
from circuits_llm.simulation.results import Axis, Trace


def _op(voltages: dict[str, float], currents: dict[str, float]) -> SimulationResult:
    op = OperatingPointResult(node_voltages=voltages, branch_currents=currents)
    return SimulationResult(ok=True, netlist="", analyses=[op])


def test_overdriven_led_and_overvolted_logic_are_errors(led_circuit: Circuit) -> None:
    data = led_circuit.model_dump(mode="json")
    data["components"].append(
        {"id": "U1", "kind": "not_gate", "pins": {"a": "N1", "y": "Y", "vdd": "VCC", "vss": "GND"}}
    )  # 74HC by default
    circuit = Circuit.model_validate(data)
    result = _op({"VCC": 9.0, "N1": 2.1, "Y": 0.0}, {"V1": -0.2, "R1": 0.2, "D1": 0.2})

    issues = {(i.component_id, i.code): i for i in check_ratings(circuit, result)}

    assert issues[("D1", "overcurrent")].severity is Severity.ERROR  # 200 mA > 30 mA
    assert issues[("U1", "supply_overvoltage")].severity is Severity.ERROR  # 9 V > 6 V
    assert issues[("R1", "resistor_power")].severity is Severity.WARNING  # 6.9 V x 0.2 A


def test_transient_spikes_use_average_current(led_circuit: Circuit) -> None:
    # A 1 ms, 60 mA turn-on spike in a 100 ms run averages well under the 30 mA rating.
    time = [0.0, 0.001, 0.0011, 0.1]
    current = [0.06, 0.06, 0.015, 0.015]
    tran = SweepResult(
        type="tran",
        x=Axis(name="time", unit="s", values=time),
        traces=[
            Trace(name="V(N1)", unit="V", values=[2.0] * 4, net="N1"),
            Trace(name="V(VCC)", unit="V", values=[9.0] * 4, net="VCC"),
            Trace(name="I(D1)", unit="A", values=current, component="D1"),
        ],
    )
    result = SimulationResult(ok=True, netlist="", analyses=[tran])

    assert not [i for i in check_ratings(led_circuit, result) if i.component_id == "D1"]
