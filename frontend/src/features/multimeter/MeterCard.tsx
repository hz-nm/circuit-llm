import type { Component } from "../../api/types";
import { formatReadout } from "../../lib/si";
import { componentSummary } from "../schematic/componentText";
import { SYMBOLS } from "../schematic/symbols";
import { netKey } from "../simulation/live";
import { isTwoPin, meterReadings } from "./readings";

interface Props {
  component: Component;
  voltages: ReadonlyMap<string, number> | null;
  currents: ReadonlyMap<string, number> | null;
  pinned: boolean;
  onUnpin?: () => void;
  /** Present when the part can be plotted (two-pin parts with a result). */
  plotted?: boolean;
  onTogglePlot?: () => void;
}

/**
 * Compact multimeter card. All values use the fixed-width readout format in a
 * monospace font and the card has a fixed width, so nothing moves while the
 * timeline plays.
 */
export function MeterCard({ component, voltages, currents, pinned, onUnpin, plotted, onTogglePlot }: Props) {
  const rows = meterReadings(
    component,
    (net) => voltages?.get(netKey(net)),
    (id) => currents?.get(netKey(id)),
  );
  const summary = componentSummary(component);
  const noData = voltages === null;

  return (
    <div
      className={`w-60 rounded-lg border bg-panel/95 p-2 text-xs shadow-lg backdrop-blur ${pinned ? "border-accent" : "border-line"}`}
      role={pinned ? "region" : "tooltip"}
      aria-label={`Multimeter: ${component.id}`}
    >
      <div className="mb-1 flex items-center gap-2">
        <span aria-hidden="true">⎓</span>
        <span className="font-semibold">{component.id}</span>
        <span className="min-w-0 flex-1 truncate text-muted" title={summary || SYMBOLS[component.kind].pins.map((p) => p.name).join(", ")}>
          {summary || component.kind.replace(/_/g, " ")}
        </span>
        {pinned && onUnpin && (
          <button
            type="button"
            onClick={onUnpin}
            aria-label={`Unpin ${component.id} meter`}
            title="Unpin (Esc)"
            className="flex h-5 w-5 items-center justify-center rounded text-muted hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
          >
            ×
          </button>
        )}
      </div>
      {noData ? (
        <p className="text-muted">Run a simulation to measure.</p>
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          {rows.map((row) => (
            <div key={row.label} className={`contents ${row.emphasis ? "font-semibold" : "text-muted"}`}>
              <dt className="whitespace-nowrap" title={row.hint}>
                {row.label}
              </dt>
              <dd className="whitespace-pre text-right font-mono tabular-nums text-ink">{formatReadout(row.value ?? Number.NaN, row.unit)}</dd>
            </div>
          ))}
        </dl>
      )}
      {pinned && !noData && isTwoPin(component) && onTogglePlot && (
        <button
          type="button"
          onClick={onTogglePlot}
          aria-pressed={plotted}
          className={`mt-1.5 w-full rounded-md border px-2 py-0.5 text-[11px] focus-visible:outline-2 focus-visible:outline-accent ${
            plotted ? "border-accent bg-accent-soft" : "border-line hover:bg-sunken"
          }`}
          title="Add V across and current of this part to the Simulation plots"
        >
          {plotted ? "✓ Plotted (click to remove)" : "Plot V across and current"}
        </button>
      )}
      {!pinned && <p className="mt-1 text-[10px] text-muted">Click the part to pin this meter</p>}
    </div>
  );
}
