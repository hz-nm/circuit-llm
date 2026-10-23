"""SPICE device library: ``.model`` / ``.subckt`` text for every model in the catalog.

Every model name listed in :data:`circuits_llm.domain.CATALOG` has an entry here
(a test enforces it). Discrete semiconductors use published Gummel-Poon / diode
parameters; MOSFETs use ngspice's 3-terminal ``VDMOS`` model (body tied to source)
fitted to datasheet threshold voltage, on-resistance and capacitances; op-amps
are behavioural subcircuits.

Only the entries a circuit actually uses are emitted (see :func:`library_text`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from circuits_llm.domain import ComponentKind

# --------------------------------------------------------------------------- discrete models


@dataclass(frozen=True, slots=True)
class DeviceModel:
    """A SPICE ``.model`` card. ``spice_name`` is what instance lines reference."""

    spice_name: str
    card: str  # "D(...)", "NPN(...)", "VDMOS(...)"

    @property
    def text(self) -> str:
        return f".model {self.spice_name} {self.card}"


def _diode(name: str, params: str) -> DeviceModel:
    return DeviceModel(f"D_{name.upper()}", f"D({params})")


def _led(colour: str, saturation_current: float, emission: float, series_r: float) -> DeviceModel:
    # Reverse rating of typical indicator LEDs is 5 V.
    return DeviceModel(
        f"D_LED_{colour.upper()}",
        f"D(IS={saturation_current:.3g} N={emission:g} RS={series_r:g} BV=5 IBV=10u CJO=30p)",
    )


def _bjt(name: str, polarity: str, params: str) -> DeviceModel:
    return DeviceModel(f"Q_{name.upper()}", f"{polarity}({params})")


def _vdmos(name: str, params: str) -> DeviceModel:
    return DeviceModel(f"M_{name.upper()}", f"VDMOS({params})")


DISCRETE_MODELS: Final[dict[ComponentKind, dict[str, DeviceModel]]] = {
    ComponentKind.DIODE: {
        "1N4148": _diode("1N4148", "IS=2.52n RS=0.568 N=1.752 CJO=4p M=0.4 TT=20n BV=100 IBV=100u"),
        "1N4007": _diode(
            "1N4007",
            "IS=7.02767n RS=0.0341512 N=1.80803 EG=1.05743 XTI=5 BV=1000 IBV=5e-08 "
            "CJO=1e-11 VJ=0.7 M=0.5 FC=0.5 TT=1e-07",
        ),
        "1N5819": _diode(
            "1N5819", "IS=31.7u RS=0.051 N=1.373 CJO=110p M=0.35 EG=0.69 XTI=2 BV=40 IBV=1m"
        ),
    },
    # Fitted for Vf at 20 mA: red 1.95 V, yellow 2.0 V, green 2.1 V, blue 3.1 V, white 3.15 V.
    ComponentKind.LED: {
        "red": _led("red", 3.92e-18, 2.0, 4.0),
        "green": _led("green", 2.16e-19, 2.0, 4.0),
        "yellow": _led("yellow", 1.49e-18, 2.0, 4.0),
        "blue": _led("blue", 3.51e-22, 2.5, 8.0),
        "white": _led("white", 1.62e-22, 2.5, 8.0),
    },
    ComponentKind.NPN: {
        "2N3904": _bjt(
            "2N3904",
            "NPN",
            "IS=1e-14 VAF=100 BF=300 IKF=0.4 XTB=1.5 BR=4 CJC=4e-12 CJE=8e-12 RB=20 RC=0.1 "
            "RE=0.1 TR=250e-9 TF=350e-12 ITF=1 VTF=2 XTF=3",
        ),
        "2N2222": _bjt(
            "2N2222",
            "NPN",
            "IS=1e-14 VAF=100 BF=200 IKF=0.3 XTB=1.5 BR=3 CJC=8e-12 CJE=25e-12 TR=100e-9 "
            "TF=400e-12 ITF=1 VTF=2 XTF=3 RB=10 RC=0.3 RE=0.2",
        ),
        "BC547": _bjt(
            "BC547",
            "NPN",
            "IS=2.39e-14 NF=1.008 ISE=3.545e-15 NE=1.541 BF=294.3 IKF=0.1357 VAF=63.2 "
            "NR=1.004 ISC=6.272e-14 NC=1.243 BR=7.946 IKR=0.1144 VAR=25.9 RB=1 IRB=1e-06 "
            "RBM=1 RE=0.4683 RC=0.85 XTB=0 EG=1.11 XTI=3 CJE=1.358e-11 VJE=0.65 MJE=0.3279 "
            "TF=4.391e-10 XTF=120 VTF=2.643 ITF=0.7495 PTF=0 CJC=3.728e-12 VJC=0.3997 "
            "MJC=0.2955 XCJC=0.6193 TR=1e-32 FC=0.9579",
        ),
    },
    ComponentKind.PNP: {
        "2N3906": _bjt(
            "2N3906",
            "PNP",
            "IS=1e-14 VAF=100 BF=200 IKF=0.4 XTB=1.5 BR=4 CJC=4.5e-12 CJE=10e-12 RB=20 "
            "RC=0.1 RE=0.1 TR=250e-9 TF=350e-12 ITF=1 VTF=2 XTF=3",
        ),
        "2N2907": _bjt(
            "2N2907",
            "PNP",
            "IS=1e-14 VAF=120 BF=250 IKF=0.3 XTB=1.5 BR=3 CJC=8e-12 CJE=30e-12 TR=100e-9 "
            "TF=400e-12 ITF=1 VTF=2 XTF=3 RB=10 RC=0.3 RE=0.2",
        ),
        "BC557": _bjt(
            "BC557",
            "PNP",
            "IS=3.83e-14 NF=1.008 ISE=1.22e-14 NE=1.528 BF=344.4 IKF=0.08039 VAF=21.11 "
            "NR=1.005 ISC=2.85e-13 NC=1.28 BR=14.84 IKR=0.047 VAR=32.02 RB=1 IRB=1e-06 "
            "RBM=1 RE=0.6202 RC=0.5713 XTB=0 EG=1.11 XTI=3 CJE=1.23e-11 VJE=0.6106 "
            "MJE=0.378 TF=5.6e-10 XTF=3.414 VTF=5.23 ITF=0.1483 PTF=0 CJC=1.084e-11 "
            "VJC=0.1 MJC=0.3302 XCJC=0.6288 TR=1e-32 FC=0.8",
        ),
    },
    # VDMOS fits: threshold, Rds(on) at |Vgs| = 10 V, input/reverse capacitance, body diode.
    ComponentKind.NMOS: {
        "2N7000": _vdmos(
            "2N7000",
            "VTO=2.1 KP=0.125 LAMBDA=0.01 RD=0.5 RS=0.3 RG=5 CGS=20p CGDMAX=20p CGDMIN=3p "
            "A=1 IS=1e-14 RB=0.5 CJO=30p BV=60",
        ),
        "BS170": _vdmos(
            "BS170",
            "VTO=2.1 KP=0.2 LAMBDA=0.01 RD=0.3 RS=0.2 RG=5 CGS=24p CGDMAX=24p CGDMIN=3p "
            "A=1 IS=1e-14 RB=0.5 CJO=30p BV=60",
        ),
        "IRFZ44N": _vdmos(
            "IRFZ44N",
            "VTO=3.0 KP=14 LAMBDA=0.005 RD=4m RS=3m RG=2 CGS=1.3n CGDMAX=1.5n CGDMIN=60p "
            "A=0.5 IS=1e-12 RB=5m CJO=1n BV=55",
        ),
    },
    ComponentKind.PMOS: {
        "BS250": _vdmos(
            "BS250",
            "PCHAN VTO=-2.0 KP=0.012 LAMBDA=0.01 RD=1.5 RS=0.5 RG=10 CGS=50p CGDMAX=30p "
            "CGDMIN=5p A=1 IS=1e-14 RB=1 CJO=40p BV=45",
        ),
        "IRF9540": _vdmos(
            "IRF9540",
            "PCHAN VTO=-3.0 KP=2.5 LAMBDA=0.005 RD=70m RS=30m RG=3 CGS=1.1n CGDMAX=1n "
            "CGDMIN=100p A=0.5 IS=1e-12 RB=20m CJO=800p BV=100",
        ),
    },
}


def discrete_model(kind: ComponentKind, model: str) -> DeviceModel | None:
    """Return the library model for ``kind``/``model`` (canonical catalog spelling)."""
    return DISCRETE_MODELS.get(kind, {}).get(model)


ZENER_TEST_CURRENT: Final = "1m"


def zener_model(spice_element: str, breakdown_v: float) -> DeviceModel:
    """Per-instance zener model whose breakdown voltage is the component's value."""
    if not (math.isfinite(breakdown_v) and breakdown_v > 0):
        raise ValueError("zener breakdown voltage must be a positive finite number")
    return DeviceModel(
        f"DZ_{spice_element.upper()}",
        f"D(IS=1e-14 N=1 RS=2 BV={breakdown_v:.6g} IBV={ZENER_TEST_CURRENT} CJO=100p TT=50n)",
    )


# --------------------------------------------------------------------------- op-amps

# Internal integrator resistance of the behavioural op-amp (sets gm = gain / R).
_OPAMP_INTERNAL_R: Final = 1e6
# Near-ideal clamp diode: ~10-15 mV forward drop at the integrator's current limit.
_CLAMP_DIODE: Final = "D(IS=1e-12 N=0.02)"


@dataclass(frozen=True, slots=True)
class OpAmpSpec:
    """Behavioural op-amp parameters.

    A transconductance stage (current limited by ``tanh`` to give the slew rate)
    drives an RC integrator that sets the open-loop gain and dominant pole; a unity
    buffer drives the output. With supplies connected the integrator node is
    diode-clamped to ``[V- + headroom_low, V+ - headroom_high]`` so the output
    saturates at the rails and recovers immediately (no wind-up).
    """

    gain: float  # open-loop DC gain (V/V)
    gbw_hz: float  # gain-bandwidth product
    slew_v_per_s: float
    headroom_high_v: float  # output swing limit below V+
    headroom_low_v: float  # output swing limit above V-

    @property
    def transconductance(self) -> float:
        return self.gain / _OPAMP_INTERNAL_R

    @property
    def pole_capacitance(self) -> float:
        pole_hz = self.gbw_hz / self.gain
        return 1.0 / (2 * math.pi * _OPAMP_INTERNAL_R * pole_hz)

    @property
    def current_limit(self) -> float:
        return self.slew_v_per_s * self.pole_capacitance


OPAMP_MODELS: Final[dict[str, OpAmpSpec]] = {
    "ideal": OpAmpSpec(
        gain=1e6, gbw_hz=1e9, slew_v_per_s=1e9, headroom_high_v=0.0, headroom_low_v=0.0
    ),
    "LM358": OpAmpSpec(
        gain=1e5, gbw_hz=1e6, slew_v_per_s=0.3e6, headroom_high_v=1.5, headroom_low_v=0.02
    ),
    "TL072": OpAmpSpec(
        gain=2e5, gbw_hz=3e6, slew_v_per_s=13e6, headroom_high_v=1.5, headroom_low_v=1.5
    ),
}


def opamp_subckt_name(model: str, with_supplies: bool) -> str:
    return f"OA_{model.upper()}_{5 if with_supplies else 3}"


def opamp_subckt(model: str, with_supplies: bool) -> str:
    """Subcircuit text. Pins: ``inp inn out`` (3-pin) or ``inp inn out vp vn`` (5-pin)."""
    spec = OPAMP_MODELS[model]
    name = opamp_subckt_name(model, with_supplies)
    gm_over_limit = spec.transconductance / spec.current_limit
    pins = "inp inn out vp vn" if with_supplies else "inp inn out"
    lines = [
        f".subckt {name} {pins}",
        f"BGM 0 n1 I={spec.current_limit:.6g}*tanh({gm_over_limit:.6g}*(V(inp)-V(inn)))",
        f"RINT n1 0 {_OPAMP_INTERNAL_R:.6g}",
        f"CINT n1 0 {spec.pole_capacitance:.6g}",
        "EOUT out 0 n1 0 1",
    ]
    if with_supplies:
        lines += [
            f"BHI hi 0 V=V(vp)-{spec.headroom_high_v:.6g}",
            f"BLO lo 0 V=V(vn)+{spec.headroom_low_v:.6g}",
            "DHI n1 hi DCLAMP",
            "DLO lo n1 DCLAMP",
            f".model DCLAMP {_CLAMP_DIODE}",
        ]
    lines.append(f".ends {name}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- assembly


def library_text(models: Iterable[DeviceModel], opamps: Iterable[tuple[str, bool]]) -> str:
    """Deduplicated library section for the given models and (op-amp model, supplies) pairs."""
    cards = sorted({m.spice_name: m.text for m in models}.items())
    subckts = sorted({opamp_subckt_name(m, s): opamp_subckt(m, s) for m, s in opamps}.items())
    return "\n".join([text for _, text in cards] + [text for _, text in subckts])
