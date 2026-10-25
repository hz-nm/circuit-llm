/**
 * Current through every drawn wire, for the animated current-flow overlay.
 *
 * Nets are drawn as stars (root pin → each other pin), so the current along the
 * wire ending at pin P is the current entering P's component from that net.
 * Pin currents come from component current traces (positive into the first
 * catalog pin; transistors: into collector/drain); the rest are filled in with
 * Kirchhoff's current law, per net and per component, when exactly one is unknown.
 */
import type { Circuit } from "../../api/types";
import { SYMBOLS } from "./symbols";

export const pinKey = (componentId: string, pin: string) => `${componentId}::${pin}`;

/** Pins whose current is (essentially) zero: high-impedance inputs. */
const ZERO_CURRENT_PINS: Record<string, readonly string[]> = {
  opamp: ["in+", "in-"],
  npn: ["base"],
  pnp: ["base"],
  nmos: ["gate"],
  pmos: ["gate"],
  not_gate: ["a"],
  schmitt_inverter: ["a"],
  and_gate: ["a", "b"],
  or_gate: ["a", "b"],
  nand_gate: ["a", "b"],
  nor_gate: ["a", "b"],
  xor_gate: ["a", "b"],
};

/** Transistors: the metered pin and its counterpart (base/gate is ~0). */
const TRANSISTOR_PINS: Record<string, readonly [string, string]> = {
  npn: ["collector", "emitter"],
  pnp: ["collector", "emitter"],
  nmos: ["drain", "source"],
  pmos: ["drain", "source"],
};

/**
 * Current INTO each connected pin (keyed by `pinKey`), where it can be determined.
 * `currentOf(id)` is the component's recorded current (into its first pin / collector / drain).
 */
export function pinCurrents(circuit: Circuit, currentOf: (componentId: string) => number | undefined): Map<string, number> {
  const known = new Map<string, number>();
  const set = (id: string, pin: string, value: number) => known.set(pinKey(id, pin), value);

  for (const c of circuit.components) {
    const connected = (pin: string) => c.pins[pin] !== undefined;
    for (const pin of ZERO_CURRENT_PINS[c.kind] ?? []) if (connected(pin)) set(c.id, pin, 0);
    const current = currentOf(c.id);
    if (current === undefined) continue;
    const transistor = TRANSISTOR_PINS[c.kind];
    const pins = SYMBOLS[c.kind].pins;
    const [main, other] = transistor ?? (pins.length === 2 ? [pins[0]!.name, pins[1]!.name] : [null, null]);
    if (main && other) {
      set(c.id, main, current);
      set(c.id, other, -current);
    }
  }

  // Kirchhoff: the currents into a net's pins, and into a component's pins, sum to zero.
  const groups: string[][] = [];
  const byNet = new Map<string, string[]>();
  for (const c of circuit.components) {
    const own: string[] = [];
    for (const [pin, net] of Object.entries(c.pins)) {
      const key = pinKey(c.id, pin);
      own.push(key);
      const list = byNet.get(net.toUpperCase()) ?? [];
      list.push(key);
      byNet.set(net.toUpperCase(), list);
    }
    groups.push(own);
  }
  // A net's pins draw current *out of* the net, so the same zero-sum rule applies to both.
  groups.push(...byNet.values());

  for (let changed = true, rounds = 0; changed && rounds < 50; rounds++) {
    changed = false;
    for (const group of groups) {
      const unknown = group.filter((k) => !known.has(k));
      if (unknown.length !== 1) continue;
      const sum = group.reduce((acc, k) => acc + (known.get(k) ?? 0), 0);
      known.set(unknown[0]!, -sum);
      changed = true;
    }
  }
  return known;
}

export type FlowMode = "off" | "conventional" | "electrons";

const MIN_CURRENT = 1e-6;

/**
 * Dot speed in px/s for a current along a wire (sign = direction along the path).
 * Logarithmic: 1 µA crawls, 1 A races; below 1 µA there are no dots (0).
 */
export function flowSpeed(current: number, mode: FlowMode): number {
  const magnitude = Math.abs(current);
  if (mode === "off" || !(magnitude >= MIN_CURRENT)) return 0;
  const level = Math.min(6, Math.max(0, Math.log10(magnitude / MIN_CURRENT)));
  const speed = 6 + 16 * level;
  const direction = Math.sign(current) * (mode === "electrons" ? -1 : 1);
  return speed * direction;
}
