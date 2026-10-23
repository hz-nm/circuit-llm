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

export const MOCK_CIRCUITS: readonly Circuit[] = [ledCircuit, rcLowPass, opampAmplifier, transistorSwitch, symbolZoo];

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
        { name: "V(IN)", unit: "V", values: freqs.map(() => 1), phase_deg: freqs.map(() => 0) },
        {
          name: "V(OUT)",
          unit: "V",
          values: freqs.map((f) => 1 / Math.sqrt(1 + (f / fc) ** 2)),
          phase_deg: freqs.map((f) => (-Math.atan(f / fc) * 180) / Math.PI),
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
        { name: "V(IN)", unit: "V", values: times.map((t) => 0.5 * Math.sin(2 * Math.PI * 1000 * t)), phase_deg: null },
        {
          name: "V(OUT)",
          unit: "V",
          values: times.map((t) => Math.max(-10.5, Math.min(10.5, 5.5 * Math.sin(2 * Math.PI * 1000 * t)))),
          phase_deg: null,
        },
        {
          name: "I(RL)",
          unit: "A",
          values: times.map((t) => Math.max(-10.5, Math.min(10.5, 5.5 * Math.sin(2 * Math.PI * 1000 * t))) / 1e4),
          phase_deg: null,
        },
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
        { name: "V(SW)", unit: "V", values: sweep.map((v) => (v < 0.65 ? 12 : Math.max(0.1, 12 - (v - 0.65) * 30))), phase_deg: null },
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
