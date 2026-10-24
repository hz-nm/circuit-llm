/**
 * Live simulation data shared by the schematic and the plots: which analysis
 * "drives" the schematic, per-net voltage arrays, a cursor store that moves at
 * animation-frame rate, interpolation and the voltage colour scale.
 */
import type { AnalysisResult, SimulationResult, SweepResult } from "../../api/types";

// ---------------------------------------------------------------------------- cursor store

export type CursorSource = "scrubber" | "player" | `plot:${string}`;
type Listener = (x: number | null, source: CursorSource) => void;

/**
 * Position along the driving analysis' x axis. Kept outside React state so the
 * player can update it every frame and only the subscribed views re-render.
 */
export class CursorStore {
  private x: number | null = null;
  private source: CursorSource = "scrubber";
  private readonly listeners = new Set<Listener>();

  get = (): number | null => this.x;
  lastSource = (): CursorSource => this.source;

  set(x: number | null, source: CursorSource): void {
    if (x === this.x) return;
    this.x = x;
    this.source = source;
    for (const listener of this.listeners) listener(x, source);
  }

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
}

// ---------------------------------------------------------------------------- driving analysis

/** Analyses that can animate the schematic: transient and DC sweeps (AC magnitudes are unsigned). */
export function isDrivable(a: AnalysisResult): a is SweepResult {
  return a.type === "tran" || a.type === "dc";
}

/** Default driver: the transient analysis, else a DC sweep, else none. */
export function defaultDriver(result: SimulationResult | null | undefined): number | null {
  const analyses = result?.ok ? (result.analyses ?? []) : [];
  const tran = analyses.findIndex((a) => a.type === "tran");
  if (tran >= 0) return tran;
  const dc = analyses.findIndex((a) => a.type === "dc");
  return dc >= 0 ? dc : null;
}

export const netKey = (net: string) => net.toUpperCase();

/** Node voltages ready for the schematic: static (op) or per-net arrays over x (sweep). */
/**
 * Live data for the schematic and multimeter: node voltages keyed by net and
 * currents keyed by component id (both upper-cased), static (op) or per sample.
 */
export type LiveVoltages =
  | { kind: "static"; values: Map<string, number>; currents: Map<string, number>; maxAbs: number }
  | {
      kind: "sweep";
      x: Float64Array;
      values: Map<string, Float64Array>;
      currents: Map<string, Float64Array>;
      maxAbs: number;
      sweep: SweepResult;
    };

export function buildLiveVoltages(result: SimulationResult | null | undefined, driver: number | null): LiveVoltages | null {
  if (!result?.ok) return null;
  const analyses = result.analyses ?? [];
  const sweep = driver !== null ? analyses[driver] : undefined;
  if (sweep && isDrivable(sweep)) {
    const values = new Map<string, Float64Array>();
    const currents = new Map<string, Float64Array>();
    let maxAbs = 0;
    for (const trace of sweep.traces) {
      if (trace.component && trace.unit === "A") currents.set(netKey(trace.component), Float64Array.from(trace.values));
      if (!trace.net || trace.unit !== "V") continue;
      const arr = Float64Array.from(trace.values);
      for (const v of arr) maxAbs = Math.max(maxAbs, Math.abs(v));
      values.set(netKey(trace.net), arr);
    }
    if (values.size > 0) return { kind: "sweep", x: Float64Array.from(sweep.x.values), values, currents, maxAbs, sweep };
  }
  const op = analyses.find((a) => a.type === "op");
  if (op && op.type === "op") {
    const values = new Map<string, number>();
    let maxAbs = 0;
    for (const [net, v] of Object.entries(op.node_voltages)) {
      values.set(netKey(net), v);
      maxAbs = Math.max(maxAbs, Math.abs(v));
    }
    const currents = new Map(Object.entries(op.branch_currents).map(([id, i]) => [netKey(id), i]));
    return { kind: "static", values, currents, maxAbs };
  }
  return null;
}

/** Linear interpolation of `ys` over ascending `xs` at `x` (clamped to the ends). */
export function sampleAt(xs: ArrayLike<number>, ys: ArrayLike<number>, x: number): number {
  const n = xs.length;
  if (n === 0) return 0;
  if (x <= xs[0]!) return ys[0]!;
  if (x >= xs[n - 1]!) return ys[n - 1]!;
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid]! <= x) lo = mid;
    else hi = mid;
  }
  const x0 = xs[lo]!;
  const x1 = xs[hi]!;
  const t = x1 === x0 ? 0 : (x - x0) / (x1 - x0);
  return ys[lo]! + (ys[hi]! - ys[lo]!) * t;
}

/** Currents of every metered component at the cursor position (or the static op values). */
export function currentsAt(live: LiveVoltages, x: number | null): Map<string, number> {
  if (live.kind === "static") return live.currents;
  const at = x ?? live.x[0] ?? 0;
  const out = new Map<string, number>();
  for (const [id, ys] of live.currents) out.set(id, sampleAt(live.x, ys, at));
  return out;
}

/** Voltages of every net at the cursor position (or the static op values). */
export function voltagesAt(live: LiveVoltages, x: number | null): Map<string, number> {
  if (live.kind === "static") return live.values;
  const at = x ?? live.x[0] ?? 0;
  const out = new Map<string, number>();
  for (const [net, ys] of live.values) out.set(net, sampleAt(live.x, ys, at));
  return out;
}

/** Label for the x axis position, e.g. "t = 1.25 ms" or "V1 = 2.5 V". */
export function cursorLabel(sweep: SweepResult, x: number, format: (v: number, unit: string) => string): string {
  const name = sweep.type === "tran" ? "t" : sweep.x.name;
  return `${name} = ${format(x, sweep.x.unit)}`;
}
