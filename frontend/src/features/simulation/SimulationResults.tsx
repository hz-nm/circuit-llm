import { useMemo, useState } from "react";
import type { AnalysisResult, Circuit, OperatingPointResult, SimulationResult, SweepResult, Trace } from "../../api/types";
import { isTwoPin, twoPinNames } from "../multimeter/readings";
import { netKey } from "./live";
import { formatSI } from "../../lib/si";
import type { CursorStore } from "./live";
import { UPlotChart, type ChartSeries } from "./UPlotChart";

/** How the plots interact with the rest of the app (probes and the shared cursor); optional. */
export interface PlotLinks {
  showsTrace: (trace: Trace) => boolean;
  toggleNet: (net: string) => void;
  cursor: CursorStore;
  /** Index of the analysis the shared cursor belongs to. */
  driver: number | null;
  /** Components added from the multimeter (upper-cased ids) and the circuit they belong to. */
  components: ReadonlySet<string>;
  togglePlot: (componentId: string) => void;
  circuit: Circuit;
}

/**
 * V-across traces for components plotted from the multimeter, computed from
 * the two pin-net traces (GND = 0 V). Returns trace -> component id.
 */
function acrossTraces(result: SweepResult, links: PlotLinks | undefined): Map<Trace, string> {
  const out = new Map<Trace, string>();
  if (!links || result.type === "ac") return out;
  const byNet = new Map(result.traces.filter((t) => t.net && t.unit === "V").map((t) => [netKey(t.net!), t.values]));
  const zeros = result.x.values.map(() => 0);
  const netValues = (net: string | undefined) => (net === undefined ? undefined : netKey(net) === "GND" ? zeros : byNet.get(netKey(net)));
  for (const component of links.circuit.components) {
    if (!links.components.has(netKey(component.id)) || !isTwoPin(component)) continue;
    const [p1, p2] = twoPinNames(component);
    const a = netValues(component.pins[p1]);
    const b = netValues(component.pins[p2]);
    if (!a || !b) continue;
    const trace: Trace = { name: `V(${component.id})`, unit: "V", values: a.map((v, k) => v - (b[k] ?? 0)), probed: true, net: null };
    out.set(trace, component.id);
  }
  return out;
}

const TITLES: Record<AnalysisResult["type"], string> = {
  op: "Operating point",
  dc: "DC sweep",
  ac: "AC analysis (Bode plot)",
  tran: "Transient analysis",
};

export function SimulationResults({ result, links }: { result: SimulationResult; links?: PlotLinks }) {
  const analyses = result.analyses ?? [];
  return (
    <>
      {!result.ok && (
        <section role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-3 text-sm">
          <p className="font-semibold text-danger">Simulation failed</p>
          {result.error && <p className="mt-1">{result.error}</p>}
          {result.log && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-muted">Simulator log</summary>
              <pre className="mt-1 max-h-72 overflow-auto rounded border border-line bg-panel p-2 font-mono text-xs">{result.log}</pre>
            </details>
          )}
        </section>
      )}
      {analyses.map((analysis, i) => (
        <section key={i} className="rounded-lg border border-line bg-panel p-3">
          <h3 className="mb-2 text-sm font-semibold">{TITLES[analysis.type]}</h3>
          {analysis.type === "op" ? <OperatingPointTables result={analysis} /> : <SweepSection result={analysis} links={links} cursor={links && links.driver === i ? links.cursor : undefined} />}
        </section>
      ))}
      <details>
        <summary className="cursor-pointer text-xs text-muted">SPICE netlist</summary>
        <pre className="mt-1 overflow-auto rounded-lg border border-line bg-sunken p-3 font-mono text-xs">{result.netlist}</pre>
      </details>
    </>
  );
}

// ---------------------------------------------------------------------------- op

function ValueTable({ caption, rows, unit, keyLabel }: { caption: string; rows: [string, number][]; unit: string; keyLabel: string }) {
  return (
    <table className="w-full text-sm">
      <caption className="mb-1 text-left text-xs font-medium text-muted">{caption}</caption>
      <thead>
        <tr className="border-b border-line text-left text-xs text-muted">
          <th scope="col" className="py-1 font-medium">{keyLabel}</th>
          <th scope="col" className="py-1 text-right font-medium">Value</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([name, value]) => (
          <tr key={name} className="border-b border-line/60 last:border-0">
            <th scope="row" className="py-1 text-left font-mono font-normal">{name}</th>
            <td className="py-1 text-right tabular-nums">{formatSI(value, unit, 4)}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={2} className="py-1 text-xs text-muted">None</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function OperatingPointTables({ result }: { result: OperatingPointResult }) {
  const byName = (a: [string, number], b: [string, number]) => a[0].localeCompare(b[0], undefined, { numeric: true });
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <ValueTable caption="Node voltages (relative to GND)" keyLabel="Net" unit="V" rows={Object.entries(result.node_voltages).sort(byName)} />
      <ValueTable caption="Branch currents" keyLabel="Component" unit="A" rows={Object.entries(result.branch_currents).sort(byName)} />
    </div>
  );
}

// ---------------------------------------------------------------------------- sweeps

/** Magnitude in dB from linear magnitude (floored so zeros don't become -Infinity). */
export function toDb(values: readonly number[]): number[] {
  return values.map((v) => 20 * Math.log10(Math.max(Math.abs(v), 1e-15)));
}

let syncCounter = 0;

/** Chart names for sensor environment units. */
const ENV_NAMES: Record<string, string> = { lux: "Light", "°C": "Temperature", ppm: "Gas", "": "Environment" };

const probedByDefault = (t: Trace) => t.probed !== false;

interface Indexed {
  trace: Trace;
  /** Position in the analysis: fixes the trace colour, so probing others never repaints it. */
  index: number;
}

function SweepSection({ result, links, cursor }: { result: SweepResult; links: PlotLinks | undefined; cursor: CursorStore | undefined }) {
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [syncKey] = useState(() => `sweep-${++syncCounter}`);
  const shows = links?.showsTrace ?? probedByDefault;

  // Plotted: traces marked probed (by the backend or the user's probes), minus user un-probes,
  // plus V-across traces of components plotted from the multimeter.
  const synthetic = useMemo(() => acrossTraces(result, links), [result, links]);
  const shown: Indexed[] = useMemo(() => {
    const real = result.traces.map((trace, index) => ({ trace, index })).filter(({ trace }) => shows(trace));
    // Synthetic traces take the first palette slot no shown trace uses (slots wrap at 8).
    const used = new Set(real.map(({ index }) => index % 8));
    const extra = [...synthetic.keys()].map((trace, k) => {
      const slot = [0, 1, 2, 3, 4, 5, 6, 7].find((c) => !used.has(c));
      if (slot !== undefined) used.add(slot);
      return { trace, index: slot ?? result.traces.length + k };
    });
    return [...real, ...extra];
  }, [result.traces, synthetic, shows]);
  const extraNets = result.traces.filter((t) => t.net && !shows(t)).length;

  // Unchecking a net trace un-probes it (also on the schematic); current traces are only hidden.
  const toggle = (trace: Trace) => {
    if (trace.net && links) {
      links.toggleNet(trace.net);
      return;
    }
    // A component added from the multimeter is removed as a whole (V across and current).
    const fromMeter = synthetic.get(trace) ?? (trace.component && links?.components.has(netKey(trace.component)) ? trace.component : null);
    if (fromMeter && links) {
      links.togglePlot(fromMeter);
      return;
    }
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(trace.name)) next.delete(trace.name);
      else next.add(trace.name);
      return next;
    });
  };
  const visible = (t: Trace) => !hidden.has(t.name);

  // One chart per unit: a chart never has two y-scales.
  // Sensor environment traces (lux, °C, ...) get their own small charts above the electrical ones,
  // so 1000 lux never flattens the volts.
  const groups = useMemo(() => {
    const byUnit = new Map<string, Indexed[]>();
    for (const item of shown) {
      const key = item.trace.stimulus_of ? `env:${item.trace.unit}` : item.trace.unit;
      const list = byUnit.get(key) ?? [];
      list.push(item);
      byUnit.set(key, list);
    }
    return [...byUnit.entries()].sort(([a], [b]) => Number(b.startsWith("env:")) - Number(a.startsWith("env:")));
  }, [shown]);

  const series = (items: Indexed[], values: (t: Trace) => number[]): ChartSeries[] =>
    items.map(({ trace, index }) => ({ name: trace.name, values: values(trace), colorIndex: index, visible: visible(trace) }));

  const dbCache = useMemo(() => new Map(result.traces.map((t) => [t.name, toDb(t.values)])), [result.traces]);
  const logX = result.x.log_scale ?? result.type === "ac";

  return (
    <div className="space-y-4">
      <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <legend className="sr-only">Plotted traces</legend>
        {shown.map(({ trace }) => (
          <label key={trace.name} className="flex cursor-pointer items-center gap-1.5">
            <input type="checkbox" checked={visible(trace)} onChange={() => toggle(trace)} />
            <span className="font-mono">{trace.name}</span>
          </label>
        ))}
        {shown.length === 0 && <span className="text-muted">No traces probed.</span>}
        {extraNets > 0 && links && (
          <span className="text-muted">+{extraNets} more net{extraNets === 1 ? "" : "s"} recorded: click a wire on the Schematic to probe it.</span>
        )}
      </fieldset>

      {shown.length > 0 &&
        (result.type === "ac" ? (
          <>
            <UPlotChart
              title="Magnitude"
              x={result.x.values}
              xLabel="Frequency"
              xUnit={result.x.unit}
              logX
              yLabel="Magnitude"
              yUnit="dB"
              plainY
              syncKey={syncKey}
              series={series(shown, (t) => dbCache.get(t.name) ?? toDb(t.values))}
            />
            {shown.some(({ trace }) => trace.phase_deg) && (
              <UPlotChart
                title="Phase"
                x={result.x.values}
                xLabel="Frequency"
                xUnit={result.x.unit}
                logX
                yLabel="Phase"
                yUnit="°"
                plainY
                syncKey={syncKey}
                height={180}
                series={series(
                  shown.filter(({ trace }) => trace.phase_deg),
                  (t) => t.phase_deg ?? [],
                )}
              />
            )}
          </>
        ) : (
          groups.map(([key, items]) => {
            const env = key.startsWith("env:");
            const unit = env ? key.slice(4) : key;
            const name = env ? (ENV_NAMES[unit] ?? "Environment") : unit === "V" ? "Voltage" : unit === "A" ? "Current" : "Value";
            return (
              <UPlotChart
                key={key}
                title={env ? `Environment: ${name.toLowerCase()}` : unit === "V" ? "Voltages" : unit === "A" ? "Currents" : unit || "Values"}
                x={result.x.values}
                xLabel={result.type === "tran" ? "t" : result.x.name}
                xUnit={result.x.unit}
                logX={logX}
                yLabel={name}
                yUnit={unit}
                plainY={env}
                syncKey={syncKey}
                cursor={cursor}
                height={env ? 140 : groups.length > 1 ? 200 : 260}
                series={series(items, (t) => t.values)}
              />
            );
          })
        ))}
    </div>
  );
}
