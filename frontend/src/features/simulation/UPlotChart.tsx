import { useEffect, useRef, useState } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { formatSI, formatTick } from "../../lib/si";
import { useIsDark } from "../../ui/theme";

/** Categorical series colours (fixed order; validated reference palette), light and dark steps. */
const SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];

export function seriesColor(index: number, dark: boolean): string {
  const palette = dark ? SERIES_DARK : SERIES_LIGHT;
  return palette[index % palette.length]!;
}

export interface ChartSeries {
  name: string;
  values: number[];
  /** Index into the categorical palette (stable per trace, so toggling never repaints others). */
  colorIndex: number;
  visible: boolean;
}

export interface UPlotChartProps {
  title: string;
  x: number[];
  xLabel: string;
  xUnit: string;
  logX: boolean;
  yLabel: string;
  yUnit: string;
  series: ChartSeries[];
  height?: number;
  /** Charts with the same key share their cursor (e.g. Bode magnitude + phase). */
  syncKey?: string;
  /** Plain-number formatter for y (e.g. dB and degrees should not get SI prefixes). */
  plainY?: boolean;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function UPlotChart(props: UPlotChartProps) {
  const { title, x, xLabel, xUnit, logX, yLabel, yUnit, series, height = 240, syncKey, plainY = false } = props;
  const dark = useIsDark();
  const wrapRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  const [cursorIdx, setCursorIdx] = useState<number | null>(null);

  const formatY = (v: number) => (plainY ? `${Number(v.toPrecision(4))} ${yUnit}` : formatSI(v, yUnit, 4));

  // (Re)create the plot when the data, axes or theme change.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ink = cssVar("--c-muted");
    const grid = cssVar("--c-line");
    const axis = (unit: string, label: string, plain: boolean, log = false): uPlot.Axis => ({
      label,
      stroke: ink,
      grid: { stroke: grid, width: 1 },
      ticks: { stroke: grid, width: 1 },
      font: "11px ui-sans-serif, system-ui, sans-serif",
      labelFont: "11px ui-sans-serif, system-ui, sans-serif",
      // uPlot passes null for unlabeled ticks; on log axes only decades get a label.
      values: (_u, splits) =>
        splits.map((v: number | null) => {
          if (v === null || v === undefined) return "";
          if (log && Math.abs(Math.log10(Math.abs(v)) % 1) > 1e-9) return "";
          return plain ? String(Number(v.toPrecision(4))) : formatTick(v, unit);
        }),
      size: 54,
    });
    const opts: uPlot.Options = {
      width: Math.max(200, el.clientWidth),
      height,
      legend: { show: false },
      cursor: {
        sync: syncKey ? { key: syncKey } : undefined,
        points: { size: 8 },
      },
      scales: { x: { time: false, distr: logX ? 3 : 1 } },
      axes: [axis(xUnit, `${xLabel}${xUnit ? ` (${xUnit})` : ""}`, false, logX), axis(yUnit, `${yLabel}${yUnit ? ` (${yUnit})` : ""}`, plainY)],
      series: [
        {},
        ...series.map((s) => ({
          label: s.name,
          stroke: seriesColor(s.colorIndex, dark),
          width: 2,
          show: s.visible,
          points: { show: false },
        })),
      ],
      hooks: {
        setCursor: [(u) => setCursorIdx(u.cursor.idx ?? null)],
      },
    };
    const data: uPlot.AlignedData = [x, ...series.map((s) => s.values)];
    const plot = new uPlot(opts, data, el);
    plotRef.current = plot;

    const observer = new ResizeObserver(() => plot.setSize({ width: Math.max(200, el.clientWidth), height }));
    observer.observe(el);
    return () => {
      observer.disconnect();
      plot.destroy();
      plotRef.current = null;
    };
    // Visibility is applied separately below so toggling a trace doesn't rebuild the chart.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [x, series.length, series.map((s) => s.name).join("|"), xLabel, xUnit, logX, yLabel, yUnit, height, syncKey, dark, plainY]);

  useEffect(() => {
    const plot = plotRef.current;
    if (!plot) return;
    series.forEach((s, i) => {
      if (plot.series[i + 1]?.show !== s.visible) plot.setSeries(i + 1, { show: s.visible });
    });
  }, [series]);

  const xAtCursor = cursorIdx !== null ? x[cursorIdx] : undefined;

  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 flex flex-wrap items-baseline gap-x-3 text-xs">
        <span className="font-medium text-ink">{title}</span>
        {xAtCursor !== undefined && (
          <span className="text-muted">
            at {xLabel} = <strong className="text-ink">{formatSI(xAtCursor, xUnit, 4)}</strong>
          </span>
        )}
      </figcaption>
      <div ref={wrapRef} className="w-full" />
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label={`${title} legend`}>
        {series.map((s) => {
          const value = cursorIdx !== null ? s.values[cursorIdx] : undefined;
          return (
            <li key={s.name} className={s.visible ? "" : "opacity-50"}>
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden="true" className="inline-block h-0.5 w-4 rounded" style={{ background: seriesColor(s.colorIndex, dark) }} />
                <span className="font-mono text-ink">{s.name}</span>
                {value !== undefined && s.visible && <strong className="tabular-nums text-ink">{formatY(value)}</strong>}
              </span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}
