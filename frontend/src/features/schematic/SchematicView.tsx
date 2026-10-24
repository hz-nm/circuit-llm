import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState, useSyncExternalStore, type PointerEvent as ReactPointerEvent } from "react";
import type { Circuit, Issue } from "../../api/types";
import { formatSI } from "../../lib/si";
import { Button } from "../../ui/Button";
import { useIsDark } from "../../ui/theme";
import { netKey, voltageColor, voltagesAt } from "../simulation/live";
import type { SimulationSession } from "../simulation/session";
import { seriesColor } from "../simulation/UPlotChart";
import { layoutCircuit, type ElkLike } from "./layout";
import { LiveDock } from "./LiveDock";
import { SCHEMATIC_CSS, SchematicContent, type LiveOverlay, type ProbeHandlers } from "./SchematicSvg";
import { usePanZoom } from "./usePanZoom";

let elkPromise: Promise<ElkLike> | null = null;

/** ELK is large, so it is loaded on first use and shared afterwards. */
function loadElk(): Promise<ElkLike> {
  elkPromise ??= import("elkjs/lib/elk.bundled.js").then(({ default: ELK }) => new ELK());
  return elkPromise;
}

const NO_SUBSCRIBE = () => () => {};
const NULL_SNAPSHOT = () => null;

export interface SchematicViewProps {
  circuit: Circuit;
  issues?: readonly Issue[];
  /** Simulation session: enables live voltages, the scrubber and click-to-probe. */
  session?: SimulationSession;
}

export function SchematicView({ circuit, issues, session }: SchematicViewProps) {
  const dark = useIsDark();
  const [showLive, setShowLive] = useState(true);
  const live = session?.live ?? null;
  const liveOn = showLive && live !== null;

  // Layout depends only on the circuit and whether label room is reserved, never on the cursor.
  const layout = useQuery({
    queryKey: ["schematic-layout", circuit, liveOn],
    queryFn: async () => layoutCircuit(await loadElk(), circuit, { reserveVoltages: liveOn }),
    staleTime: Infinity,
    gcTime: 60_000,
    placeholderData: (previous) => previous,
  });

  // The cursor moves at animation-frame rate; only this view re-renders (layout is untouched).
  const cursor = session?.cursor;
  const x = useSyncExternalStore(cursor?.subscribe ?? NO_SUBSCRIBE, cursor?.get ?? NULL_SNAPSHOT);
  const voltages = useMemo(() => (live ? voltagesAt(live, x) : null), [live, x]);

  const highlight = useMemo(
    () => new Set((issues ?? []).filter((i) => i.severity === "error" && i.component_id).map((i) => i.component_id!)),
    [issues],
  );

  const sweep = live?.kind === "sweep" ? live.sweep : null;
  const overlay = useMemo<LiveOverlay | null>(() => {
    if (!session) return null;
    const maxAbs = live?.maxAbs ?? 0;
    return {
      voltages: liveOn ? voltages : null,
      colorOf: (v) => voltageColor(v, maxAbs, dark),
      formatVoltage: (v) => formatSI(v, "V", 3),
      probed: session.probes.nets,
      probeColor: (net) => {
        const index = sweep?.traces.findIndex((t) => t.net && netKey(t.net) === netKey(net)) ?? -1;
        return index >= 0 ? seriesColor(index, dark) : dark ? "#4c8dff" : "#2563eb";
      },
    };
  }, [session, live, liveOn, voltages, dark, sweep]);

  const containerRef = useRef<HTMLDivElement>(null);
  const schematic = layout.data ?? null;
  const size = useMemo(() => (schematic ? { width: schematic.width, height: schematic.height } : null), [schematic]);
  const { view, fit, zoomIn, zoomOut, didDrag, handlers } = usePanZoom(containerRef, size);

  // Hover tooltip for click-to-probe.
  const [hover, setHover] = useState<{ net: string; x: number; y: number } | null>(null);
  const probeHandlers = useMemo<ProbeHandlers | null>(() => {
    if (!session) return null;
    return {
      onToggle: (net) => {
        if (!didDrag()) session.probes.toggle(net);
      },
      onHover: (net: string | null, event?: ReactPointerEvent) => {
        const rect = containerRef.current?.getBoundingClientRect();
        if (!net || !event || !rect) setHover(null);
        else setHover({ net, x: event.clientX - rect.left, y: event.clientY - rect.top });
      },
    };
  }, [session, didDrag]);

  const hoverVoltage = hover && voltages ? voltages.get(netKey(hover.net)) : undefined;
  const hoverProbed = hover ? (session?.probes.isProbed(hover.net) ?? false) : false;

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-lg border border-line bg-panel/90 p-1 shadow-sm backdrop-blur">
        {live && (
          <label className="flex cursor-pointer items-center gap-1.5 px-2 text-xs text-muted">
            <input type="checkbox" checked={showLive} onChange={(e) => setShowLive(e.target.checked)} />
            Live voltages
          </label>
        )}
        <Button size="sm" variant="ghost" onClick={zoomOut} aria-label="Zoom out" title="Zoom out (−)">
          −
        </Button>
        <Button size="sm" variant="ghost" onClick={zoomIn} aria-label="Zoom in" title="Zoom in (+)">
          +
        </Button>
        <Button size="sm" variant="ghost" onClick={fit} title="Fit to view (0)">
          Fit
        </Button>
      </div>
      <div
        ref={containerRef}
        className="schematic-canvas relative min-h-0 flex-1 cursor-grab touch-none overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-accent active:cursor-grabbing"
        tabIndex={0}
        role="img"
        aria-label={`Schematic of ${circuit.title}. Drag or use arrow keys to pan, scroll or +/− to zoom, 0 to fit. Click a wire to probe it; the Probes list below does the same from the keyboard.`}
        {...handlers}
      >
        {layout.isError && <p className="p-4 text-sm text-danger">Could not lay out the schematic: {String(layout.error)}</p>}
        {!schematic && layout.isPending && <p className="p-4 text-sm text-muted">Laying out schematic…</p>}
        {schematic && (
          <svg className="h-full w-full select-none">
            <style>{SCHEMATIC_CSS}</style>
            <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              <SchematicContent schematic={schematic} highlight={highlight} live={overlay} probe={probeHandlers} />
            </g>
          </svg>
        )}
        {hover && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-20 whitespace-nowrap rounded-md border border-line bg-panel px-2 py-1 text-xs shadow-md"
            style={{ left: hover.x + 12, top: hover.y + 12 }}
          >
            {hoverProbed ? "Click to remove probe from " : "Click to probe "}
            <strong className="font-mono">{hover.net}</strong>
            {hoverVoltage !== undefined && <span className="tabular-nums"> ({formatSI(hoverVoltage, "V", 3)})</span>}
          </div>
        )}
      </div>
      {session && <LiveDock circuit={circuit} session={session} voltages={voltages} enabled={showLive} />}
    </div>
  );
}
