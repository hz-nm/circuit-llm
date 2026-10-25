"""Catalog of supported component kinds: pins, values, models and accepted aliases.

This module is the single source of truth for what a component *is*. The LLM
prompt, the lenient LLM-output parser, the ERC, the SPICE emitter and the
frontend symbol set are all derived from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final


class ComponentKind(StrEnum):
    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    VOLTAGE_SOURCE = "voltage_source"
    CURRENT_SOURCE = "current_source"
    DIODE = "diode"
    LED = "led"
    ZENER = "zener"
    NPN = "npn"
    PNP = "pnp"
    NMOS = "nmos"
    PMOS = "pmos"
    OPAMP = "opamp"
    LAMP = "lamp"
    NOT_GATE = "not_gate"
    AND_GATE = "and_gate"
    OR_GATE = "or_gate"
    NAND_GATE = "nand_gate"
    NOR_GATE = "nor_gate"
    XOR_GATE = "xor_gate"
    SCHMITT_INVERTER = "schmitt_inverter"
    LDR = "ldr"
    THERMISTOR = "thermistor"
    PHOTODIODE = "photodiode"
    PHOTOTRANSISTOR = "phototransistor"
    GAS_SENSOR = "gas_sensor"
    PIR = "pir"
    POTENTIOMETER = "potentiometer"
    ARDUINO_UNO = "arduino_uno"


class Category(StrEnum):
    PASSIVE = "passive"
    SOURCE = "source"
    SEMICONDUCTOR = "semiconductor"
    INTEGRATED = "integrated"


class Family(StrEnum):
    """Groups of kinds the planner picks from, so prompts only describe what a design needs.

    ``core`` is always included.
    """

    CORE = "core"
    TRANSISTORS = "transistors"
    AMPLIFIERS = "amplifiers"
    LOGIC = "logic"
    SENSORS = "sensors"
    MICROCONTROLLERS = "microcontrollers"


FAMILY_DESCRIPTIONS: Final[dict[Family, str]] = {
    Family.CORE: "resistors, capacitors, inductors, sources, diodes, LEDs, zeners, lamps",
    Family.TRANSISTORS: "BJTs and MOSFETs for switching loads or amplifying",
    Family.AMPLIFIERS: "op-amps for amplifiers, filters, comparators and references",
    Family.LOGIC: "logic gates (NOT/AND/OR/NAND/NOR/XOR) and Schmitt-trigger inverters",
    Family.SENSORS: (
        "sensors driven by a simulated environment: light (LDR, photodiode, "
        "phototransistor), temperature (NTC thermistor), gas (MQ-2/MQ-135), motion (PIR "
        "module) and potentiometers (knob position)"
    ),
    Family.MICROCONTROLLERS: (
        "Arduino Uno whose pins are programmed with simple behaviours: on/off, blink, PWM, "
        "or 'high when an analog input crosses a threshold'"
    ),
}


@dataclass(frozen=True, slots=True)
class StimulusSpec:
    """The environment quantity a sensor responds to, given per component as ``stimulus``."""

    quantity: str  # "light", "temperature", ...
    unit: str  # "lux", "°C", ...
    default: float  # used when a circuit gives no stimulus
    minimum: float
    maximum: float
    hint: str  # e.g. "about 10000 lux in daylight, 1 lux at night"


@dataclass(frozen=True, slots=True)
class PinSpec:
    """One terminal of a component. ``name`` is canonical; ``aliases`` are accepted on input."""

    name: str
    description: str
    aliases: tuple[str, ...] = ()
    optional: bool = False


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    kind: ComponentKind
    display_name: str
    category: Category
    designator_prefix: str
    description: str
    pins: tuple[PinSpec, ...]
    value_unit: str | None = None
    value_required: bool = False
    value_description: str | None = None
    models: tuple[str, ...] = ()
    kind_aliases: tuple[str, ...] = field(default_factory=tuple)
    # Pin pairs with a DC conduction path through the device (used by the ERC).
    dc_paths: tuple[tuple[str, str], ...] = ()
    # Pins that the device actively drives relative to ground (e.g. an op-amp output).
    driven_pins: tuple[str, ...] = ()
    family: Family = Family.CORE
    # Optional (positive, negative) supply pins that must be connected together or not at all.
    supply_pins: tuple[str, str] | None = None
    stimulus: StimulusSpec | None = None

    @property
    def default_model(self) -> str | None:
        return self.models[0] if self.models else None

    @property
    def pin_names(self) -> tuple[str, ...]:
        return tuple(pin.name for pin in self.pins)

    @property
    def required_pins(self) -> tuple[str, ...]:
        return tuple(pin.name for pin in self.pins if not pin.optional)

    @property
    def is_source(self) -> bool:
        return self.category is Category.SOURCE

    def resolve_pin(self, raw: str) -> str | None:
        """Map a canonical pin name or alias (case-insensitive) to the canonical name."""
        needle = raw.strip().lower()
        for pin in self.pins:
            if needle == pin.name.lower() or needle in (a.lower() for a in pin.aliases):
                return pin.name
        return None


_TWO_TERMINAL = (
    PinSpec("1", "first terminal", aliases=("a", "p", "pos", "positive", "left", "top", "+")),
    PinSpec("2", "second terminal", aliases=("b", "n", "neg", "negative", "right", "bottom", "-")),
)

_DIODE_PINS = (
    PinSpec("anode", "anode (+, current enters here)", aliases=("a", "+", "p", "pos", "in", "1")),
    PinSpec(
        "cathode",
        "cathode (-, marked by the band)",
        aliases=("k", "c", "-", "n", "neg", "out", "2"),
    ),
)

_BJT_PINS = (
    PinSpec("collector", "collector", aliases=("c", "col")),
    PinSpec("base", "base", aliases=("b",)),
    PinSpec("emitter", "emitter", aliases=("e", "emit")),
)

_MOSFET_PINS = (
    PinSpec("drain", "drain", aliases=("d",)),
    PinSpec("gate", "gate", aliases=("g",)),
    PinSpec("source", "source (body is tied to source)", aliases=("s",)),
)

_BJT_PATHS = (("collector", "base"), ("base", "emitter"))
_DIODE_PATHS = (("anode", "cathode"),)

_SPECS: Final[tuple[ComponentSpec, ...]] = (
    ComponentSpec(
        kind=ComponentKind.RESISTOR,
        display_name="Resistor",
        category=Category.PASSIVE,
        designator_prefix="R",
        description="Ideal resistor.",
        pins=_TWO_TERMINAL,
        value_unit="Ω",
        value_required=True,
        value_description="resistance in ohms, e.g. '10k'",
        kind_aliases=("res", "r", "resistance"),
        dc_paths=(("1", "2"),),
    ),
    ComponentSpec(
        kind=ComponentKind.CAPACITOR,
        display_name="Capacitor",
        category=Category.PASSIVE,
        designator_prefix="C",
        description="Ideal capacitor (open circuit at DC).",
        pins=_TWO_TERMINAL,
        value_unit="F",
        value_required=True,
        value_description="capacitance in farads, e.g. '100n' or '10u'",
        kind_aliases=("cap", "c", "capacitance", "electrolytic_capacitor", "ceramic_capacitor"),
    ),
    ComponentSpec(
        kind=ComponentKind.INDUCTOR,
        display_name="Inductor",
        category=Category.PASSIVE,
        designator_prefix="L",
        description="Ideal inductor (short circuit at DC).",
        pins=_TWO_TERMINAL,
        value_unit="H",
        value_required=True,
        value_description="inductance in henries, e.g. '10m' or '100u'",
        kind_aliases=("ind", "l", "coil", "choke", "inductance"),
        dc_paths=(("1", "2"),),
    ),
    ComponentSpec(
        kind=ComponentKind.VOLTAGE_SOURCE,
        display_name="Voltage source",
        category=Category.SOURCE,
        designator_prefix="V",
        description=(
            "Independent voltage source; V(+) - V(-) = value. Use 'waveform' for sine/pulse "
            "signals and 'ac_magnitude' for AC analysis."
        ),
        pins=(
            PinSpec(
                "+", "positive terminal", aliases=("pos", "positive", "p", "plus", "1", "anode")
            ),
            PinSpec(
                "-", "negative terminal", aliases=("neg", "negative", "n", "minus", "2", "cathode")
            ),
        ),
        value_unit="V",
        value_description="DC voltage in volts, e.g. '9' or '3.3'",
        kind_aliases=(
            "vsource",
            "v",
            "voltage",
            "battery",
            "dc_source",
            "dc_voltage_source",
            "ac_source",
            "ac_voltage_source",
            "power_supply",
            "supply",
            "signal_source",
            "function_generator",
            "sine_source",
            "pulse_source",
        ),
        dc_paths=(("+", "-"),),
    ),
    ComponentSpec(
        kind=ComponentKind.CURRENT_SOURCE,
        display_name="Current source",
        category=Category.SOURCE,
        designator_prefix="I",
        description=(
            "Independent current source. Current enters at 'in', flows through the source "
            "and leaves at 'out' into the circuit."
        ),
        pins=(
            PinSpec("in", "current enters the source here", aliases=("+", "pos", "1", "from")),
            PinSpec("out", "current leaves the source here", aliases=("-", "neg", "2", "to")),
        ),
        value_unit="A",
        value_description="DC current in amperes, e.g. '1m'",
        kind_aliases=("isource", "i", "current", "dc_current_source"),
    ),
    ComponentSpec(
        kind=ComponentKind.DIODE,
        display_name="Diode",
        category=Category.SEMICONDUCTOR,
        designator_prefix="D",
        description="Rectifier or signal diode.",
        pins=_DIODE_PINS,
        models=("1N4148", "1N4007", "1N5819"),
        kind_aliases=("d", "rectifier", "schottky", "signal_diode", "rectifier_diode"),
        dc_paths=_DIODE_PATHS,
    ),
    ComponentSpec(
        kind=ComponentKind.LED,
        display_name="LED",
        category=Category.SEMICONDUCTOR,
        designator_prefix="D",
        description="Light-emitting diode; 'model' is its colour.",
        pins=_DIODE_PINS,
        models=("red", "green", "yellow", "blue", "white", "infrared"),
        kind_aliases=("light_emitting_diode", "led_diode"),
        dc_paths=_DIODE_PATHS,
    ),
    ComponentSpec(
        kind=ComponentKind.ZENER,
        display_name="Zener diode",
        category=Category.SEMICONDUCTOR,
        designator_prefix="D",
        description="Zener diode; in regulation the cathode sits at the higher potential.",
        pins=_DIODE_PINS,
        value_unit="V",
        value_required=True,
        value_description="breakdown voltage in volts, e.g. '5.1'",
        kind_aliases=("zener_diode", "z"),
        dc_paths=_DIODE_PATHS,
    ),
    ComponentSpec(
        kind=ComponentKind.NPN,
        family=Family.TRANSISTORS,
        display_name="NPN transistor",
        category=Category.SEMICONDUCTOR,
        designator_prefix="Q",
        description="NPN bipolar junction transistor.",
        pins=_BJT_PINS,
        models=("2N3904", "2N2222", "BC547"),
        kind_aliases=("npn_transistor", "npn_bjt", "bjt_npn", "bjt", "transistor"),
        dc_paths=_BJT_PATHS,
    ),
    ComponentSpec(
        kind=ComponentKind.PNP,
        family=Family.TRANSISTORS,
        display_name="PNP transistor",
        category=Category.SEMICONDUCTOR,
        designator_prefix="Q",
        description="PNP bipolar junction transistor.",
        pins=_BJT_PINS,
        models=("2N3906", "2N2907", "BC557"),
        kind_aliases=("pnp_transistor", "pnp_bjt", "bjt_pnp"),
        dc_paths=_BJT_PATHS,
    ),
    ComponentSpec(
        kind=ComponentKind.NMOS,
        family=Family.TRANSISTORS,
        display_name="N-channel MOSFET",
        category=Category.SEMICONDUCTOR,
        designator_prefix="M",
        description=(
            "N-channel enhancement MOSFET (gate draws no DC current). For loads above a few "
            "hundred mA use IRLZ44N when the gate is driven from 3.3-5 V logic, or IRFZ44N "
            "when about 10 V of gate drive is available."
        ),
        pins=_MOSFET_PINS,
        models=("2N7000", "BS170", "IRFZ44N", "IRLZ44N"),
        kind_aliases=("nmosfet", "n_mosfet", "nfet", "n_channel_mosfet", "mosfet", "nchannel"),
        dc_paths=(("drain", "source"),),
    ),
    ComponentSpec(
        kind=ComponentKind.PMOS,
        family=Family.TRANSISTORS,
        display_name="P-channel MOSFET",
        category=Category.SEMICONDUCTOR,
        designator_prefix="M",
        description="P-channel enhancement MOSFET (gate draws no DC current).",
        pins=_MOSFET_PINS,
        models=("BS250", "IRF9540"),
        kind_aliases=("pmosfet", "p_mosfet", "pfet", "p_channel_mosfet", "pchannel"),
        dc_paths=(("drain", "source"),),
    ),
    ComponentSpec(
        kind=ComponentKind.OPAMP,
        family=Family.AMPLIFIERS,
        supply_pins=("v+", "v-"),
        display_name="Op-amp",
        category=Category.INTEGRATED,
        designator_prefix="U",
        description=(
            "Operational amplifier. Inputs draw no current. If supply pins are connected the "
            "output is limited to the supply rails; otherwise it is ideal and unlimited."
        ),
        pins=(
            PinSpec(
                "in+",
                "non-inverting input",
                aliases=(
                    "+",
                    "inp",
                    "in_p",
                    "non_inverting",
                    "noninverting",
                    "plus",
                    "+in",
                    "vin+",
                ),
            ),
            PinSpec(
                "in-",
                "inverting input",
                aliases=("-", "inn", "in_n", "inverting", "minus", "-in", "vin-"),
            ),
            PinSpec("out", "output", aliases=("output", "o", "vout")),
            PinSpec(
                "v+",
                "positive supply",
                aliases=("vcc", "vdd", "vs+", "v_pos", "supply+", "vpos"),
                optional=True,
            ),
            PinSpec(
                "v-",
                "negative supply",
                aliases=("vee", "vss", "vs-", "v_neg", "supply-", "vneg"),
                optional=True,
            ),
        ),
        models=("ideal", "LM358", "TL072"),
        kind_aliases=("op_amp", "operational_amplifier", "opa", "comparator_opamp", "amplifier"),
        driven_pins=("out",),
    ),
    ComponentSpec(
        kind=ComponentKind.LAMP,
        display_name="Lamp",
        category=Category.PASSIVE,
        designator_prefix="LA",
        description=(
            "A load such as a light bulb, LED bulb/module or heater, rated for 'model' volts. "
            "Simulated as a resistor drawing the rated power at the rated voltage. Use it for "
            "anything drawing more than about 1 W; a plain 'led' is a small indicator LED."
        ),
        pins=_TWO_TERMINAL,
        value_unit="W",
        value_required=True,
        value_description="rated power in watts, e.g. '50'",
        models=("12V", "5V", "24V", "230V"),
        kind_aliases=("bulb", "light_bulb", "led_bulb", "led_lamp", "led_module", "load", "heater"),
        dc_paths=(("1", "2"),),
    ),
)

_GATE_SUPPLIES = (
    PinSpec("vdd", "positive supply", aliases=("vcc", "v+", "vs+", "supply+"), optional=True),
    PinSpec("vss", "negative supply / ground", aliases=("vee", "v-", "supply-"), optional=True),
)
_GATE_IN_A = PinSpec("a", "input A", aliases=("in", "in1", "a1", "input", "i1"))
_GATE_IN_B = PinSpec("b", "input B", aliases=("in2", "b1", "i2"))
_GATE_OUT = PinSpec("y", "output", aliases=("out", "output", "q", "o", "z"))
_LOGIC_MODELS = ("74HC", "CD4000")
_LOGIC_NOTE = (
    "Inputs draw no current, so every input must be driven (never left floating). If 'vdd' "
    "and 'vss' are connected the output swings between them; otherwise it is a 5 V logic gate."
)


def _gate(kind: ComponentKind, name: str, function: str, aliases: tuple[str, ...]) -> ComponentSpec:
    single_input = kind in (ComponentKind.NOT_GATE, ComponentKind.SCHMITT_INVERTER)
    inputs = (_GATE_IN_A,) if single_input else (_GATE_IN_A, _GATE_IN_B)
    return ComponentSpec(
        kind=kind,
        display_name=name,
        category=Category.INTEGRATED,
        family=Family.LOGIC,
        designator_prefix="U",
        description=f"{function} {_LOGIC_NOTE}",
        pins=(*inputs, _GATE_OUT, *_GATE_SUPPLIES),
        models=_LOGIC_MODELS,
        kind_aliases=aliases,
        driven_pins=("y",),
        supply_pins=("vdd", "vss"),
    )


_LIGHT = StimulusSpec(
    "light",
    "lux",
    default=500,
    minimum=0,
    maximum=200_000,
    hint="about 50000 in sunlight, 500 indoors, 10 at dusk, 0.1 at night",
)
_SENSORS_NOTE = (
    "Give 'stimulus' as a constant or as a waveform over time (e.g. pwl from day to night)."
)

_SENSOR_SPECS: Final[tuple[ComponentSpec, ...]] = (
    ComponentSpec(
        kind=ComponentKind.LDR,
        display_name="Light-dependent resistor",
        category=Category.PASSIVE,
        family=Family.SENSORS,
        designator_prefix="LDR",
        description=(
            "Photoresistor: resistance falls as light rises (GL5528: about 1 M in the dark, "
            "15 k at 10 lux, 3 k at 100 lux). Use it in a divider with a resistor. " + _SENSORS_NOTE
        ),
        pins=_TWO_TERMINAL,
        models=("GL5528", "GL5539"),
        kind_aliases=("photoresistor", "light_sensor", "light_dependent_resistor", "cds"),
        dc_paths=(("1", "2"),),
        stimulus=_LIGHT,
    ),
    ComponentSpec(
        kind=ComponentKind.THERMISTOR,
        display_name="NTC thermistor",
        category=Category.PASSIVE,
        family=Family.SENSORS,
        designator_prefix="TH",
        description=(
            "NTC thermistor: resistance falls as temperature rises; 'value' is its resistance "
            "at 25 °C and 'model' its B constant. " + _SENSORS_NOTE
        ),
        pins=_TWO_TERMINAL,
        value_unit="Ω",
        value_required=True,
        value_description="resistance at 25 °C, e.g. '10k'",
        models=("B3950", "B3435"),
        kind_aliases=("ntc", "ntc_thermistor", "temperature_sensor", "temp_sensor"),
        dc_paths=(("1", "2"),),
        stimulus=StimulusSpec(
            "temperature",
            "°C",
            default=25,
            minimum=-55,
            maximum=150,
            hint="e.g. 25 room, 0 freezing, 100 boiling",
        ),
    ),
    ComponentSpec(
        kind=ComponentKind.PHOTODIODE,
        display_name="Photodiode",
        category=Category.SEMICONDUCTOR,
        family=Family.SENSORS,
        designator_prefix="D",
        description=(
            "Photodiode (BPW34): light makes a current of about 50 nA per lux flow from cathode "
            "to anode. Reverse-bias it (cathode to the positive side) into a resistor or an "
            "op-amp transimpedance stage. Also works as an IR receiver. " + _SENSORS_NOTE
        ),
        pins=_DIODE_PINS,
        models=("BPW34",),
        kind_aliases=("photo_diode", "ir_receiver", "ir_photodiode"),
        dc_paths=_DIODE_PATHS,
        stimulus=_LIGHT,
    ),
    ComponentSpec(
        kind=ComponentKind.PHOTOTRANSISTOR,
        display_name="Phototransistor",
        category=Category.SEMICONDUCTOR,
        family=Family.SENSORS,
        designator_prefix="Q",
        description=(
            "NPN phototransistor (TEPT5700): collector current of about 0.4 uA per lux, so "
            "40 uA at 100 lux. Use it with a load resistor from collector to the supply. "
            + _SENSORS_NOTE
        ),
        pins=(
            PinSpec("collector", "collector", aliases=("c",)),
            PinSpec("emitter", "emitter", aliases=("e",)),
        ),
        models=("TEPT5700",),
        kind_aliases=("photo_transistor", "ambient_light_sensor", "ir_phototransistor"),
        dc_paths=(("collector", "emitter"),),
        stimulus=_LIGHT,
    ),
    ComponentSpec(
        kind=ComponentKind.GAS_SENSOR,
        display_name="Gas sensor",
        category=Category.PASSIVE,
        family=Family.SENSORS,
        designator_prefix="GS",
        description=(
            "MQ-series gas sensor element (the heater is not modelled): its resistance falls "
            "as gas concentration rises. MQ-2 senses smoke/LPG, MQ-135 air quality (CO2). Put "
            "it in a divider with a 10k load resistor from the supply. " + _SENSORS_NOTE
        ),
        pins=_TWO_TERMINAL,
        models=("MQ-2", "MQ-135"),
        kind_aliases=(
            "mq2",
            "mq_2",
            "mq135",
            "mq_135",
            "smoke_sensor",
            "gas",
            "air_quality_sensor",
        ),
        dc_paths=(("1", "2"),),
        stimulus=StimulusSpec(
            "gas",
            "ppm",
            default=0,
            minimum=0,
            maximum=10_000,
            hint="0 for clean air; e.g. 1000 ppm smoke/LPG (MQ-2), 400-2000 ppm CO2 (MQ-135)",
        ),
    ),
    ComponentSpec(
        kind=ComponentKind.PIR,
        display_name="PIR motion sensor",
        category=Category.INTEGRATED,
        family=Family.SENSORS,
        designator_prefix="U",
        description=(
            "PIR motion sensor module (HC-SR501): 'out' is 3.3 V while motion is detected and "
            "0 V otherwise. Power 'vcc' from 4.5-20 V. The stimulus is motion: 1 = moving, "
            "0 = still. " + _SENSORS_NOTE
        ),
        pins=(
            PinSpec("vcc", "supply", aliases=("v+", "vin", "+")),
            PinSpec("out", "digital output", aliases=("output", "signal", "o")),
            PinSpec("gnd", "ground", aliases=("-", "v-")),
        ),
        models=("HC-SR501",),
        kind_aliases=("pir_sensor", "motion_sensor", "hc_sr501", "pir_module"),
        driven_pins=("out",),
        dc_paths=(("vcc", "gnd"),),
        stimulus=StimulusSpec(
            "motion",
            "",
            default=0,
            minimum=0,
            maximum=1,
            hint="1 while something moves, 0 otherwise (use a pulse for passers-by)",
        ),
    ),
    ComponentSpec(
        kind=ComponentKind.POTENTIOMETER,
        display_name="Potentiometer",
        category=Category.PASSIVE,
        family=Family.SENSORS,
        designator_prefix="RV",
        description=(
            "Potentiometer: 'value' is the total resistance between '1' and '2'; the wiper 'w' "
            "sits at the knob position (0 = at '1', 1 = at '2'). Turn the knob over time with "
            "a waveform stimulus."
        ),
        pins=(
            PinSpec("1", "end 1", aliases=("a", "ccw", "left")),
            PinSpec("w", "wiper", aliases=("wiper", "w1", "slider", "middle", "center", "3")),
            PinSpec("2", "end 2", aliases=("b", "cw", "right")),
        ),
        value_unit="Ω",
        value_required=True,
        value_description="total resistance, e.g. '10k'",
        kind_aliases=("pot", "trimmer", "trimpot", "variable_resistor", "rheostat"),
        dc_paths=(("1", "w"), ("w", "2")),
        stimulus=StimulusSpec(
            "position", "", default=0.5, minimum=0, maximum=1, hint="0 to 1 (0.5 = middle)"
        ),
    ),
)


_LOGIC_SPECS: Final[tuple[ComponentSpec, ...]] = (
    _gate(
        ComponentKind.NOT_GATE,
        "NOT gate",
        "Inverter: y = NOT a.",
        ("not", "inverter", "74hc04", "cd4069"),
    ),
    _gate(ComponentKind.AND_GATE, "AND gate", "y = a AND b.", ("and", "74hc08", "cd4081")),
    _gate(ComponentKind.OR_GATE, "OR gate", "y = a OR b.", ("or", "74hc32", "cd4071")),
    _gate(ComponentKind.NAND_GATE, "NAND gate", "y = NOT (a AND b).", ("nand", "74hc00", "cd4011")),
    _gate(ComponentKind.NOR_GATE, "NOR gate", "y = NOT (a OR b).", ("nor", "74hc02", "cd4001")),
    _gate(ComponentKind.XOR_GATE, "XOR gate", "y = a XOR b.", ("xor", "exclusive_or", "74hc86")),
    _gate(
        ComponentKind.SCHMITT_INVERTER,
        "Schmitt-trigger inverter",
        "Inverter with hysteresis: y goes low when a rises above about 60% of the supply and "
        "high again only when a falls below about 40%. Use it to turn slow or noisy signals "
        "(light sensors, RC delays, dusk detection) into clean switching without flicker.",
        ("schmitt", "schmitt_trigger", "74hc14", "cd40106"),
    ),
)

ARDUINO_DIGITAL_PINS: Final = tuple(f"D{n}" for n in range(2, 14))
ARDUINO_PWM_PINS: Final = frozenset({"D3", "D5", "D6", "D9", "D10", "D11"})
ARDUINO_ANALOG_PINS: Final = tuple(f"A{n}" for n in range(6))

_ARDUINO_SPEC: Final = ComponentSpec(
    kind=ComponentKind.ARDUINO_UNO,
    display_name="Arduino Uno",
    category=Category.INTEGRATED,
    family=Family.MICROCONTROLLERS,
    designator_prefix="U",
    description=(
        "Arduino Uno (5 V logic, powered over USB). Connect only the pins you use, and "
        "always 'GND'. '5V' and '3V3' can power small circuits. Digital pins D2-D13 are "
        "outputs programmed by 'behavior' (PWM only on D3, D5, D6, D9, D10, D11); analog "
        "pins A0-A5 are inputs read by 'rule' behaviours. Every connected D pin MUST have an "
        "entry in 'behavior' (that is how the Arduino is programmed; never write code). "
        "A pin can source at most about "
        "20 mA: drive LEDs through a resistor and larger loads through a transistor."
    ),
    pins=(
        PinSpec("5V", "5 V supply output", aliases=("+5v", "5v", "vcc"), optional=True),
        PinSpec("3V3", "3.3 V supply output", aliases=("3.3v", "3v3", "+3v3"), optional=True),
        PinSpec("GND", "ground", aliases=("gnd", "ground", "0v")),
        *(
            PinSpec(
                pin,
                "digital output" + (" (PWM)" if pin in ARDUINO_PWM_PINS else ""),
                aliases=(pin[1:], f"pin{pin[1:]}", f"pin_{pin[1:]}", f"digital{pin[1:]}"),
                optional=True,
            )
            for pin in ARDUINO_DIGITAL_PINS
        ),
        *(
            PinSpec(pin, "analog input", aliases=(f"analog{pin[1:]}",), optional=True)
            for pin in ARDUINO_ANALOG_PINS
        ),
    ),
    kind_aliases=("arduino", "uno", "arduino_uno_r3", "microcontroller", "mcu", "atmega328p"),
    dc_paths=(("5V", "GND"), ("3V3", "GND")),
    driven_pins=("5V", "3V3", *ARDUINO_DIGITAL_PINS),
)

CATALOG: Final[dict[ComponentKind, ComponentSpec]] = {
    spec.kind: spec for spec in (*_SPECS, *_LOGIC_SPECS, *_SENSOR_SPECS, _ARDUINO_SPEC)
}

_KIND_LOOKUP: Final[dict[str, ComponentKind]] = {
    key: spec.kind for spec in CATALOG.values() for key in (spec.kind.value, *spec.kind_aliases)
}


def spec_for(kind: ComponentKind) -> ComponentSpec:
    return CATALOG[kind]


def resolve_kind(raw: str) -> ComponentKind | None:
    """Map a kind name or alias (case/space/dash-insensitive) to a ``ComponentKind``."""
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return _KIND_LOOKUP.get(key)


def resolve_model(kind: ComponentKind, raw: str) -> str | None:
    """Map a model name (case-insensitive) to its canonical spelling for ``kind``."""
    needle = raw.strip().lower()
    for model in CATALOG[kind].models:
        if model.lower() == needle:
            return model
    return None
