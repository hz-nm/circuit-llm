import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { Circuit, Issue } from "../../api/types";
import { formatReadout } from "../../lib/si";
import { Button } from "../../ui/Button";
import { useIsDark } from "../../ui/theme";
import { MeterCard } from "../multimeter/MeterCard";
import { currentsAt, netKey, stimuliAt, voltagesAt } from "../simulation/live";
import type { SimulationSession } from "../simulation/session";
import { seriesColor } from "../simulation/UPlotChart";
import { pinCurrents, type FlowMode } from "./currentFlow";
import { FlowLayer } from "./FlowLayer";
import { layoutCircuit, type ElkLike } from "./layout";
import { LiveDock } from "./LiveDock";
import { SCHEMATIC_CSS, SchematicContent, type LiveOverlay, type ProbeHandlers, type RatingMark } from "./SchematicSvg";
import { usePanZoom } from "./usePanZoom";

let elkPromise: Promise<ElkLike> | null = null;

/** ELK is large, so it is loaded on first use and shared afterwards. */
function loadElk(): Promise<ElkLike> {
  elkPromise ??= import("elkjs/lib/elk.bundled.js").then(({ default: ELK }) => new ELK());
  return elkPromise;
}

const NO_SUBSCRIBE = () => () => {};
const NULL_SNAPSHOT = () => null;
const CARD_WIDTH = 240;

function initialFlowMode(): FlowMode {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "off" : "conventional";
  } catch {
    return "conventional";
  }
}

export interface SchematicViewProps {
  circuit: Circuit;
  issues?: readonly Issue[];
  /** Simulation session: enables live voltages, the scrubber, probes and the multimeter. */
  session?: SimulationSession;
}

type Hover = { kind: "net" | "component"; id: string; x: number; y: number };

export function SchematicView({ circuit, issues, session }: SchematicViewProps) {
  const dark = useIsDark();
  const [showLabels, setShowLabels] = useState(true);
  const live = session?.live ?? null;
  const labelsOn = showLabels && live !== null;

  // Layout depends only on the circuit and whether label room is reserved, never on the cursor.
  const layout = useQuery({
    queryKey: ["schematic-layout", circuit, labelsOn],
    queryFn: async () => layoutCircuit(await loadElk(), circuit, { reserveVoltages: labelsOn }),
    staleTime: Infinity,
    gcTime: 60_000,
    placeholderData: (previous) => previous,
  });

  // The cursor moves at animation-frame rate; only this view re-renders (layout is untouched).
  const cursor = session?.cursor;
  const x = useSyncExternalStore(cursor?.subscribe ?? NO_SUBSCRIBE, cursor?.get ?? NULL_SNAPSHOT);
  const voltages = useMemo(() => (live ? voltagesAt(live, x) : null), [live, x]);
  const currents = useMemo(() => (live ? currentsAt(live, x) : null), [live, x]);
  const stimuli = useMemo(() => (live ? stimuliAt(live, x) : null), [live, x]);

  // Current flow: currents into every pin at the cursor (recorded + Kirchhoff), drawn as moving dots.
  const [flowMode, setFlowMode] = useState<FlowMode>(initialFlowMode);
  const flowPins = useMemo(
    () => (currents ? pinCurrents(circuit, (id) => currents.get(netKey(id))) : null),
    [circuit, currents],
  );

  const highlight = useMemo(
    () => new Set((issues ?? []).filter((i) => i.severity === "error" && i.component_id).map((i) => i.component_id!)),
    [issues],
  );

  // Bench-check marks: errors outrank warnings; all messages of a part go in its tooltip.
  const ratingIssues = session?.ratingIssues;
  const ratings = useMemo(() => {
    const map = new Map<string, RatingMark>();
    for (const [id, list] of ratingIssues ?? []) {
      map.set(id, {
        severity: list.some((c) => c.severity === "error") ? "error" : "warning",
        message: list.map((c) => c.message).join(" · "),
      });
    }
    return map;
  }, [ratingIssues]);

  const sweep = live?.kind === "sweep" ? live.sweep : null;
  const overlay = useMemo<LiveOverlay | null>(() => {
    if (!session) return null;
    return {
      voltages: labelsOn ? voltages : null,
      formatVoltage: (v) => formatReadout(v, "V"),
      probed: session.probes.nets,
      probeColor: (net) => {
        const index = sweep?.traces.findIndex((t) => t.net && netKey(t.net) === netKey(net)) ?? -1;
        return index >= 0 ? seriesColor(index, dark) : dark ? "#4c8dff" : "#2563eb";
      },
    };
  }, [session, labelsOn, voltages, dark, sweep]);

  const containerRef = useRef<HTMLDivElement>(null);
  const schematic = layout.data ?? null;
  const size = useMemo(() => (schematic ? { width: schematic.width, height: schematic.height } : null), [schematic]);
  const { view, fit, zoomIn, zoomOut, didDrag, handlers } = usePanZoom(containerRef, size);

  // ---- hover (wire tooltip or component meter) and pinned meters
  const [hover, setHover] = useState<Hover | null>(null);
  // Pinned meters live in the session (so they survive tab switches); without one there are none.
  const [localPinned, setLocalPinned] = useState<string[]>([]);
  const pinned = session?.pinned ?? localPinned;
  const setPinned = session?.setPinned ?? setLocalPinned;

  const position = (event: ReactPointerEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    return rect ? { x: event.clientX - rect.left, y: event.clientY - rect.top } : { x: 0, y: 0 };
  };

  const probeHandlers = useMemo<ProbeHandlers | null>(() => {
    if (!session) return null;
    return {
      onToggle: (net) => {
        if (!didDrag()) session.probes.toggle(net);
      },
      onHover: (net: string | null, event?: ReactPointerEvent) => {
        if (!net || !event) setHover((h) => (h?.kind === "net" ? null : h));
        else setHover({ kind: "net", id: net, ...position(event) });
      },
    };
  }, [session, didDrag]);

  const componentAt = (event: { target: EventTarget }) =>
    event.target instanceof Element ? (event.target.closest("[data-component]")?.getAttribute("data-component") ?? null) : null;

  const onSvgPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!session) return;
    const id = componentAt(event);
    if (id) setHover({ kind: "component", id, ...position(event) });
    else setHover((h) => (h?.kind === "component" ? null : h));
  };

  const onSvgClick = (event: ReactMouseEvent<SVGSVGElement>) => {
    if (!session || didDrag()) return;
    const id = componentAt(event);
    if (!id) return;
    setPinned((list) => (list.includes(id) ? list.filter((p) => p !== id) : [...list, id]));
  };

  // Esc unpins the most recently pinned meter (unless typing in a field).
  useEffect(() => {
    if (pinned.length === 0) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      setPinned((list) => list.slice(0, -1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pinned.length, setPinned]);

  const byId = useMemo(() => new Map(circuit.components.map((c) => [c.id, c])), [circuit]);
  const meterProps = (id: string) => {
    const component = byId.get(id)!;
    return {
      component,
      voltages: live ? voltages : null,
      currents: live ? currents : null,
      stimuli: live ? stimuli : null,
      plotted: session?.probes.components.has(netKey(id)) ?? false,
      onTogglePlot: session && live ? () => session.probes.togglePlot(id) : undefined,
      issues: session?.ratingIssues.get(id) ?? [],
    };
  };

  const hoverNetVoltage = hover?.kind === "net" && voltages ? voltages.get(netKey(hover.id)) : undefined;
  const hoverProbed = hover?.kind === "net" ? (session?.probes.isProbed(hover.id) ?? false) : false;
  const containerWidth = containerRef.current?.clientWidth ?? 800;
  const hoverComponent = hover?.kind === "component" && byId.has(hover.id) && !pinned.includes(hover.id) ? hover : null;

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-lg border border-line bg-panel/90 p-1 shadow-sm backdrop-blur">
        {live && (
          <label className="flex cursor-pointer items-center gap-1.5 px-2 text-xs text-muted">
            <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
            Net voltages
          </label>
        )}
        {live && (
          <label className="flex items-center gap-1.5 px-1 text-xs text-muted" title="Animate the current in the wires (speed ∝ log |I|)">
            Current flow
            <select
              value={flowMode}
              onChange={(e) => setFlowMode(e.target.value as FlowMode)}
              className="rounded-md border border-line bg-bg px-1 py-0.5 text-xs text-ink"
            >
              <option value="off">Off</option>
              <option value="conventional">Conventional</option>
              <option value="electrons">Electrons</option>
            </select>
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

      {pinned.length > 0 && (
        <div className="absolute left-3 top-3 z-10 flex max-h-[calc(100%-5rem)] flex-col gap-2 overflow-y-auto" aria-label="Pinned meters">
          {pinned
            .filter((id) => byId.has(id))
            .map((id) => (
              <MeterCard key={id} pinned onUnpin={() => setPinned((list) => list.filter((p) => p !== id))} {...meterProps(id)} />
            ))}
        </div>
      )}

      <div
        ref={containerRef}
        className="schematic-canvas relative min-h-0 flex-1 cursor-grab touch-none overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-accent active:cursor-grabbing"
        tabIndex={0}
        role="img"
        aria-label={`Schematic of ${circuit.title}. Drag or use arrow keys to pan, scroll or +/− to zoom, 0 to fit. Hover a part for its multimeter and click to pin it; click a wire to probe it (the Probes list below does the same from the keyboard).`}
        {...handlers}
      >
        {layout.isError && <p className="p-4 text-sm text-danger">Could not lay out the schematic: {String(layout.error)}</p>}
        {!schematic && layout.isPending && <p className="p-4 text-sm text-muted">Laying out schematic…</p>}
        {schematic && (
          <svg className="h-full w-full select-none" onPointerMove={onSvgPointerMove} onPointerLeave={() => setHover(null)} onClick={onSvgClick}>
            <style>{SCHEMATIC_CSS}</style>
            <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              <SchematicContent schematic={schematic} highlight={highlight} ratings={ratings} live={overlay} probe={probeHandlers} />
              {flowPins && <FlowLayer schematic={schematic} pins={flowPins} mode={flowMode} />}
            </g>
          </svg>
        )}
        {hover?.kind === "net" && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-20 whitespace-pre rounded-md border border-line bg-panel px-2 py-1 text-xs shadow-md"
            style={{ left: hover.x + 12, top: hover.y + 12 }}
          >
            {hoverProbed ? "Click to remove probe from " : "Click to probe "}
            <strong className="font-mono">{hover.id}</strong>
            {hoverNetVoltage !== undefined && <span className="font-mono tabular-nums"> ({formatReadout(hoverNetVoltage, "V").trim()})</span>}
          </div>
        )}
        {hoverComponent && (
          <div
            className="pointer-events-none absolute z-20"
            style={{ left: Math.min(hoverComponent.x + 16, containerWidth - CARD_WIDTH - 8), top: hoverComponent.y + 16 }}
          >
            <MeterCard pinned={false} {...meterProps(hoverComponent.id)} />
          </div>
        )}
      </div>
      {session && <LiveDock circuit={circuit} session={session} voltages={voltages} />}
    </div>
  );
}
