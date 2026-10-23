/**
 * Circuit → ELK graph conversion.
 *
 * Every component becomes an ELK node with fixed-position ports (one per
 * connected pin). Ground is never routed as a net: each grounded pin gets its
 * own ground symbol drawn right at the pin, and the glyph is folded into the
 * node's bounding box so the layout keeps clear of it. Pins on a net of their
 * own get a small net-name flag instead of a wire. Every other net becomes a
 * star of edges from one "root" pin to the rest; with ELK's orthogonal router
 * edges leaving the same port share segments, which reads as a single wire.
 */
import type { ElkExtendedEdge, ElkLabel, ElkNode, ElkPort } from "elkjs/lib/elk-api";
import type { Circuit, Component } from "../../api/types";
import { componentSummary, isNamedNet } from "./componentText";
import { SYMBOLS, type Side, type SymbolDef } from "./symbols";

export const GROUND = "GND";
export type Rotation = 0 | 90 | 180 | 270;

export interface Point {
  x: number;
  y: number;
}

export interface Box {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** Something drawn at a pin in addition to the symbol (all coordinates node-local). */
export type PinAttachment =
  | { type: "ground"; wire: Point[]; glyph: Point; up: boolean }
  | { type: "flag"; wire: Point[]; text: string; anchor: Point; align: "start" | "middle" | "end" };

export interface PlacedPort {
  pin: string;
  net: string;
  side: Side;
  /** Port position on the node boundary (node-local). */
  x: number;
  y: number;
  /** Extra lead from the symbol's pin to the boundary, when the node box was widened. */
  lead: Point[] | null;
}

/** A component's oriented symbol, attachments and ports inside its ELK node box. */
export interface PlacedComponent {
  component: Component;
  symbol: SymbolDef;
  rotation: Rotation;
  /** Translation of the symbol's (rotated) origin inside the node box. */
  offset: Point;
  width: number;
  height: number;
  ports: PlacedPort[];
  attachments: PinAttachment[];
  connected: ReadonlySet<string>;
  label: string[];
}

export interface NetEdgeMeta {
  id: string;
  net: string;
}

export interface ElkConversion {
  graph: ElkNode;
  components: Map<string, PlacedComponent>;
  edges: NetEdgeMeta[];
}

export interface ConversionOptions {
  /** Node voltages from an operating-point result, keyed by net name (case-insensitive). */
  nodeVoltages?: Record<string, number> | null;
  formatVoltage?: (volts: number) => string;
}

// ---------------------------------------------------------------------------- geometry

const ROTATE_SIDE: Record<Side, Side> = { NORTH: "EAST", EAST: "SOUTH", SOUTH: "WEST", WEST: "NORTH" };

function rotateSide(side: Side, rotation: Rotation): Side {
  let result = side;
  for (let r = 0; r < rotation; r += 90) result = ROTATE_SIDE[result];
  return result;
}

/** Rotate a local point clockwise inside a `w` x `h` box; the result lives in the rotated box. */
export function rotatePoint(p: Point, w: number, h: number, rotation: Rotation): Point {
  switch (rotation) {
    case 0:
      return p;
    case 90:
      return { x: h - p.y, y: p.x };
    case 180:
      return { x: w - p.x, y: h - p.y };
    case 270:
      return { x: p.y, y: w - p.x };
  }
}

/** SVG transform that draws a canonical symbol rotated clockwise into its rotated box. */
export function rotationTransform(w: number, h: number, rotation: Rotation): string {
  switch (rotation) {
    case 0:
      return "";
    case 90:
      return `translate(${h} 0) rotate(90)`;
    case 180:
      return `translate(${w} ${h}) rotate(180)`;
    case 270:
      return `translate(0 ${w}) rotate(270)`;
  }
}

const OUTWARD: Record<Side, Point> = {
  NORTH: { x: 0, y: -1 },
  EAST: { x: 1, y: 0 },
  SOUTH: { x: 0, y: 1 },
  WEST: { x: -1, y: 0 },
};

const CHAR_WIDTH = 6.6; // ~11px UI font
const LINE_HEIGHT = 13;

export function textWidth(text: string): number {
  return Math.ceil(text.length * CHAR_WIDTH) + 2;
}

function extend(box: Box, p: Point): void {
  box.minX = Math.min(box.minX, p.x);
  box.minY = Math.min(box.minY, p.y);
  box.maxX = Math.max(box.maxX, p.x);
  box.maxY = Math.max(box.maxY, p.y);
}

// ---------------------------------------------------------------------------- orientation

function chooseRotation(symbol: SymbolDef, pins: Record<string, string>): Rotation {
  const grounded = (name: string | undefined) => name !== undefined && pins[name] === GROUND;
  const [first, second] = symbol.pins.map((p) => p.name);
  switch (symbol.orientation) {
    case "fixed":
      return 0;
    case "vertical":
      // Canonical: first pin on top. Flip if only the top pin is grounded.
      return grounded(first) && !grounded(second) ? 180 : 0;
    case "two-terminal":
      // Canonical: first pin west. Hang shunt elements down towards their ground.
      if (grounded(second) && !grounded(first)) return 90; // west -> north
      if (grounded(first) && !grounded(second)) return 270; // west -> south
      return 0;
  }
}

// ---------------------------------------------------------------------------- attachments

const GROUND_LEAD = 10;
const SIDE_GROUND_LEAD = 14;
const FLAG_LEAD = 8;

function groundAttachment(p: Point, side: Side): PinAttachment {
  switch (side) {
    case "SOUTH":
      return { type: "ground", wire: [p, { x: p.x, y: p.y + GROUND_LEAD }], glyph: { x: p.x, y: p.y + GROUND_LEAD }, up: false };
    case "NORTH":
      return { type: "ground", wire: [p, { x: p.x, y: p.y - GROUND_LEAD }], glyph: { x: p.x, y: p.y - GROUND_LEAD }, up: true };
    case "EAST":
    case "WEST": {
      const dx = OUTWARD[side].x * SIDE_GROUND_LEAD;
      const corner = { x: p.x + dx, y: p.y };
      const end = { x: p.x + dx, y: p.y + 8 };
      return { type: "ground", wire: [p, corner, end], glyph: end, up: false };
    }
  }
}

function flagAttachment(p: Point, side: Side, text: string): PinAttachment {
  const out = OUTWARD[side];
  const end = { x: p.x + out.x * FLAG_LEAD, y: p.y + out.y * FLAG_LEAD };
  const gap = 3;
  switch (side) {
    case "EAST":
      return { type: "flag", wire: [p, end], text, anchor: { x: end.x + gap, y: end.y }, align: "start" };
    case "WEST":
      return { type: "flag", wire: [p, end], text, anchor: { x: end.x - gap, y: end.y }, align: "end" };
    case "NORTH":
      return { type: "flag", wire: [p, end], text, anchor: { x: end.x, y: end.y - 8 }, align: "middle" };
    case "SOUTH":
      return { type: "flag", wire: [p, end], text, anchor: { x: end.x, y: end.y + 8 }, align: "middle" };
  }
}

function attachmentBox(a: PinAttachment): Point[] {
  if (a.type === "ground") {
    const g = a.glyph;
    const dy = a.up ? -8 : 8;
    return [...a.wire, { x: g.x - 8, y: g.y }, { x: g.x + 8, y: g.y + dy }];
  }
  const w = textWidth(a.text);
  const left = a.align === "start" ? a.anchor.x : a.align === "end" ? a.anchor.x - w : a.anchor.x - w / 2;
  return [...a.wire, { x: left, y: a.anchor.y - LINE_HEIGHT / 2 }, { x: left + w, y: a.anchor.y + LINE_HEIGHT / 2 }];
}

// ---------------------------------------------------------------------------- placement

function voltageText(net: string, options: ConversionOptions): string | null {
  const voltages = options.nodeVoltages;
  if (!voltages || net === GROUND) return null;
  const key = Object.keys(voltages).find((k) => k.toLowerCase() === net.toLowerCase());
  if (key === undefined) return null;
  const format = options.formatVoltage ?? ((v: number) => `${v.toPrecision(3)} V`);
  return format(voltages[key]!);
}

/** Text to show for a net (name and/or operating-point voltage), or null for none. */
export function netLabelText(net: string, options: ConversionOptions): string | null {
  const parts = [isNamedNet(net) ? net : null, voltageText(net, options)].filter((p): p is string => p !== null);
  return parts.length > 0 ? parts.join(" = ") : null;
}

export function placeComponent(
  component: Component,
  netSizes: ReadonlyMap<string, number>,
  options: ConversionOptions = {},
): PlacedComponent {
  const symbol = SYMBOLS[component.kind];
  const rotation = chooseRotation(symbol, component.pins);
  const rotated = rotation === 90 || rotation === 270;
  const w = rotated ? symbol.height : symbol.width;
  const h = rotated ? symbol.width : symbol.height;
  const connected = new Set(Object.keys(component.pins));

  const box: Box = { minX: 0, minY: 0, maxX: w, maxY: h };
  const attachments: PinAttachment[] = [];
  const routed: { pin: string; net: string; side: Side; at: Point }[] = [];

  for (const pin of symbol.pins) {
    const net = component.pins[pin.name];
    if (net === undefined) continue;
    const at = rotatePoint({ x: pin.x, y: pin.y }, symbol.width, symbol.height, rotation);
    const side = rotateSide(pin.side, rotation);
    let attachment: PinAttachment | null = null;
    if (net === GROUND) {
      attachment = groundAttachment(at, side);
    } else if ((netSizes.get(net) ?? 0) < 2) {
      const text = netLabelText(net, options);
      attachment = text ? flagAttachment(at, side, text) : null;
    } else {
      routed.push({ pin: pin.name, net, side, at });
    }
    if (attachment) {
      attachments.push(attachment);
      for (const p of attachmentBox(attachment)) extend(box, p);
    }
  }

  const offset = { x: -box.minX, y: -box.minY };
  const shift = (p: Point): Point => ({ x: p.x + offset.x, y: p.y + offset.y });
  const width = box.maxX - box.minX;
  const height = box.maxY - box.minY;

  // Ports sit on the node boundary; draw a lead when the box grew past the pin.
  const ports: PlacedPort[] = routed.map(({ pin, net, side, at }) => {
    const p = shift(at);
    const edge: Point =
      side === "WEST" ? { x: 0, y: p.y } : side === "EAST" ? { x: width, y: p.y } : side === "NORTH" ? { x: p.x, y: 0 } : { x: p.x, y: height };
    const lead = edge.x === p.x && edge.y === p.y ? null : [p, edge];
    return { pin, net, side, x: edge.x, y: edge.y, lead };
  });

  const shifted = attachments.map((a): PinAttachment =>
    a.type === "ground"
      ? { ...a, wire: a.wire.map(shift), glyph: shift(a.glyph) }
      : { ...a, wire: a.wire.map(shift), anchor: shift(a.anchor) },
  );

  const summary = componentSummary(component);
  return {
    component,
    symbol,
    rotation,
    offset,
    width,
    height,
    ports,
    attachments: shifted,
    connected,
    label: summary ? [component.id, summary] : [component.id],
  };
}

function labelPlacement(placed: PlacedComponent): string {
  const side = placed.symbol.labelSide;
  if (side === "top" && placed.rotation % 180 === 0) return "OUTSIDE V_TOP H_CENTER";
  if (side === "right-top") return "OUTSIDE H_RIGHT V_TOP";
  return "OUTSIDE H_RIGHT V_CENTER";
}

// ---------------------------------------------------------------------------- nets → edges

/** Lower is a better edge source: outputs on the east, then bottom/top pins, inputs last. */
const SOURCE_RANK: Record<Side, number> = { EAST: 0, NORTH: 1, SOUTH: 2, WEST: 3 };

export function portId(componentId: string, pin: string): string {
  return `${componentId}::${pin}`;
}

export function circuitToElk(circuit: Circuit, options: ConversionOptions = {}): ElkConversion {
  const netSizes = new Map<string, number>();
  for (const c of circuit.components) {
    for (const net of Object.values(c.pins)) netSizes.set(net, (netSizes.get(net) ?? 0) + 1);
  }

  const components = new Map<string, PlacedComponent>();
  const children: ElkNode[] = [];
  const netPorts = new Map<string, { componentId: string; port: PlacedPort; order: number }[]>();
  let order = 0;

  for (const component of circuit.components) {
    const placed = placeComponent(component, netSizes, options);
    components.set(component.id, placed);
    const ports: ElkPort[] = placed.ports.map((p) => {
      const list = netPorts.get(p.net) ?? [];
      list.push({ componentId: component.id, port: p, order: order++ });
      netPorts.set(p.net, list);
      return {
        id: portId(component.id, p.pin),
        x: p.x,
        y: p.y,
        width: 0,
        height: 0,
        layoutOptions: { "elk.port.side": p.side },
      };
    });
    const label: ElkLabel = {
      id: `${component.id}::label`,
      text: placed.label.join("\n"),
      width: Math.max(...placed.label.map(textWidth)),
      height: placed.label.length * LINE_HEIGHT,
    };
    children.push({
      id: component.id,
      width: placed.width,
      height: placed.height,
      ports,
      labels: [label],
      layoutOptions: {
        "elk.portConstraints": "FIXED_POS",
        "elk.nodeLabels.placement": labelPlacement(placed),
      },
    });
  }

  const edges: ElkExtendedEdge[] = [];
  const edgeMeta: NetEdgeMeta[] = [];
  for (const [net, members] of netPorts) {
    if (members.length < 2) continue;
    const sorted = [...members].sort(
      (a, b) => SOURCE_RANK[a.port.side] - SOURCE_RANK[b.port.side] || a.order - b.order,
    );
    const root = sorted[0]!;
    const text = netLabelText(net, options);
    sorted.slice(1).forEach((target, i) => {
      const id = `net:${net}:${i}`;
      edges.push({
        id,
        sources: [portId(root.componentId, root.port.pin)],
        targets: [portId(target.componentId, target.port.pin)],
        labels:
          i === 0 && text
            ? [{ id: `${id}:label`, text, width: textWidth(text), height: LINE_HEIGHT }]
            : undefined,
      });
      edgeMeta.push({ id, net });
    });
  }

  const graph: ElkNode = {
    id: "root",
    layoutOptions: LAYOUT_OPTIONS,
    children,
    edges,
  };
  return { graph, components, edges: edgeMeta };
}

export const LAYOUT_OPTIONS: Record<string, string> = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.edgeRouting": "ORTHOGONAL",
  "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
  "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
  "elk.layered.spacing.nodeNodeBetweenLayers": "45",
  "elk.layered.spacing.edgeNodeBetweenLayers": "18",
  "elk.layered.spacing.edgeEdgeBetweenLayers": "12",
  "elk.spacing.nodeNode": "35",
  "elk.spacing.edgeNode": "18",
  "elk.spacing.edgeEdge": "12",
  "elk.spacing.labelNode": "4",
  "elk.spacing.edgeLabel": "3",
  "elk.edgeLabels.placement": "CENTER",
  "elk.layered.edgeLabels.sideSelection": "ALWAYS_UP",
  "elk.spacing.componentComponent": "50",
  "elk.padding": "[top=20,left=20,bottom=20,right=20]",
};
