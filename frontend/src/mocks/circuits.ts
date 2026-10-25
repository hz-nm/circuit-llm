/** Realistic mock circuits and simulation results, used by tests, the dev gallery and the mock API. */
import type { Circuit, SimulationResult } from "../api/types";

export const ledCircuit: Circuit = {
  title: "LED with current-limiting resistor",
  description: "A red LED driven from 9 V through a 470 Ω resistor (about 15 mA).",
  components: [
    { id: "V1", kind: "voltage_source", pins: { "+": "VCC", "-": "GND" }, value: 9 },
    { id: "R1", kind: "resistor", pins: { "1": "VCC", "2": "LED_A" }, value: 470 },
    { id: "D1", kind: "led", pins: { anode: "LED_A", cathode: "GND" }, model: "red" },
  ],
  analyses: [{ type: "op" }],
  probes: [],
};

export const rcLowPass: Circuit = {
  title: "RC low-pass filter",
  description: "First-order low-pass, fc ≈ 1.59 kHz.",
  components: [
    { id: "V1", kind: "voltage_source", pins: { "+": "IN", "-": "GND" }, value: 0, ac_magnitude: 1 },
    { id: "R1", kind: "resistor", pins: { "1": "IN", "2": "OUT" }, value: 1000 },
    { id: "C1", kind: "capacitor", pins: { "1": "OUT", "2": "GND" }, value: 100e-9 },
  ],
  analyses: [{ type: "ac", start_frequency: 10, stop_frequency: 1e6, points_per_decade: 20 }],
  probes: [{ kind: "voltage", target: "OUT" }],
};

export const opampAmplifier: Circuit = {
  title: "Non-inverting amplifier (gain 11)",
  description: "LM358 non-inverting amplifier on ±12 V rails.",
  components: [
    {
      id: "VIN",
      kind: "voltage_source",
      pins: { "+": "IN", "-": "GND" },
      waveform: { shape: "sine", offset: 0, amplitude: 0.5, frequency: 1000, delay: 0, phase_deg: 0 },
    },
    { id: "VCC", kind: "voltage_source", pins: { "+": "VPOS", "-": "GND" }, value: 12 },
    { id: "VEE", kind: "voltage_source", pins: { "+": "GND", "-": "VNEG" }, value: 12 },
    { id: "U1", kind: "opamp", pins: { "in+": "IN", "in-": "FB", out: "OUT", "v+": "VPOS", "v-": "VNEG" }, model: "LM358" },
    { id: "RF", kind: "resistor", pins: { "1": "FB", "2": "OUT" }, value: 10000 },
    { id: "RG", kind: "resistor", pins: { "1": "FB", "2": "GND" }, value: 1000 },
    { id: "RL", kind: "resistor", pins: { "1": "OUT", "2": "GND" }, value: 10000 },
  ],
  analyses: [{ type: "tran", stop_time: 3e-3, start_time: 0 }],
  probes: [
    { kind: "voltage", target: "IN" },
    { kind: "voltage", target: "OUT" },
  ],
};

export const transistorSwitch: Circuit = {
  title: "NPN low-side switch with flyback diode",
  description: "",
  components: [
    { id: "V1", kind: "voltage_source", pins: { "+": "VCC", "-": "GND" }, value: 12 },
    { id: "VCTL", kind: "voltage_source", pins: { "+": "CTL", "-": "GND" }, value: 5 },
    { id: "RB", kind: "resistor", pins: { "1": "CTL", "2": "N001" }, value: 4700 },
    { id: "Q1", kind: "npn", pins: { collector: "SW", base: "N001", emitter: "GND" }, model: "2N2222" },
    { id: "L1", kind: "inductor", pins: { "1": "VCC", "2": "SW" }, value: 0.01 },
    { id: "D1", kind: "diode", pins: { anode: "SW", cathode: "VCC" }, model: "1N4007" },
  ],
  analyses: [{ type: "op" }],
  probes: [],
};

/** Exercises the remaining symbols: PNP, NMOS, PMOS, zener and current source. */
export const symbolZoo: Circuit = {
  title: "Symbol zoo",
  description: "",
  components: [
    { id: "V1", kind: "voltage_source", pins: { "+": "VDD", "-": "GND" }, value: 5 },
    { id: "I1", kind: "current_source", pins: { in: "GND", out: "BIAS" }, value: 1e-3 },
    { id: "DZ1", kind: "zener", pins: { anode: "GND", cathode: "BIAS" }, value: 3.3 },
    { id: "Q2", kind: "pnp", pins: { emitter: "VDD", base: "BIAS", collector: "OUT1" }, model: "BC557" },
    { id: "R2", kind: "resistor", pins: { "1": "OUT1", "2": "GND" }, value: 2200 },
    { id: "M1", kind: "pmos", pins: { source: "VDD", gate: "OUT1", drain: "OUT2" }, model: "BS250" },
    { id: "M2", kind: "nmos", pins: { drain: "OUT2", gate: "OUT1", source: "GND" }, model: "2N7000" },
  ],
  analyses: [{ type: "op" }],
  probes: [],
};

/** Logic gates (IEEE distinctive shapes) and a lamp. */
export const logicZoo: Circuit = {
  title: "Logic zoo",
  description: "",
  components: [
    { id: "V1", kind: "voltage_source", pins: { "+": "VDD", "-": "GND" }, value: 5 },
    { id: "VA", kind: "voltage_source", pins: { "+": "A", "-": "GND" }, value: 5 },
    { id: "VB", kind: "voltage_source", pins: { "+": "B", "-": "GND" }, value: 0 },
    { id: "U1", kind: "not_gate", pins: { a: "A", y: "NA", vdd: "VDD", vss: "GND" } },
    { id: "U2", kind: "and_gate", pins: { a: "NA", b: "B", y: "AND1" } },
    { id: "U3", kind: "or_gate", pins: { a: "A", b: "B", y: "OR1" } },
    { id: "U4", kind: "nand_gate", pins: { a: "AND1", b: "OR1", y: "NAND1" } },
    { id: "U5", kind: "nor_gate", pins: { a: "A", b: "NAND1", y: "NOR1" } },
    { id: "U6", kind: "xor_gate", pins: { a: "NOR1", b: "B", y: "XOR1" } },
    { id: "U7", kind: "schmitt_inverter", pins: { a: "XOR1", y: "DRV" } },
    { id: "X1", kind: "lamp", pins: { "1": "DRV", "2": "GND" }, value: 50, model: "12V" },
  ],
  analyses: [{ type: "op" }],
  probes: [],
};

/** Every sensor kind (plus an IR LED), each seeing a simulated environment. */
export const sensorZoo: Circuit = {
  title: "Sensor zoo",
  description: "",
  components: [
    { id: "V1", kind: "voltage_source", pins: { "+": "VCC", "-": "GND" }, value: 5 },
    { id: "LDR1", kind: "ldr", model: "GL5528", stimulus: { shape: "pwl", points: [[0, 1000], [0.4, 0.5], [0.6, 0.5], [1, 1000]] }, pins: { "1": "VCC", "2": "LIGHT" } },
    { id: "R1", kind: "resistor", value: 10000, pins: { "1": "LIGHT", "2": "GND" } },
    { id: "TH1", kind: "thermistor", value: 10000, model: "B3950", stimulus: 43.2, pins: { "1": "VCC", "2": "TEMP" } },
    { id: "R2", kind: "resistor", value: 10000, pins: { "1": "TEMP", "2": "GND" } },
    { id: "GS1", kind: "gas_sensor", model: "MQ-135", stimulus: 400, pins: { "1": "VCC", "2": "GAS" } },
    { id: "R3", kind: "resistor", value: 20000, pins: { "1": "GAS", "2": "GND" } },
    { id: "PD1", kind: "photodiode", model: "BPW34", stimulus: 500, pins: { anode: "GND", cathode: "PD" } },
    { id: "R4", kind: "resistor", value: 100000, pins: { "1": "VCC", "2": "PD" } },
    { id: "Q1", kind: "phototransistor", model: "TEPT5700", stimulus: 200, pins: { collector: "PT", emitter: "GND" } },
    { id: "R5", kind: "resistor", value: 4700, pins: { "1": "VCC", "2": "PT" } },
    { id: "P1", kind: "pir", stimulus: { shape: "pulse", initial: 0, pulsed: 1, delay: 0.2, rise: 0.001, fall: 0.001, width: 0.3, period: 1 }, pins: { vcc: "VCC", out: "MOTION", gnd: "GND" } },
    { id: "RV1", kind: "potentiometer", value: 10000, stimulus: 0.25, pins: { "1": "VCC", w: "KNOB", "2": "GND" } },
    { id: "D1", kind: "led", model: "infrared", pins: { anode: "IRA", cathode: "GND" } },
    { id: "R6", kind: "resistor", value: 220, pins: { "1": "VCC", "2": "IRA" } },
  ],
  analyses: [{ type: "tran", stop_time: 1, start_time: 0 }],
  probes: [],
};

/** Arduino Uno night light (the backend generates its sketch). */
export const arduinoNightLight: Circuit = {
  title: "Arduino night light",
  description: "",
  components: [
    {
      id: "U1",
      kind: "arduino_uno",
      pins: { GND: "GND", "5V": "VCC", A0: "SENSE", D9: "PIN9", D13: "PIN13" },
      behavior: [
        { pin: "D9", output: "rule", when: "A0 > 2.5" },
        { pin: "D13", output: "blink", period: 0.25 },
      ],
    },
    { id: "R1", kind: "resistor", value: 10000, pins: { "1": "VCC", "2": "SENSE" } },
    { id: "LDR1", kind: "ldr", pins: { "1": "SENSE", "2": "GND" }, stimulus: { shape: "pwl", points: [[0, 1000], [0.4, 0.5], [0.6, 0.5], [1, 1000]] } },
    { id: "R2", kind: "resistor", value: 220, pins: { "1": "PIN9", "2": "LED" } },
    { id: "D1", kind: "led", pins: { anode: "LED", cathode: "GND" } },
    { id: "R3", kind: "resistor", value: 1000, pins: { "1": "PIN13", "2": "GND" } },
  ],
  analyses: [{ type: "tran", stop_time: 1, step_time: 0.001, start_time: 0 }],
  probes: [],
};

export const MOCK_CIRCUITS: readonly Circuit[] = [ledCircuit, rcLowPass, opampAmplifier, transistorSwitch, symbolZoo, logicZoo, sensorZoo, arduinoNightLight];

// ---------------------------------------------------------------------------- simulation results

export const ledOpResult: SimulationResult = {
  ok: true,
  netlist: "* LED with current-limiting resistor\nV1 VCC 0 DC 9\nR1 VCC LED_A 470\nD1 LED_A 0 LED_RED\n.op\n.end\n",
  analyses: [
    {
      type: "op",
      node_voltages: { VCC: 9, LED_A: 1.83 },
      branch_currents: { V1: -0.01526, R1: 0.01526, D1: 0.01526 },
    },
  ],
  error: null,
  log: "",
  duration_ms: 41,
};

function logspace(start: number, stop: number, perDecade: number): number[] {
  const decades = Math.log10(stop / start);
  const n = Math.round(decades * perDecade);
  return Array.from({ length: n + 1 }, (_, i) => start * 10 ** ((i * decades) / n));
}

const fc = 1 / (2 * Math.PI * 1000 * 100e-9);
const freqs = logspace(10, 1e6, 20);

export const rcAcResult: SimulationResult = {
  ok: true,
  netlist: "* RC low-pass filter\nV1 IN 0 DC 0 AC 1\nR1 IN OUT 1k\nC1 OUT 0 100n\n.ac dec 20 10 1meg\n.end\n",
  analyses: [
    {
      type: "ac",
      x: { name: "frequency", unit: "Hz", values: freqs, log_scale: true },
      traces: [
        { name: "V(IN)", unit: "V", values: freqs.map(() => 1), phase_deg: freqs.map(() => 0), net: "IN", probed: false },
        {
          name: "V(OUT)",
          unit: "V",
          values: freqs.map((f) => 1 / Math.sqrt(1 + (f / fc) ** 2)),
          phase_deg: freqs.map((f) => (-Math.atan(f / fc) * 180) / Math.PI),
          net: "OUT",
          probed: true,
        },
      ],
    },
  ],
  error: null,
  log: "",
  duration_ms: 63,
};

const times = Array.from({ length: 601 }, (_, i) => (i * 3e-3) / 600);

export const opampTranResult: SimulationResult = {
  ok: true,
  netlist: "* Non-inverting amplifier\n.tran 5u 3m\n.end\n",
  analyses: [
    {
      type: "tran",
      x: { name: "time", unit: "s", values: times, log_scale: false },
      traces: [
        { name: "V(IN)", unit: "V", values: times.map((t) => 0.5 * Math.sin(2 * Math.PI * 1000 * t)), phase_deg: null, net: "IN", probed: true },
        {
          name: "V(OUT)",
          unit: "V",
          values: times.map((t) => Math.max(-10.5, Math.min(10.5, 5.5 * Math.sin(2 * Math.PI * 1000 * t)))),
          phase_deg: null,
          net: "OUT",
          probed: true,
        },
        {
          name: "I(RL)",
          unit: "A",
          values: times.map((t) => Math.max(-10.5, Math.min(10.5, 5.5 * Math.sin(2 * Math.PI * 1000 * t))) / 1e4),
          phase_deg: null,
          net: null,
          probed: true,
          component: "RL",
        },
        { name: "V(FB)", unit: "V", values: times.map((t) => 0.5 * Math.sin(2 * Math.PI * 1000 * t)), phase_deg: null, net: "FB", probed: false },
        { name: "V(VPOS)", unit: "V", values: times.map(() => 12), phase_deg: null, net: "VPOS", probed: false },
        { name: "V(VNEG)", unit: "V", values: times.map(() => -12), phase_deg: null, net: "VNEG", probed: false },
      ],
    },
  ],
  error: null,
  log: "",
  duration_ms: 118,
};

const sweep = Array.from({ length: 51 }, (_, i) => i * 0.1);

export const dcSweepResult: SimulationResult = {
  ok: true,
  netlist: "* DC sweep\n.dc VCTL 0 5 0.1\n.end\n",
  analyses: [
    {
      type: "dc",
      x: { name: "VCTL", unit: "V", values: sweep, log_scale: false },
      traces: [
        { name: "V(SW)", unit: "V", values: sweep.map((v) => (v < 0.65 ? 12 : Math.max(0.1, 12 - (v - 0.65) * 30))), phase_deg: null, net: "SW", probed: true },
        { name: "V(CTL)", unit: "V", values: sweep, phase_deg: null, net: "CTL", probed: false },
        { name: "V(VCC)", unit: "V", values: sweep.map(() => 12), phase_deg: null, net: "VCC", probed: false },
      ],
    },
  ],
  error: null,
  log: "",
  duration_ms: 25,
};

export const failedResult: SimulationResult = {
  ok: false,
  netlist: "* broken\n.end\n",
  analyses: [],
  error: "singular matrix: node OUT is floating",
  log: "Circuit: broken\nError: singular matrix\ngmin stepping failed\nsource stepping failed\n",
  duration_ms: 12,
};
