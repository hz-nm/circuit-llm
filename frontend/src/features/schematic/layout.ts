import type { ElkExtendedEdge, ElkNode } from "elkjs/lib/elk-api";
import type { Circuit } from "../../api/types";
import { circuitToElk, type ConversionOptions, type PlacedComponent, type Point } from "./toElk";

export interface LaidOutComponent {
  placed: PlacedComponent;
  x: number;
  y: number;
  label: { x: number; y: number; width: number; lines: string[]; align: "middle" | "start" };
}

export interface Wire {
  id: string;
  net: string;
  points: Point[];
}

export interface NetLabel {
  net: string;
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Schematic {
  width: number;
  height: number;
  components: LaidOutComponent[];
  wires: Wire[];
  junctions: Point[];
  netLabels: NetLabel[];
}

/** Minimal ELK interface (so tests can pass a Node instance and the app a lazily-loaded one). */
export interface ElkLike {
  layout(graph: ElkNode): Promise<ElkNode>;
}

export async function layoutCircuit(
  elk: ElkLike,
  circuit: Circuit,
  options: ConversionOptions = {},
): Promise<Schematic> {
  const conversion = circuitToElk(circuit, options);
  const result = await elk.layout(conversion.graph);

  const components: LaidOutComponent[] = (result.children ?? []).map((node) => {
    const placed = conversion.components.get(node.id)!;
    const x = node.x ?? 0;
    const y = node.y ?? 0;
    const label = node.labels?.[0];
    const right = (label?.x ?? 0) >= placed.width - 1;
    return {
      placed,
      x,
      y,
      label: {
        x: x + (label?.x ?? 0) + (right ? 0 : (label?.width ?? 0) / 2),
        y: y + (label?.y ?? 0),
        width: label?.width ?? 0,
        lines: placed.label,
        align: right ? "start" : "middle",
      },
    };
  });

  const netOf = new Map(conversion.edges.map((e) => [e.id, e.net]));
  const wires: Wire[] = [];
  const netLabels: NetLabel[] = [];
  for (const edge of (result.edges ?? []) as ElkExtendedEdge[]) {
    const net = netOf.get(edge.id) ?? "";
    for (const section of edge.sections ?? []) {
      wires.push({
        id: section.id ?? edge.id,
        net,
        points: [section.startPoint, ...(section.bendPoints ?? []), section.endPoint].map((p) => ({ x: p.x, y: p.y })),
      });
    }
    for (const label of edge.labels ?? []) {
      netLabels.push({
        net,
        text: label.text ?? net,
        x: label.x ?? 0,
        y: label.y ?? 0,
        width: label.width ?? 0,
        height: label.height ?? 0,
      });
    }
  }

  return {
    width: result.width ?? 0,
    height: result.height ?? 0,
    components,
    wires,
    junctions: findJunctions(wires),
    netLabels,
  };
}

// ---------------------------------------------------------------------------- junctions

type Direction = "N" | "E" | "S" | "W";

const EPS = 0.5;

/**
 * Find wire junctions: points where three or more wire branches of the same net
 * meet. For each candidate point (every segment end) we collect the directions
 * in which some segment of the net leaves it; three or more means a T or cross
 * where the net branches, which is where a schematic draws a dot. Crossing wires
 * of *different* nets never produce a dot because nets are checked separately.
 */
export function findJunctions(wires: readonly Wire[]): Point[] {
  const byNet = new Map<string, [Point, Point][]>();
  for (const wire of wires) {
    const segments = byNet.get(wire.net) ?? [];
    for (let i = 0; i + 1 < wire.points.length; i++) {
      const a = wire.points[i]!;
      const b = wire.points[i + 1]!;
      if (Math.abs(a.x - b.x) > EPS || Math.abs(a.y - b.y) > EPS) segments.push([a, b]);
    }
    byNet.set(wire.net, segments);
  }

  const junctions: Point[] = [];
  const seen = new Set<string>();
  for (const segments of byNet.values()) {
    const candidates = segments.flatMap(([a, b]) => [a, b]);
    for (const p of candidates) {
      const key = `${Math.round(p.x)},${Math.round(p.y)}`;
      if (seen.has(key)) continue;
      const directions = new Set<Direction>();
      for (const [a, b] of segments) for (const d of directionsFrom(p, a, b)) directions.add(d);
      if (directions.size >= 3) {
        seen.add(key);
        junctions.push({ x: p.x, y: p.y });
      }
    }
  }
  return junctions;
}

/** Directions in which the axis-aligned segment a–b leaves point p (if p lies on it). */
function directionsFrom(p: Point, a: Point, b: Point): Direction[] {
  const result: Direction[] = [];
  if (Math.abs(a.y - b.y) <= EPS && Math.abs(p.y - a.y) <= EPS) {
    const lo = Math.min(a.x, b.x);
    const hi = Math.max(a.x, b.x);
    if (p.x < lo - EPS || p.x > hi + EPS) return result;
    if (hi - p.x > EPS) result.push("E");
    if (p.x - lo > EPS) result.push("W");
  } else if (Math.abs(a.x - b.x) <= EPS && Math.abs(p.x - a.x) <= EPS) {
    const lo = Math.min(a.y, b.y);
    const hi = Math.max(a.y, b.y);
    if (p.y < lo - EPS || p.y > hi + EPS) return result;
    if (hi - p.y > EPS) result.push("S");
    if (p.y - lo > EPS) result.push("N");
  }
  return result;
}
