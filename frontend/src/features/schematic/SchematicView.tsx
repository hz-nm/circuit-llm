import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import type { Circuit, Issue } from "../../api/types";
import { formatSI } from "../../lib/si";
import { Button } from "../../ui/Button";
import { layoutCircuit, type ElkLike } from "./layout";
import { SCHEMATIC_CSS, SchematicContent } from "./SchematicSvg";
import { usePanZoom } from "./usePanZoom";

let elkPromise: Promise<ElkLike> | null = null;

/** ELK is large, so it is loaded on first use and shared afterwards. */
function loadElk(): Promise<ElkLike> {
  elkPromise ??= import("elkjs/lib/elk.bundled.js").then(({ default: ELK }) => new ELK());
  return elkPromise;
}

export interface SchematicViewProps {
  circuit: Circuit;
  /** Node voltages from an operating-point result, if one exists. */
  nodeVoltages?: Record<string, number> | null;
  issues?: readonly Issue[];
}

export function SchematicView({ circuit, nodeVoltages, issues }: SchematicViewProps) {
  const [showVoltages, setShowVoltages] = useState(true);
  const voltages = showVoltages ? (nodeVoltages ?? null) : null;

  const layout = useQuery({
    queryKey: ["schematic-layout", circuit, voltages],
    queryFn: async () =>
      layoutCircuit(await loadElk(), circuit, {
        nodeVoltages: voltages,
        formatVoltage: (v) => formatSI(v, "V"),
      }),
    staleTime: Infinity,
    gcTime: 60_000,
    placeholderData: (previous) => previous,
  });

  const highlight = useMemo(
    () => new Set((issues ?? []).filter((i) => i.severity === "error" && i.component_id).map((i) => i.component_id!)),
    [issues],
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const schematic = layout.data ?? null;
  const size = useMemo(
    () => (schematic ? { width: schematic.width, height: schematic.height } : null),
    [schematic],
  );
  const { view, fit, zoomIn, zoomOut, handlers } = usePanZoom(containerRef, size);

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-lg border border-line bg-panel/90 p-1 shadow-sm backdrop-blur">
        {nodeVoltages && (
          <label className="flex cursor-pointer items-center gap-1.5 px-2 text-xs text-muted">
            <input type="checkbox" checked={showVoltages} onChange={(e) => setShowVoltages(e.target.checked)} />
            Node voltages
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
        aria-label={`Schematic of ${circuit.title}. Drag or use arrow keys to pan, scroll or +/− to zoom, 0 to fit.`}
        {...handlers}
      >
        {layout.isError && (
          <p className="p-4 text-sm text-danger">Could not lay out the schematic: {String(layout.error)}</p>
        )}
        {!schematic && layout.isPending && <p className="p-4 text-sm text-muted">Laying out schematic…</p>}
        {schematic && (
          <svg className="h-full w-full select-none" aria-hidden="true">
            <style>{SCHEMATIC_CSS}</style>
            <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              <SchematicContent schematic={schematic} highlight={highlight} />
            </g>
          </svg>
        )}
      </div>
    </div>
  );
}
