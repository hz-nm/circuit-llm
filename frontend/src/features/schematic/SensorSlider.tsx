import { useEffect, useRef, useSyncExternalStore, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { Component } from "../../api/types";
import { formatReadout } from "../../lib/si";
import { currentsAt, netKey, outputsAt, voltagesAt } from "../simulation/live";
import { exploreRange, type SimulationSession } from "../simulation/session";
import { formatStimulus, isBinary, STIMULUS, type StimulusSpec } from "./stimulus";

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
  out?: (id: string) => number | undefined,
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
  if (component.kind === "dc_motor") {
    const rpm = out?.(component.id);
    const across = (pinV("+") ?? Number.NaN) - (pinV("-") ?? Number.NaN);
    const speed = rpm === undefined ? "–" : `${Math.round(rpm)}`.padStart(6, " ");
    return `${head} ${speed} rpm · ${fmt(i(component.id), "A")} · ${fmt(across, "V")}`;
  }
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
  if (isBinary(spec)) return <SensorButton session={session} component={component} spec={spec} compact={compact} />;
  return <StimulusSlider session={session} component={component} spec={spec} compact={compact} />;
}

interface ControlProps {
  session: SimulationSession;
  component: Component;
  spec: StimulusSpec;
  compact: boolean;
}

/** The sensor's readout at the current setting (explore sweep at the cursor), or null. */
function useReadout(session: SimulationSession, component: Component, spec: StimulusSpec, value: number | null): string | null {
  const { cursor, live } = session;
  const x = useSyncExternalStore(cursor.subscribe, cursor.get);
  if (value === null || !live || x === null) return null;
  const volts = voltagesAt(live, x);
  const amps = currentsAt(live, x);
  const outs = outputsAt(live, x);
  return sensorReadout(component, spec, value, (net) => volts.get(netKey(net)), (id) => amps.get(netKey(id)), (id) => outs.get(netKey(id)));
}

/**
 * Button for binary stimuli (switches, PIR motion). Push buttons are momentary
 * (pressed while held: pointer or Space/Enter); toggle, reed and limit switches
 * and the PIR flip on click. Pressing selects the up sweep at 1, releasing the
 * down sweep at 0, through the same explore machinery as the sliders.
 */
function SensorButton({ session, component, spec, compact }: ControlProps) {
  const active = session.explore?.sensorId === component.id ? session.explore : null;
  const momentary = component.kind === "switch" && (component.model ?? "push_button").toLowerCase().startsWith("push_button");
  const constant = typeof component.stimulus === "number" ? component.stimulus : 0;
  const pressed = (active ? active.value : constant) >= 0.5;
  const sweeping = session.exploreStatus?.sensorId === component.id && session.exploreStatus.kind === "sweeping";
  const error = session.exploreStatus?.sensorId === component.id && session.exploreStatus.kind === "error" ? session.exploreStatus.message : null;

  // A press before the explore sweep has loaded is applied as soon as it arrives.
  const pending = useRef<number | null>(null);
  const { setExploreValue, startExplore } = session;
  useEffect(() => {
    if (active && pending.current !== null) {
      setExploreValue(pending.current);
      pending.current = null;
    }
  }, [active, setExploreValue]);

  const set = (value: number) => {
    if (active) setExploreValue(value);
    else {
      pending.current = value;
      if (!sweeping) startExplore(component.id);
    }
  };
  const isKey = (e: KeyboardEvent) => e.key === " " || e.key === "Enter";
  const handlers = momentary
    ? {
        onPointerDown: (e: ReactPointerEvent<HTMLButtonElement>) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          set(1);
        },
        onPointerUp: () => set(0),
        onPointerCancel: () => set(0),
        onKeyDown: (e: KeyboardEvent) => {
          if (!isKey(e)) return;
          e.preventDefault();
          if (!e.repeat) set(1);
        },
        onKeyUp: (e: KeyboardEvent) => {
          if (!isKey(e)) return;
          e.preventDefault();
          set(0);
        },
      }
    : { onClick: () => set(pressed ? 0 : 1) };

  const label = spec.quantity === "motion" ? (pressed ? "motion" : "no motion") : momentary ? (pressed ? "pressed" : "press") : pressed ? "on" : "off";
  const readout = useReadout(session, component, spec, active ? active.value : null);

  return (
    <span className={`flex items-center gap-1.5 ${compact ? "" : "flex-wrap"}`}>
      {!compact && <span className="font-mono text-xs font-semibold">{component.id}</span>}
      <button
        type="button"
        aria-pressed={pressed}
        title={momentary ? `Hold to press ${component.id}` : `Click to flip ${component.id}`}
        className={`select-none rounded-md border px-2 py-0.5 text-[11px] font-medium focus-visible:outline-2 focus-visible:outline-accent ${
          pressed ? "border-accent bg-accent text-accent-ink" : "border-line bg-panel text-ink hover:bg-sunken"
        }`}
        {...handlers}
      >
        {momentary ? "⏺ " : spec.quantity === "motion" ? "◎ " : "⏻ "}
        {label}
      </button>
      {sweeping && <span className="text-[11px] text-muted">Sweeping…</span>}
      {error && <span className="text-[11px] text-danger">{error}</span>}
      {!compact && readout && <span className="whitespace-pre font-mono text-xs tabular-nums">{readout}</span>}
    </span>
  );
}

/** Slider for continuous stimuli (light, temperature, gas, position, motor load). */
function StimulusSlider({ session, component, spec, compact }: ControlProps) {
  const { explore, exploreStatus } = session;
  const active = explore?.sensorId === component.id ? explore : null;

  const range = active ? exploreRange(active.data) : null;
  const log = active?.data.log_scale ?? false;
  const position = active && range ? toPosition(active.value, range.min, range.max, log) : STEPS / 2;
  const sweeping = exploreStatus?.sensorId === component.id && exploreStatus.kind === "sweeping";
  const error = exploreStatus?.sensorId === component.id && exploreStatus.kind === "error" ? exploreStatus.message : null;

  const grab = () => {
    if (!active && !sweeping) session.startExplore(component.id);
  };

  const readout = useReadout(session, component, spec, active ? active.value : null);

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
