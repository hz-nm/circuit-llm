/**
 * What the multimeter shows for a component, computed from node voltages and
 * component currents at the cursor. Pure, so the card is easy to reason about.
 */
import type { Component } from "../../api/types";
import { SYMBOLS } from "../schematic/symbols";

export interface Reading {
  label: string;
  /** null when the value isn't available (e.g. current not recorded). */
  value: number | null;
  unit: "V" | "A" | "W";
  /** Short explanation shown as a tooltip. */
  hint?: string;
  /** Visually separate summary rows (V across, I, P) from pin voltages. */
  emphasis?: boolean;
}

export type VoltageOf = (net: string) => number | undefined;
export type CurrentOf = (componentId: string) => number | undefined;

const GROUND = "GND";

/** Voltage at a component pin (GND is 0 V by definition). */
function pinVoltage(component: Component, pin: string, v: VoltageOf): number | null {
  const net = component.pins[pin];
  if (net === undefined) return null;
  if (net.toUpperCase() === GROUND) return 0;
  return v(net) ?? null;
}

const diff = (a: number | null, b: number | null) => (a === null || b === null ? null : a - b);

/** True for parts with exactly two terminals (R, C, L, diodes, sources, lamp). */
export function isTwoPin(component: Component): boolean {
  return SYMBOLS[component.kind].pins.length === 2;
}

/** The two pins of a two-pin part in catalog order (pin 1/anode/+ first). */
export function twoPinNames(component: Component): [string, string] {
  const [a, b] = SYMBOLS[component.kind].pins;
  return [a!.name, b!.name];
}

export function meterReadings(component: Component, v: VoltageOf, i: CurrentOf): Reading[] {
  const symbol = SYMBOLS[component.kind];
  const pins = symbol.pins.filter((p) => component.pins[p.name] !== undefined);
  const pinRows: Reading[] = pins.map((p) => ({
    label: `V(${p.name})`,
    value: pinVoltage(component, p.name, v),
    unit: "V",
    hint: `Voltage at pin ${p.name} (net ${component.pins[p.name]}) relative to GND`,
  }));
  const at = (pin: string) => pinVoltage(component, pin, v);

  if (isTwoPin(component)) {
    const [p1, p2] = twoPinNames(component);
    const across = diff(at(p1), at(p2));
    const current = i(component.id) ?? null;
    const power = across !== null && current !== null ? across * current : null;
    const source = component.kind === "voltage_source" || component.kind === "current_source";
    return [
      ...pinRows,
      { label: "V across", value: across, unit: "V", hint: `V(${p1}) − V(${p2})`, emphasis: true },
      {
        label: "I through",
        value: current,
        unit: "A",
        hint: current === null ? "Current not recorded for this part" : `Current from ${p1} to ${p2} through the part`,
        emphasis: true,
      },
      {
        label: "P",
        value: power,
        unit: "W",
        hint: source ? "V × I; negative means the source is delivering power" : "V × I dissipated in the part",
        emphasis: true,
      },
    ];
  }

  switch (component.kind) {
    case "npn":
    case "pnp": {
      const vce = diff(at("collector"), at("emitter"));
      const ic = i(component.id) ?? null; // current trace flowing into the collector
      return [
        { label: "V_BE", value: diff(at("base"), at("emitter")), unit: "V", hint: "V(base) − V(emitter)", emphasis: true },
        { label: "V_CE", value: vce, unit: "V", hint: "V(collector) − V(emitter)", emphasis: true },
        { label: "I_C", value: ic, unit: "A", hint: ic === null ? "Collector current not recorded" : "Current into the collector", emphasis: true },
        { label: "P", value: vce !== null && ic !== null ? vce * ic : null, unit: "W", hint: "≈ V_CE × I_C (base power neglected)", emphasis: true },
        ...pinRows,
      ];
    }
    case "nmos":
    case "pmos": {
      const vds = diff(at("drain"), at("source"));
      const id = i(component.id) ?? null; // current trace flowing into the drain
      return [
        { label: "V_GS", value: diff(at("gate"), at("source")), unit: "V", hint: "V(gate) − V(source)", emphasis: true },
        { label: "V_DS", value: vds, unit: "V", hint: "V(drain) − V(source)", emphasis: true },
        { label: "I_D", value: id, unit: "A", hint: id === null ? "Drain current not recorded" : "Current into the drain", emphasis: true },
        { label: "P", value: vds !== null && id !== null ? vds * id : null, unit: "W", hint: "≈ V_DS × I_D", emphasis: true },
        ...pinRows,
      ];
    }
    case "opamp":
      return [
        { label: "V_in+ − V_in−", value: diff(at("in+"), at("in-")), unit: "V", hint: "Differential input voltage", emphasis: true },
        ...pinRows,
      ];
    default:
      return pinRows; // logic gates and anything else: pin voltages
  }
}
