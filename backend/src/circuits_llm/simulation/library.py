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

from circuits_llm.domain import CATALOG, Component, ComponentKind, PinBehavior
from circuits_llm.domain.arduino import ARDUINO_LOGIC_V, DEFAULT_PWM_HZ, rule_condition

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
        # 940 nm IR emitter: Vf ~1.2 V at 20 mA
        "infrared": _led("infrared", 6.9e-14, 1.7, 2.0),
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
        # Logic-level twin of the IRFZ44N, fitted to Rds(on) ~25 mOhm at Vgs = 5 V and
        # ~35 mOhm at 4 V (VTO 2 V).
        "IRLZ44N": _vdmos(
            "IRLZ44N",
            "VTO=2.0 KP=19 LAMBDA=0.005 RD=4m RS=3m RG=2 CGS=1.6n CGDMAX=1.5n CGDMIN=60p "
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


# --------------------------------------------------------------------------- logic gates


@dataclass(frozen=True, slots=True)
class LogicFamilySpec:
    """Behavioural CMOS logic parameters (thresholds are fractions of the supply)."""

    output_ohms: float  # output resistance
    delay_s: float  # propagation delay
    threshold: float  # switching threshold of plain gates
    schmitt_high: float  # Schmitt positive-going threshold VT+
    schmitt_low: float  # Schmitt negative-going threshold VT-


LOGIC_FAMILIES: Final[dict[str, LogicFamilySpec]] = {
    "74HC": LogicFamilySpec(
        output_ohms=50, delay_s=10e-9, threshold=0.5, schmitt_high=0.58, schmitt_low=0.38
    ),
    "CD4000": LogicFamilySpec(
        output_ohms=400, delay_s=60e-9, threshold=0.5, schmitt_high=0.59, schmitt_low=0.39
    ),
}

UNPOWERED_LOGIC_SUPPLY_V: Final = 5.0
_LOGIC_DELAY_R: Final = 1e3
_LOGIC_INPUT_R: Final = 1e12  # CMOS input leakage; keeps the matrix well-conditioned
_LOGIC_SUPPLY: Final = "V(vdd,vss)"
_LOGIC_WIDTH: Final = f"(0.02*{_LOGIC_SUPPLY}+1e-3)"  # tanh transition width: sharp yet smooth

# Logic functions on soft inputs A, B in [0, 1].
_LOGIC_FUNCTIONS: Final[dict[ComponentKind, str]] = {
    ComponentKind.NOT_GATE: "(1-A)",
    ComponentKind.AND_GATE: "(A*B)",
    ComponentKind.OR_GATE: "(A+B-A*B)",
    ComponentKind.NAND_GATE: "(1-A*B)",
    ComponentKind.NOR_GATE: "(1-(A+B-A*B))",
    ComponentKind.XOR_GATE: "(A+B-2*A*B)",
}
LOGIC_KINDS: Final = frozenset((*_LOGIC_FUNCTIONS, ComponentKind.SCHMITT_INVERTER))


def _soft_high(node: str, threshold: str) -> str:
    """0..1, switching smoothly as V(node) crosses ``threshold`` (both relative to vss)."""
    return f"0.5*(1+tanh((V({node},vss)-{threshold})/{_LOGIC_WIDTH}))"


def logic_subckt_name(kind: ComponentKind, model: str, with_supplies: bool) -> str:
    suffix = "" if with_supplies else "_5V"
    return f"CL_{kind.value.upper()}_{model.upper()}{suffix}"


def logic_subckt(kind: ComponentKind, model: str, with_supplies: bool) -> str:
    """Gate as: soft logic source -> RC propagation delay -> buffer -> output resistance."""
    family = LOGIC_FAMILIES[model]
    single_input = kind in (ComponentKind.NOT_GATE, ComponentKind.SCHMITT_INVERTER)
    inputs = ["a"] if single_input else ["a", "b"]
    ports = " ".join([*inputs, "y", *(["vdd", "vss"] if with_supplies else [])])
    lines = [f".subckt {logic_subckt_name(kind, model, with_supplies)} {ports}"]
    if not with_supplies:
        lines += [f"Vsup vdd 0 DC {UNPOWERED_LOGIC_SUPPLY_V:g}", "Vgnd vss 0 DC 0"]
    lines += [f"Rin_{pin} {pin} vss {_LOGIC_INPUT_R:g}" for pin in inputs]

    if kind is ComponentKind.SCHMITT_INVERTER:
        # The threshold follows the delayed output state: VT+ while the output is high,
        # VT- while it is low. That positive feedback is the hysteresis.
        span = family.schmitt_high - family.schmitt_low
        state = _soft_high("d", f"0.5*{_LOGIC_SUPPLY}")
        lines.append(f"Bth th vss V={_LOGIC_SUPPLY}*({family.schmitt_low}+{span:g}*{state})")
        lines.append(f"Blogic l vss V={_LOGIC_SUPPLY}*(1-{_soft_high('a', 'V(th,vss)')})")
    else:
        threshold = f"{family.threshold}*{_LOGIC_SUPPLY}"
        function = _LOGIC_FUNCTIONS[kind]
        function = function.replace("A", _soft_high("a", threshold))
        function = function.replace("B", _soft_high("b", threshold))
        lines.append(f"Blogic l vss V={_LOGIC_SUPPLY}*{function}")

    lines += [
        f"Rdelay l d {_LOGIC_DELAY_R:g}",
        f"Cdelay d vss {family.delay_s / _LOGIC_DELAY_R:g}",
        "Bbuf o vss V=V(d,vss)",
        f"Rout o y {family.output_ohms:g}",
        ".ends",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- sensors
#
# Each sensor is a subcircuit whose last port, ``stim``, carries the environment value
# (lux, degrees C, ppm, motion 0/1, knob position 0..1) as a voltage driven by a hidden
# source. Resistive sensors are behavioural current sources I = V / R(stimulus).

_MIN_SENSOR_OHMS: Final = 1e-2  # keeps behavioural resistances finite


@dataclass(frozen=True, slots=True)
class LdrSpec:
    ohms_at_10_lux: float
    gamma: float  # slope of log(R) against log(lux)
    dark_ohms: float


LDR_MODELS: Final[dict[str, LdrSpec]] = {
    "GL5528": LdrSpec(ohms_at_10_lux=15e3, gamma=0.7, dark_ohms=1e6),
    "GL5539": LdrSpec(ohms_at_10_lux=70e3, gamma=0.8, dark_ohms=5e6),
}
NTC_B_CONSTANTS: Final[dict[str, float]] = {"B3950": 3950.0, "B3435": 3435.0}


@dataclass(frozen=True, slots=True)
class GasSensorSpec:
    """Rs/R0 = (ppm / scale_ppm) ** -exponent, capped at the clean-air ratio."""

    r0_ohms: float
    scale_ppm: float
    exponent: float
    clean_air_ratio: float


GAS_SENSOR_MODELS: Final[dict[str, GasSensorSpec]] = {
    "MQ-2": GasSensorSpec(r0_ohms=10e3, scale_ppm=574.25, exponent=0.45, clean_air_ratio=9.8),
    "MQ-135": GasSensorSpec(r0_ohms=10e3, scale_ppm=116.6, exponent=0.361, clean_air_ratio=3.6),
}
PHOTODIODE_AMPS_PER_LUX: Final = {"BPW34": 50e-9}
PHOTOTRANSISTOR_AMPS_PER_LUX: Final = {"TEPT5700": 0.4e-6}
_PHOTOTRANSISTOR_BETA: Final = 400.0
PIR_OUTPUT_V: Final = 3.3
PIR_MIN_SUPPLY_V: Final = 4.5

SENSOR_KINDS: Final = frozenset(
    {
        ComponentKind.LDR,
        ComponentKind.THERMISTOR,
        ComponentKind.PHOTODIODE,
        ComponentKind.PHOTOTRANSISTOR,
        ComponentKind.GAS_SENSOR,
        ComponentKind.PIR,
        ComponentKind.POTENTIOMETER,
    }
)


def sensor_subckt_name(kind: ComponentKind, model: str | None) -> str:
    suffix = "" if model is None else "_" + model.upper().replace("-", "")
    return f"SNS_{kind.value.upper()}{suffix}"


def _clamped(expression: str, low: float, high: float) -> str:
    return f"min(max({expression},{low:g}),{high:g})"


def sensor_subckt(kind: ComponentKind, model: str | None) -> str:
    """Subcircuit text; ports are the catalog pins in order, then ``stim``."""
    name = sensor_subckt_name(kind, model)
    match kind:
        case ComponentKind.LDR:
            ldr = LDR_MODELS[model or "GL5528"]
            ohms = (
                f"min({ldr.dark_ohms:g},{ldr.ohms_at_10_lux:g}"
                f"*pow(max(V(stim),1e-3)/10,{-ldr.gamma:g}))"
            )
            return f".subckt {name} 1 2 stim\nB1 1 2 I=V(1,2)/{ohms}\n.ends"
        case ComponentKind.THERMISTOR:
            b = NTC_B_CONSTANTS[model or "B3950"]
            kelvin = f"({_clamped('V(stim)', -55, 150)}+273.15)"
            ohms = f"({{r25}}*exp({b:g}*(1/{kelvin}-1/298.15)))"
            return f".subckt {name} 1 2 stim params: r25=10k\nB1 1 2 I=V(1,2)/{ohms}\n.ends"
        case ComponentKind.GAS_SENSOR:
            gas = GAS_SENSOR_MODELS[model or "MQ-2"]
            ratio = (
                f"min({gas.clean_air_ratio:g},pow(max(V(stim),1)/{gas.scale_ppm:g},"
                f"{-gas.exponent:g}))"
            )
            return f".subckt {name} 1 2 stim\nB1 1 2 I=V(1,2)/({gas.r0_ohms:g}*{ratio})\n.ends"
        case ComponentKind.PHOTODIODE:
            per_lux = PHOTODIODE_AMPS_PER_LUX[model or "BPW34"]
            return "\n".join(
                [
                    f".subckt {name} a k stim",
                    "D1 a k DPHOTO",
                    f"Bphoto k a I={per_lux:g}*max(V(stim),0)",  # light: cathode -> anode
                    ".model DPHOTO D(IS=1e-9 N=1.9 RS=2 CJO=72p BV=60 IBV=10u)",
                    ".ends",
                ]
            )
        case ComponentKind.PHOTOTRANSISTOR:
            per_lux = PHOTOTRANSISTOR_AMPS_PER_LUX[model or "TEPT5700"]
            base_per_lux = per_lux / _PHOTOTRANSISTOR_BETA
            return "\n".join(
                [
                    f".subckt {name} c e stim",
                    "Q1 c b e QPHOTO",
                    f"Bphoto c b I={base_per_lux:g}*max(V(stim),0)",  # photo base current
                    f".model QPHOTO NPN(BF={_PHOTOTRANSISTOR_BETA:g} IS=1e-14 VAF=50 "
                    "CJC=10p CJE=10p)",
                    ".ends",
                ]
            )
        case ComponentKind.PIR:
            motion = "0.5*(1+tanh((V(stim)-0.5)/0.05))"
            powered = f"0.5*(1+tanh((V(vcc,gnd)-{PIR_MIN_SUPPLY_V - 0.5:g})/0.2))"
            return "\n".join(
                [
                    f".subckt {name} vcc out gnd stim",
                    "Rquiescent vcc gnd 66k",  # about 65 uA idle current
                    f"Bout o gnd V={PIR_OUTPUT_V:g}*{motion}*{powered}",
                    "Rout o out 1k",
                    ".ends",
                ]
            )
        case ComponentKind.POTENTIOMETER:
            position = _clamped("V(stim)", 0, 1)
            return "\n".join(
                [
                    f".subckt {name} 1 w 2 stim params: r=10k",
                    f"B1 1 w I=V(1,w)/max({{r}}*{position},{_MIN_SENSOR_OHMS:g})",
                    f"B2 w 2 I=V(w,2)/max({{r}}*(1-{position}),{_MIN_SENSOR_OHMS:g})",
                    ".ends",
                ]
            )
        case _:
            raise ValueError(f"{kind} is not a sensor")


# --------------------------------------------------------------------------- arduino
#
# Each Arduino is its own subcircuit (its pins are programmed per instance). Ports are
# the connected pins in catalog order. Programmed outputs drive through the ATmega's
# ~25 ohm output resistance; inputs are high impedance.

ARDUINO_PIN_OHMS: Final = 25.0
_ARDUINO_EDGE_S: Final = 100e-9
_RULE_WIDTH_V: Final = 0.01  # tanh width of a 'rule' threshold


def arduino_node(pin: str) -> str:
    return "p_" + pin.lower()


def _pin_drive(behavior: PinBehavior, target: str, gnd: str, nodes: dict[str, str]) -> str:
    """One element setting internal node ``target`` to the pin's 0/5 V drive."""
    high = ARDUINO_LOGIC_V
    name = behavior.pin
    match behavior.output:
        case "high" | "low":
            level = high if behavior.output == "high" else 0.0
            return f"Vdrv_{name} {target} {gnd} DC {level:g}"
        case "blink" | "pwm":
            if behavior.output == "blink":
                period = behavior.period or 1.0
            else:
                period = 1.0 / (behavior.frequency or DEFAULT_PWM_HZ)
            duty = behavior.duty if behavior.duty is not None else 0.5
            if duty <= 1e-3 or duty >= 1 - 1e-3:
                return f"Vdrv_{name} {target} {gnd} DC {high if duty > 0.5 else 0:g}"
            width = max(duty * period - _ARDUINO_EDGE_S, _ARDUINO_EDGE_S)
            pulse = (
                f"PULSE(0 {high:g} 0 {_ARDUINO_EDGE_S:g} {_ARDUINO_EDGE_S:g} {width:g} {period:g})"
            )
            return f"Vdrv_{name} {target} {gnd} DC 0 {pulse}"
        case "rule":
            signal, operator, threshold = rule_condition(behavior)
            if signal.target not in nodes:
                raise ValueError(f"rule input {signal.target} is not connected")
            reading = f"V({nodes[signal.target]},{gnd})"
            margin = (
                f"({reading}-{threshold:g})"
                if operator in (">", ">=")
                else f"({threshold:g}-{reading})"
            )
            return f"Bdrv_{name} {target} {gnd} V={high:g}*0.5*(1+tanh({margin}/{_RULE_WIDTH_V:g}))"


def arduino_subckt(component: Component) -> tuple[str, str]:
    """(subcircuit name, text) for one Arduino instance."""
    name = f"ARD_{component.id.upper()}"
    spec = CATALOG[ComponentKind.ARDUINO_UNO]
    ports = [pin.name for pin in spec.pins if pin.name in component.pins]
    nodes = {pin: arduino_node(pin) for pin in ports}
    gnd = nodes["GND"]
    lines = [f".subckt {name} {' '.join(nodes[p] for p in ports)}"]
    if "5V" in nodes:
        lines += [f"Vrail5 i_5v {gnd} DC 5", f"Rrail5 i_5v {nodes['5V']} 0.1"]
    if "3V3" in nodes:
        lines += [f"Vrail3 i_3v3 {gnd} DC 3.3", f"Rrail3 i_3v3 {nodes['3V3']} 0.5"]
    behaviors = {b.pin: b for b in component.behavior or []}
    for pin in ports:
        node = nodes[pin]
        if pin.startswith("A"):
            lines.append(f"Rin_{pin} {node} {gnd} 100Meg")
        elif pin.startswith("D"):
            behavior = behaviors.get(pin)
            if behavior is None:
                lines.append(f"Rin_{pin} {node} {gnd} 10Meg")
                continue
            inner = "i_" + pin.lower()
            lines.append(_pin_drive(behavior, inner, gnd, nodes))
            lines.append(f"Rout_{pin} {inner} {node} {ARDUINO_PIN_OHMS:g}")
    lines.append(".ends")
    return name, "\n".join(lines)


# --------------------------------------------------------------------------- library section


def library_text(
    models: Iterable[DeviceModel],
    opamps: Iterable[tuple[str, bool]],
    logic: Iterable[tuple[ComponentKind, str, bool]] = (),
    sensors: Iterable[tuple[ComponentKind, str | None]] = (),
    custom: Iterable[tuple[str, str]] = (),
) -> str:
    """Deduplicated library section for the models, op-amps, gates and sensors in use."""
    cards = sorted({m.spice_name: m.text for m in models}.items())
    subckts = {opamp_subckt_name(m, s): opamp_subckt(m, s) for m, s in opamps}
    subckts |= {logic_subckt_name(k, m, s): logic_subckt(k, m, s) for k, m, s in logic}
    subckts |= {sensor_subckt_name(k, m): sensor_subckt(k, m) for k, m in sensors}
    subckts |= dict(custom)  # per-instance subcircuits, e.g. programmed Arduinos
    return "\n".join([text for _, text in cards] + [text for _, text in sorted(subckts.items())])
