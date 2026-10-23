import { useMemo, useState } from "react";
import type { AnalysisResult, OperatingPointResult, SimulationResult, SweepResult } from "../../api/types";
import { formatSI } from "../../lib/si";
import { UPlotChart, type ChartSeries } from "./UPlotChart";

const TITLES: Record<AnalysisResult["type"], string> = {
  op: "Operating point",
  dc: "DC sweep",
  ac: "AC analysis (Bode plot)",
  tran: "Transient analysis",
};

export function SimulationResults({ result }: { result: SimulationResult }) {
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
          {analysis.type === "op" ? <OperatingPointTables result={analysis} /> : <SweepSection result={analysis} />}
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

function SweepSection({ result }: { result: SweepResult }) {
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [syncKey] = useState(() => `sweep-${++syncCounter}`);
  const traces = result.traces;
  const toggle = (name: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const xLabel = result.x.name;
  const logX = result.x.log_scale ?? result.type === "ac";

  // One chart per unit: a chart never has two y-scales.
  const groups = useMemo(() => {
    const byUnit = new Map<string, { name: string; values: number[]; phase: number[] | null; colorIndex: number }[]>();
    traces.forEach((t, i) => {
      const list = byUnit.get(t.unit) ?? [];
      list.push({ name: t.name, values: t.values, phase: t.phase_deg ?? null, colorIndex: i });
      byUnit.set(t.unit, list);
    });
    return [...byUnit.entries()];
  }, [traces]);

  const dbSeries = useMemo(
    () => traces.map((t) => ({ name: t.name, values: toDb(t.values) })),
    [traces],
  );

  if (traces.length === 0) return <p className="text-sm text-muted">No traces were recorded.</p>;

  const visible = (name: string) => !hidden.has(name);

  return (
    <div className="space-y-4">
      {traces.length > 1 && (
        <fieldset className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          <legend className="sr-only">Show traces</legend>
          {traces.map((t) => (
            <label key={t.name} className="flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" checked={visible(t.name)} onChange={() => toggle(t.name)} />
              <span className="font-mono">{t.name}</span>
            </label>
          ))}
        </fieldset>
      )}

      {result.type === "ac" ? (
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
            series={dbSeries.map((s, i): ChartSeries => ({ ...s, colorIndex: i, visible: visible(s.name) }))}
          />
          {traces.some((t) => t.phase_deg) && (
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
              series={traces.flatMap((t, i): ChartSeries[] =>
                t.phase_deg ? [{ name: t.name, values: t.phase_deg, colorIndex: i, visible: visible(t.name) }] : [],
              )}
            />
          )}
        </>
      ) : (
        groups.map(([unit, list]) => (
          <UPlotChart
            key={unit}
            title={unit === "V" ? "Voltages" : unit === "A" ? "Currents" : unit || "Values"}
            x={result.x.values}
            xLabel={xLabel}
            xUnit={result.x.unit}
            logX={logX}
            yLabel={unit === "V" ? "Voltage" : unit === "A" ? "Current" : "Value"}
            yUnit={unit}
            syncKey={syncKey}
            height={groups.length > 1 ? 200 : 260}
            series={list.map((s) => ({ name: s.name, values: s.values, colorIndex: s.colorIndex, visible: visible(s.name) }))}
          />
        ))
      )}
    </div>
  );
}
