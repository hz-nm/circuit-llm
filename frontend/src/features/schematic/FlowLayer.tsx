import { useEffect, useMemo, useRef } from "react";
import { flowSpeed, pinKey, type FlowMode } from "./currentFlow";
import type { Schematic } from "./layout";
import type { Point } from "./toElk";

interface FlowPath {
  key: string;
  d: string;
  /** Signed current along the path direction (A), or undefined when it can't be determined. */
  current: number | undefined;
}

/** Dot spacing (stroke-dasharray "0 14"); offsets wrap at this period so dots never jump. */
const DOT_PERIOD = 14;

const toPath = (points: readonly Point[]) => points.map((p, i) => `${i === 0 ? "M" : "L"}${Math.round(p.x * 10) / 10} ${Math.round(p.y * 10) / 10}`).join("");

/** Every wire whose current we can name, with the current along its drawn direction. */
function flowPaths(schematic: Schematic, pins: ReadonlyMap<string, number>): FlowPath[] {
  const paths: FlowPath[] = [];
  for (const wire of schematic.wires) {
    // Drawn from the net's root pin to the target pin: forward = into the target component.
    const current = wire.target ? pins.get(pinKey(wire.target.componentId, wire.target.pin)) : undefined;
    paths.push({ key: wire.id, d: toPath(wire.points), current });
  }
  for (const item of schematic.components) {
    for (const [i, a] of item.placed.attachments.entries()) {
      if (a.type !== "ground") continue;
      // Drawn from the pin to the ground symbol: forward = out of the component at that pin.
      const into = pins.get(pinKey(item.placed.component.id, a.pin));
      const points = a.wire.map((p) => ({ x: item.x + p.x, y: item.y + p.y }));
      paths.push({ key: `gnd:${item.placed.component.id}:${i}`, d: toPath(points), current: into === undefined ? undefined : -into });
    }
  }
  return paths;
}

/**
 * Dots moving along the wires: speed from |I| (logarithmic), direction from its
 * sign. Animated by writing stroke-dashoffset from requestAnimationFrame, so
 * React never re-renders per frame and the layout is untouched.
 */
export function FlowLayer({ schematic, pins, mode }: { schematic: Schematic; pins: ReadonlyMap<string, number>; mode: FlowMode }) {
  const paths = useMemo(() => flowPaths(schematic, pins), [schematic, pins]);
  const speeds = useRef(new Map<string, number>());
  const offsets = useRef(new Map<string, number>());
  const elements = useRef(new Map<string, SVGPathElement>());

  // New speeds take effect on the next frame; offsets carry on, so dots never jump.
  speeds.current = new Map(paths.map((p) => [p.key, p.current === undefined ? 0 : flowSpeed(p.current, mode)]));

  useEffect(() => {
    if (mode === "off") return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      for (const [key, el] of elements.current) {
        const speed = speeds.current.get(key) ?? 0;
        if (speed === 0) continue;
        const offset = ((offsets.current.get(key) ?? 0) - speed * dt) % DOT_PERIOD; // decreasing offset = forward
        offsets.current.set(key, offset);
        el.style.strokeDashoffset = String(offset);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [mode]);

  if (mode === "off") return null;
  return (
    <g className="sch-flow-layer" aria-hidden="true">
      {paths.map((p) =>
        speeds.current.get(p.key) ? (
          <path
            key={p.key}
            d={p.d}
            className="sch-flow"
            data-speed={Math.round(speeds.current.get(p.key) ?? 0)}
            ref={(el) => {
              if (el) elements.current.set(p.key, el);
              else elements.current.delete(p.key);
            }}
          />
        ) : null,
      )}
    </g>
  );
}
