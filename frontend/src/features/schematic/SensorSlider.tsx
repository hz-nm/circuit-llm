import { useSyncExternalStore } from "react";
import type { Component } from "../../api/types";
import { formatReadout } from "../../lib/si";
import { currentsAt, netKey, voltagesAt } from "../simulation/live";
import { exploreRange, type SimulationSession } from "../simulation/session";
import { formatStimulus, STIMULUS, type StimulusSpec } from "./stimulus";

const STEPS = 1000;
const RESISTIVE = new Set(["ldr", "thermistor", "gas_sensor"]);

/** Slider position (0..STEPS) ↔ stimulus value, logarithmic when the sweep is. */
function toValue(t: number, min: number, max: number, log: boolean): number {
  const f = t / STEPS;
  return log ? 10 ** (Math.log10(min) + f * (Math.log10(max) - Math.log10(min))) : min + f * (max - min);
}
function toPosition(value: number, min: number, max: number, log: boolean): number {
  const f = log ? (Math.log10(value) - Math.log10(min)) / (Math.log10(max) - Math.log10(min)) : (value - min) / (max - min || 1);
  return Math.round(Math.min(1, Math.max(0, f)) * STEPS);
}

/**
 * What the sensor does at this setting, in the fixed-width readout format, e.g.
 * "☀    120 lx → 2.60 kΩ · SENSE  3.90  V ·  900 µA".
 */
export function sensorReadout(
  component: Component,
  spec: StimulusSpec,
  stimulus: number,
  v: (net: string) => number | undefined,
  i: (id: string) => number | undefined,
): string {
  const pinV = (pin: string) => {
    const net = component.pins[pin];
    return net === undefined ? undefined : net.toUpperCase() === "GND" ? 0 : v(net);
  };
  const fmt = (value: number | undefined, unit: string) => formatReadout(value ?? Number.NaN, unit);
  if (component.kind === "potentiometer") {
    return `${spec.icon} ${(stimulus * 100).toFixed(0).padStart(3, " ")} % → w ${fmt(pinV("w"), "V")}`;
  }
  const head = `${spec.icon} ${formatStimulus(stimulus, spec)} →`;
  if (component.kind === "pir") return `${head} out ${fmt(pinV("out"), "V")}`;
  const current = i(component.id);
  if (!RESISTIVE.has(component.kind)) return `${head} ${fmt(current, "A")}`;
  const v1 = pinV("1");
  const v2 = pinV("2");
  const r = v1 !== undefined && v2 !== undefined && current !== undefined && Math.abs(current) > 1e-15 ? (v1 - v2) / current : undefined;
  // The "sense" side: the net on pin 2, unless that's ground.
  const sidePin = component.pins["2"]?.toUpperCase() === "GND" ? "1" : "2";
  const sideNet = component.pins[sidePin] ?? "";
  return `${head} ${fmt(r, "Ω")} · ${sideNet} ${fmt(pinV(sidePin), "V")} · ${fmt(current, "A")}`;
}

/**
 * A sensor's stimulus slider. Grabbing it the first time runs the explore sweep;
 * then dragging shows the circuit's steady state at that value.
 */
export function SensorSlider({ session, component, compact = false }: { session: SimulationSession; component: Component; compact?: boolean }) {
  const spec = STIMULUS[component.kind]!;
  const { explore, exploreStatus, cursor, live } = session;
  const active = explore?.sensorId === component.id ? explore : null;
  const x = useSyncExternalStore(cursor.subscribe, cursor.get);

  const range = active ? exploreRange(active.data) : null;
  const log = active?.data.log_scale ?? false;
  const position = active && range ? toPosition(active.value, range.min, range.max, log) : STEPS / 2;
  const sweeping = exploreStatus?.sensorId === component.id && exploreStatus.kind === "sweeping";
  const error = exploreStatus?.sensorId === component.id && exploreStatus.kind === "error" ? exploreStatus.message : null;

  const grab = () => {
    if (!active && !sweeping) session.startExplore(component.id);
  };

  let readout: string | null = null;
  if (active && live && x !== null) {
    const volts = voltagesAt(live, x);
    const amps = currentsAt(live, x);
    readout = sensorReadout(component, spec, active.value, (net) => volts.get(netKey(net)), (id) => amps.get(netKey(id)));
  }

  return (
    <span className={`flex items-center gap-1.5 ${compact ? "" : "flex-wrap"}`}>
      {!compact && <span className="font-mono text-xs font-semibold">{component.id}</span>}
      <input
        type="range"
        min={0}
        max={STEPS}
        step={1}
        value={position}
        onPointerDown={grab}
        onKeyDown={grab}
        onChange={(e) => {
          if (active && range) session.setExploreValue(toValue(Number(e.target.value), range.min, range.max, log));
        }}
        aria-label={`${component.id} ${spec.quantity}${active ? "" : " (grab to explore)"}`}
        aria-valuetext={active ? formatStimulus(active.value, spec).trim() : undefined}
        title={active ? `Drag to set the ${spec.quantity}` : `Grab to explore ${component.id}: sweeps its ${spec.quantity} and shows the steady state`}
        className={`${compact ? "w-20" : "w-40"} accent-[var(--c-accent)] ${active ? "" : "opacity-70"}`}
      />
      {sweeping && <span className="text-[11px] text-muted">Sweeping…</span>}
      {error && <span className="text-[11px] text-danger">{error}</span>}
      {active && compact && (
        <span className="whitespace-pre rounded bg-panel/90 px-1 font-mono text-[10px] tabular-nums">{formatStimulus(active.value, spec)}</span>
      )}
      {!compact && readout && <span className="whitespace-pre font-mono text-xs tabular-nums">{readout}</span>}
    </span>
  );
}
