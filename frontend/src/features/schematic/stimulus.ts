/**
 * What environment each sensor kind responds to. The catalog endpoint doesn't
 * expose this, so it is mirrored here (backend: the "sensors" family).
 */
import type { Component, ComponentKind } from "../../api/types";

export interface StimulusSpec {
  quantity: "light" | "temperature" | "gas" | "motion" | "position";
  /** Unit as written in the circuit and in `stimulus_of` traces ("" for 0/1 and 0..1 quantities). */
  unit: string;
  icon: string;
}

export const STIMULUS: Partial<Record<ComponentKind, StimulusSpec>> = {
  ldr: { quantity: "light", unit: "lux", icon: "☀" },
  photodiode: { quantity: "light", unit: "lux", icon: "☀" },
  phototransistor: { quantity: "light", unit: "lux", icon: "☀" },
  thermistor: { quantity: "temperature", unit: "°C", icon: "🌡" },
  gas_sensor: { quantity: "gas", unit: "ppm", icon: "≋" },
  pir: { quantity: "motion", unit: "", icon: "◎" },
  potentiometer: { quantity: "position", unit: "", icon: "⟲" },
};

/** Plain, compact number for labels: 1000, 0.5, 43.2 (no SI prefixes on environment units). */
const num = (v: number) => String(Number(v.toPrecision(3)));
const withUnit = (v: number, unit: string) => (unit ? `${num(v)} ${unit}` : num(v));

/** Label text for a component's stimulus, e.g. "light 500 lux" or "light pwl 1000 → 0.5 lux". */
export function stimulusText(component: Component): string | null {
  const spec = STIMULUS[component.kind];
  const stimulus = component.stimulus;
  if (!spec || stimulus === undefined || stimulus === null) return null;
  const unit = spec.unit ? ` ${spec.unit}` : "";
  if (typeof stimulus === "number") return `${spec.quantity} ${withUnit(stimulus, spec.unit)}`;
  switch (stimulus.shape) {
    case "sine":
      return `${spec.quantity} sine ${num(stimulus.offset)} ± ${num(stimulus.amplitude)}${unit} @ ${num(stimulus.frequency)} Hz`;
    case "pulse":
      return `${spec.quantity} pulse ${num(stimulus.initial)} → ${num(stimulus.pulsed)}${unit}`;
    case "pwl": {
      // Distinct consecutive values only: [1000, 0.5, 0.5, 1000] reads "1000 → 0.5 → 1000".
      const values = stimulus.points.map(([, v]) => v).filter((v, i, all) => i === 0 || v !== all[i - 1]);
      const shown = values.slice(0, 4).map(num).join(" → ");
      return `${spec.quantity} pwl ${shown}${values.length > 4 ? " …" : ""}${unit}`;
    }
  }
}

const FIGURE_SPACE = "\u2007";

/** Plain number padded to 7 characters: 2 decimals below 10, 1 below 100, none above (up to 9999999). */
function plainFixed(value: number): string {
  const magnitude = Math.abs(value);
  const text = value.toFixed(magnitude < 9.995 ? 2 : magnitude < 99.95 ? 1 : 0);
  return text.padStart(7, FIGURE_SPACE);
}

/**
 * Fixed-width environment readout (never changes length while animating):
 * light/gas use plain numbers with decimals by range ("0.50 lx", "50.5 lx",
 * "1000 lx"), temperature one decimal, position two decimals, motion a word.
 */
export function formatStimulus(value: number, spec: StimulusSpec): string {
  switch (spec.quantity) {
    case "light":
      return `${plainFixed(value)} lx`;
    case "gas":
      return `${plainFixed(value)} ppm`;
    case "temperature":
      return `${value.toFixed(1).padStart(6, FIGURE_SPACE)} °C`;
    case "position":
      return value.toFixed(2).padStart(5, FIGURE_SPACE);
    case "motion":
      return value >= 0.5 ? "motion" : "idle  ";
  }
}
