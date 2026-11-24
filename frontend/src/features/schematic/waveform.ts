/**
 * Names for source waveforms. The backend stores square, PWM, triangle and
 * sawtooth signals as pulses (triangles and sawtooths are pulses with long
 * edges), so the shape a user asked for is recovered from the timings here.
 */
import type { Component } from "../../api/types";

type Waveform = NonNullable<Component["waveform"]>;
type Pulse = Extract<Waveform, { shape: "pulse" }>;

export type WaveKind = "sine" | "square" | "pulse" | "triangle" | "sawtooth" | "pwl";

/** Fraction of the period spent high (edges count half). */
export const dutyOf = (p: Pulse) => (p.width + (p.rise + p.fall) / 2) / p.period;

export function waveKind(waveform: Waveform): WaveKind {
  if (waveform.shape !== "pulse") return waveform.shape;
  const { rise, fall } = waveform;
  if (rise + fall > 0.9 * waveform.period) return Math.abs(rise - fall) < 0.1 * waveform.period ? "triangle" : "sawtooth";
  return Math.abs(dutyOf(waveform) - 0.5) < 0.02 ? "square" : "pulse";
}
