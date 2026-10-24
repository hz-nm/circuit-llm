import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { Circuit } from "../../api/types";
import { formatSI } from "../../lib/si";
import { useIsDark } from "../../ui/theme";
import { cursorLabel, isDrivable, netKey, scaleStops, type LiveVoltages } from "../simulation/live";
import type { SimulationSession } from "../simulation/session";

const SWEEP_MS = 4000;

/** Legend for the diverging wire colours: −max … 0 V … +max. */
function VoltageLegend({ maxAbs }: { maxAbs: number }) {
  const dark = useIsDark();
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted" aria-label={`Wire colour: blue negative, grey 0 V, red positive, up to ${formatSI(maxAbs, "V")}`}>
      <span className="tabular-nums">{formatSI(-maxAbs, "V", 2)}</span>
      <span aria-hidden="true" className="h-2 w-24 rounded-full" style={{ background: scaleStops(dark) }} />
      <span className="tabular-nums">+{formatSI(maxAbs, "V", 2)}</span>
    </div>
  );
}

/** Slider + play/pause over the driving sweep's x axis; the player loops in ~4 s. */
function Scrubber({ live, session }: { live: Extract<LiveVoltages, { kind: "sweep" }>; session: SimulationSession }) {
  const { cursor } = session;
  const x = useSyncExternalStore(cursor.subscribe, cursor.get);
  const [playing, setPlaying] = useState(false);
  const x0 = live.x[0] ?? 0;
  const x1 = live.x[live.x.length - 1] ?? 1;
  const span = x1 - x0 || 1;
  const frame = useRef(0);

  useEffect(() => {
    if (!playing) return;
    // Continue from the current position.
    const startFrac = ((cursor.get() ?? x0) - x0) / span;
    const t0 = performance.now() - (startFrac >= 0.999 ? 0 : startFrac) * SWEEP_MS;
    const tick = (now: number) => {
      const frac = ((now - t0) % SWEEP_MS) / SWEEP_MS;
      cursor.set(x0 + frac * span, "player");
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    // Any other cursor source (the slider, hovering a plot) pauses the player.
    const unsubscribe = cursor.subscribe((_x, source) => {
      if (source !== "player") setPlaying(false);
    });
    return () => {
      cancelAnimationFrame(frame.current);
      unsubscribe();
    };
  }, [playing, cursor, x0, span]);

  const value = x ?? x0;
  const label = cursorLabel(live.sweep, value, (v, unit) => formatSI(v, unit, 4));

  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <button
        type="button"
        onClick={() => setPlaying((p) => !p)}
        aria-label={playing ? "Pause sweep animation" : "Play sweep animation"}
        title={playing ? "Pause" : "Play (sweeps the whole range in 4 s, looping)"}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-xs text-accent-ink hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent"
      >
        {playing ? "❚❚" : "▶"}
      </button>
      <input
        type="range"
        min={x0}
        max={x1}
        step={span / 1000}
        value={value}
        onChange={(e) => cursor.set(Number(e.target.value), "scrubber")}
        aria-label="Sweep position"
        aria-valuetext={label}
        className="min-w-24 flex-1 accent-[var(--c-accent)]"
      />
      <span className="w-28 shrink-0 font-mono text-xs tabular-nums">{label}</span>
    </div>
  );
}

/** Keyboard-accessible probe list: one toggle per non-ground net, with its live voltage. */
function NetList({ circuit, session, voltages }: { circuit: Circuit; session: SimulationSession; voltages: ReadonlyMap<string, number> | null }) {
  const nets = [...new Set(circuit.components.flatMap((c) => Object.values(c.pins)))].filter((n) => netKey(n) !== "GND").sort();
  const { probes } = session;
  return (
    <div role="group" aria-label="Probe nets" className="flex flex-wrap gap-1">
      {nets.map((net) => {
        const on = probes.isProbed(net);
        const v = voltages?.get(netKey(net));
        return (
          <button
            key={net}
            type="button"
            aria-pressed={on}
            onClick={() => probes.toggle(net)}
            title={on ? `Remove probe from ${net}` : `Probe ${net}`}
            className={`rounded-full border px-2 py-0.5 font-mono text-[11px] focus-visible:outline-2 focus-visible:outline-accent ${
              on ? "border-accent bg-accent-soft text-ink" : "border-line text-muted hover:text-ink"
            }`}
          >
            {on ? "◉ " : "○ "}
            {net}
            {v !== undefined && <span className="ml-1 tabular-nums opacity-80">{formatSI(v, "V", 3)}</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Panel under the schematic: colour legend, sweep scrubber, analysis picker and probe list. */
export function LiveDock({
  circuit,
  session,
  voltages,
  enabled,
}: {
  circuit: Circuit;
  session: SimulationSession;
  voltages: ReadonlyMap<string, number> | null;
  enabled: boolean;
}) {
  const { live, result, driver, setDriver } = session;
  const sweeps = (result?.ok ? (result.analyses ?? []) : []).flatMap((a, i) => (isDrivable(a) ? [{ a, i }] : []));
  const [showNets, setShowNets] = useState(false);

  return (
    <div className="border-t border-line bg-panel px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {enabled && live?.kind === "sweep" && <Scrubber live={live} session={session} />}
        {enabled && live?.kind === "static" && <span className="text-xs text-muted">Operating point</span>}
        {!live && <span className="text-xs text-muted">{result === null ? "Not simulated yet: press ▶ Run" : "No node voltages in this result"}</span>}
        {sweeps.length > 1 && (
          <label className="flex items-center gap-1.5 text-xs text-muted">
            Drive with
            <select
              value={driver ?? ""}
              onChange={(e) => setDriver(Number(e.target.value))}
              className="rounded-md border border-line bg-bg px-1.5 py-0.5 text-xs text-ink"
            >
              {sweeps.map(({ a, i }) => (
                <option key={i} value={i}>
                  {a.type === "tran" ? "Transient" : `DC sweep (${a.x.name})`}
                </option>
              ))}
            </select>
          </label>
        )}
        {enabled && live && live.maxAbs > 0 && <VoltageLegend maxAbs={live.maxAbs} />}
        <button
          type="button"
          aria-expanded={showNets}
          onClick={() => setShowNets((s) => !s)}
          className="ml-auto rounded-md px-2 py-0.5 text-xs text-muted hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
        >
          Probes ({session.probes.nets.size}) {showNets ? "▴" : "▾"}
        </button>
      </div>
      {showNets && (
        <div className="mt-2">
          <NetList circuit={circuit} session={session} voltages={enabled ? voltages : null} />
          <p className="mt-1 text-[11px] text-muted">Click a wire or a net here to toggle its probe; probed nets appear in the Simulation plots.</p>
        </div>
      )}
    </div>
  );
}
