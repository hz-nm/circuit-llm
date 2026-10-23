from __future__ import annotations

import pytest

from circuits_llm.domain import CATALOG, Circuit, ComponentKind
from circuits_llm.simulation import DISCRETE_MODELS, OPAMP_MODELS, parse_raw, to_spice
from circuits_llm.simulation.downsample import decimation_indices
from circuits_llm.simulation.library import opamp_subckt


def test_every_catalog_model_has_a_library_entry() -> None:
    for kind, spec in CATALOG.items():
        for model in spec.models:
            if kind is ComponentKind.OPAMP:
                assert model in OPAMP_MODELS
                assert opamp_subckt(model, with_supplies=False).startswith(".subckt")
                assert opamp_subckt(model, with_supplies=True).startswith(".subckt")
            else:
                assert model in DISCRETE_MODELS.get(kind, {}), f"{kind}: {model}"


def test_led_circuit_deck(led_circuit: Circuit) -> None:
    circuit = led_circuit.model_copy(update={"title": "LED\n.control\nshell rm -rf /"})
    deck = to_spice(circuit)
    lines = deck.text.splitlines()

    assert lines[0] == "* LED .control shell rm -rf /"  # title is one comment line
    assert "V1 VCC 0 DC 9" in lines
    assert "R1 R1_sense N1 330" in lines  # probed pin 1 goes through the sense source
    assert "VSENSE_R1 VCC R1_sense DC 0" in lines
    assert "D1 N1 0 D_LED_RED" in lines  # GND -> 0
    assert sum(line.startswith(".model") for line in lines) == 1  # only models in use
    assert "D_1N4148" not in deck.text
    assert [p.command for p in deck.analyses] == ["op"]
    assert deck.branch_currents == {"i(v1)": "V1", "i(vsense_r1)": "R1"}
    assert [t.name for t in deck.traces] == ["V(N1)", "I(R1)"]


def test_opamp_variant_follows_supply_pins() -> None:
    def deck_for(pins: dict[str, str]) -> str:
        circuit = Circuit.model_validate(
            {
                "title": "buffer",
                "components": [
                    {
                        "id": "V1",
                        "kind": "voltage_source",
                        "value": 1,
                        "pins": {"+": "IN", "-": "0"},
                    },
                    {"id": "U1", "kind": "opamp", "model": "TL072", "pins": pins},
                ],
            }
        )
        return to_spice(circuit).text

    base = {"in+": "IN", "in-": "OUT", "out": "OUT"}
    assert "XU1 IN OUT OUT OA_TL072_3" in deck_for(base)
    assert "XU1 IN OUT OUT VP 0 OA_TL072_5" in deck_for(base | {"v+": "VP", "v-": "GND"})


RAW_FIXTURE = """Title: * rc
Date: Fri Oct 23 21:35:34  2026
Plotname: AC Analysis
Flags: complex
No. Variables: 3
No. Points: 2
Variables:
\t0\tfrequency\tfrequency grid=3
\t1\tv(out)\tvoltage
\t2\tv1#branch\tcurrent
Values:
 0\t1.0e+01,0.0e+00
\t1.0e+00,-1.0e+00
\t-2.0e-03,0.0e+00
 1\t1.0e+02,0.0e+00
\t0.0e+00,-5.0e-01
\t-1.0e-03,1.0e-04
"""


def test_parse_ascii_raw() -> None:
    plot = parse_raw(RAW_FIXTURE)
    assert plot.plotname == "AC Analysis"
    assert plot.is_complex
    assert plot.names == ("frequency", "v(out)", "i(v1)")
    assert plot.real[0] == (10.0, 100.0)
    assert plot.imag is not None
    assert plot.imag[1] == (-1.0, -0.5)


def test_parse_raw_rejects_truncated_file() -> None:
    with pytest.raises(ValueError, match="truncated"):
        parse_raw(RAW_FIXTURE.rsplit("\n", 3)[0])


def test_decimation_keeps_spikes_and_bounds_points() -> None:
    flat = [0.0] * 10_000
    flat[4321] = 5.0
    keep = decimation_indices([flat], 100)
    assert len(keep) <= 100
    assert 4321 in keep
    assert keep[0] == 0 and keep[-1] == 9_999
