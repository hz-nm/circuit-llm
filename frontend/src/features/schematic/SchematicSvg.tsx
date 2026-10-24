import { memo, type PointerEvent as ReactPointerEvent } from "react";
import type { LaidOutComponent, Schematic, Wire } from "./layout";
import { GroundGlyph } from "./symbols";
import { composeNetLabel, rotationTransform, type Point } from "./toElk";

const round = (n: number) => Math.round(n * 10) / 10;
const toPath = (points: readonly Point[]) => points.map((p, i) => `${i === 0 ? "M" : "L"}${round(p.x)} ${round(p.y)}`).join("");
const key = (net: string) => net.toUpperCase();

// ---------------------------------------------------------------------------- static layer

function ComponentGlyph({ item, highlighted }: { item: LaidOutComponent; highlighted: boolean }) {
  const { placed } = item;
  const { symbol, rotation, offset, component } = placed;
  return (
    <g
      transform={`translate(${round(item.x)} ${round(item.y)})`}
      className={highlighted ? "sch-component sch-highlight" : "sch-component"}
      data-component={component.id}
    >
      {/* Transparent box so the whole part (not just its strokes) can be hovered and clicked. */}
      <rect width={placed.width} height={placed.height} className="sch-hitbox" />
      <g transform={`translate(${offset.x} ${offset.y}) ${rotationTransform(symbol.width, symbol.height, rotation)}`}>
        {symbol.draw(component, placed.connected)}
      </g>
      {placed.ports.map((port) => port.lead && <path key={port.pin} d={toPath(port.lead)} className="sch-wire" />)}
      {placed.attachments.map(
        (a, i) =>
          a.type === "ground" && (
            <g key={i} className="sch-ground">
              <path d={toPath(a.wire)} className="sch-wire" />
              <GroundGlyph x={a.glyph.x} y={a.glyph.y} up={a.up} />
            </g>
          ),
      )}
    </g>
  );
}

function ComponentLabel({ item }: { item: LaidOutComponent }) {
  const { label } = item;
  return (
    <text x={round(label.x)} y={round(label.y)} textAnchor={label.align} className="sch-label">
      {label.lines.map((line, i) => (
        <tspan key={i} x={round(label.x)} dy={i === 0 ? "1em" : "1.2em"} className={i === 0 ? "sch-label-id" : undefined}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

/** Symbols and component labels: never change while animating, so they are memoised. */
const StaticLayer = memo(function StaticLayer({ schematic, highlight }: { schematic: Schematic; highlight?: ReadonlySet<string> }) {
  return (
    <>
      {schematic.components.map((item) => (
        <ComponentGlyph key={item.placed.component.id} item={item} highlighted={highlight?.has(item.placed.component.id) ?? false} />
      ))}
      {schematic.components.map((item) => (
        <ComponentLabel key={item.placed.component.id} item={item} />
      ))}
    </>
  );
});

// ---------------------------------------------------------------------------- live layer

/** Live state drawn over the static schematic (all optional: without it the schematic is plain). */
export interface LiveOverlay {
  /** Node voltages keyed by upper-cased net name; null when there is no result. */
  voltages: ReadonlyMap<string, number> | null;
  /** Fixed-width formatter, so labels keep their size while animating. */
  formatVoltage: (volts: number) => string;
  probed: ReadonlySet<string>;
  /** Badge colour for a probed net (matches its plot trace when there is one). */
  probeColor: (net: string) => string;
}

export interface ProbeHandlers {
  onToggle: (net: string) => void;
  onHover: (net: string | null, event?: ReactPointerEvent) => void;
}

interface FlagLabel {
  net: string;
  name: string | null;
  anchor: Point;
  align: "start" | "middle" | "end";
  wire: Point[];
}

function flagsOf(schematic: Schematic): FlagLabel[] {
  return schematic.components.flatMap((item) =>
    item.placed.attachments.flatMap((a) =>
      a.type === "flag"
        ? [
            {
              net: a.net,
              name: a.name,
              align: a.align,
              anchor: { x: item.x + a.anchor.x, y: item.y + a.anchor.y },
              wire: a.wire.map((p) => ({ x: item.x + p.x, y: item.y + p.y })),
            },
          ]
        : [],
    ),
  );
}

/** Where to put a net's probe badge: left of its label, else the middle of its longest segment. */
function badgeAnchor(net: string, schematic: Schematic, wires: Wire[], flags: FlagLabel[]): Point | null {
  const label = schematic.netLabels.find((l) => key(l.net) === key(net));
  if (label) return { x: label.x - 10, y: label.y + label.height / 2 };
  let best: { p: Point; len: number } | null = null;
  for (const wire of wires) {
    if (key(wire.net) !== key(net)) continue;
    for (let i = 0; i + 1 < wire.points.length; i++) {
      const a = wire.points[i]!;
      const b = wire.points[i + 1]!;
      const len = Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
      if (!best || len > best.len) best = { p: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, len };
    }
  }
  if (best) return best.p;
  const flag = flags.find((f) => key(f.net) === key(net));
  return flag ? flag.wire[flag.wire.length - 1] ?? null : null;
}

function ProbeBadge({ at, color, net }: { at: Point; color: string; net: string }) {
  return (
    <g transform={`translate(${round(at.x)} ${round(at.y)})`} className="sch-probe-badge" aria-label={`${net} probed`}>
      <circle r={7} fill={color} />
      <path d="M-4 0.5q1-3.5 2 0t2 0t2 0t2 0" fill="none" stroke="#fff" strokeWidth={1.4} strokeLinecap="round" />
    </g>
  );
}

export interface SchematicSvgProps {
  schematic: Schematic;
  highlight?: ReadonlySet<string>;
  live?: LiveOverlay | null;
  probe?: ProbeHandlers | null;
}

/** SVG content of a laid-out schematic (testable with renderToStaticMarkup). */
export function SchematicContent({ schematic, highlight, live = null, probe = null }: SchematicSvgProps) {
  const voltageOf = (net: string) => live?.voltages?.get(key(net));
  const labelText = (net: string, name: string | null) => {
    const v = voltageOf(net);
    return composeNetLabel(name, v !== undefined && live ? live.formatVoltage(v) : null);
  };
  const flags = flagsOf(schematic);
  const probedNets = live ? [...new Set(schematic.wires.map((w) => w.net).concat(flags.map((f) => f.net)))].filter((n) => live.probed.has(key(n))) : [];

  return (
    <g className="sch">
      {/* Probe highlight under the wires: neutral, so it never reads as a voltage colour. */}
      {probedNets.map((net) =>
        schematic.wires
          .filter((w) => w.net === net)
          .map((w) => <path key={`hl:${w.id}`} d={toPath(w.points)} className="sch-probe-glow" />),
      )}
      <g className="sch-wires">
        {schematic.wires.map((wire) => (
          <path key={wire.id} d={toPath(wire.points)} className="sch-wire" data-net={wire.net} />
        ))}
      </g>
      {schematic.junctions.map((j) => (
        <circle key={`${j.x},${j.y}`} cx={round(j.x)} cy={round(j.y)} r={3} className="sch-junction" />
      ))}
      <StaticLayer schematic={schematic} highlight={highlight} />
      {flags.map((f) => (
        <g key={`flag:${f.net}:${f.anchor.x}:${f.anchor.y}`}>
          <path d={toPath(f.wire)} className="sch-wire" />
          <text x={round(f.anchor.x)} y={round(f.anchor.y)} textAnchor={f.align} dominantBaseline="central" className="sch-net-label">
            {labelText(f.net, f.name)}
          </text>
        </g>
      ))}
      {schematic.netLabels.map((label) => {
        const text = labelText(label.net, label.name);
        return (
          text && (
            <text
              key={`${label.net}:${label.x}:${label.y}`}
              x={round(label.x + label.width / 2)}
              y={round(label.y + label.height / 2)}
              textAnchor="middle"
              dominantBaseline="central"
              className="sch-net-label"
            >
              {text}
            </text>
          )
        );
      })}
      {probedNets.map((net) => {
        const at = badgeAnchor(net, schematic, schematic.wires, flags);
        return at && <ProbeBadge key={`badge:${net}`} at={at} color={live!.probeColor(net)} net={net} />;
      })}
      {/* Wide invisible strokes make thin wires easy to hover and click. */}
      {probe &&
        schematic.wires
          .filter((w) => key(w.net) !== "GND")
          .map((wire) => (
            <path
              key={`hit:${wire.id}`}
              d={toPath(wire.points)}
              className="sch-hit"
              onPointerEnter={(e) => probe.onHover(wire.net, e)}
              onPointerMove={(e) => probe.onHover(wire.net, e)}
              onPointerLeave={() => probe.onHover(null)}
              onClick={() => probe.onToggle(wire.net)}
            />
          ))}
    </g>
  );
}

/** Styles for the schematic, inlined so a standalone SVG export looks the same as in the app. */
export const SCHEMATIC_CSS = `
.sch { color: var(--sch-ink, #1f2937); }
.sch-component { stroke: currentColor; stroke-width: 2; fill: none; stroke-linecap: round; }
.sch-component .sym-body { fill: var(--sch-body, transparent); }
.sch-highlight { color: var(--sch-highlight, #dc2626); }
.sch-wire { stroke: var(--sch-wire, #2563eb); stroke-width: 1.75; fill: none; stroke-linejoin: round; stroke-linecap: round; }
.sch-ground { stroke: currentColor; }
.sch-junction { fill: var(--sch-wire, #2563eb); }
.sch-label { font: 11px ui-sans-serif, system-ui, sans-serif; fill: var(--sch-muted, #4b5563); stroke: none; }
.sch-label-id { font-weight: 600; fill: var(--sch-ink, #1f2937); }
.sch-net-label { font: 600 10.5px ui-monospace, SFMono-Regular, Menlo, monospace; fill: var(--sch-net, #0f766e); stroke: var(--sch-bg, #ffffff); stroke-width: 4px; stroke-linejoin: round; paint-order: stroke; font-variant-numeric: tabular-nums; }
.sch-probe-glow { fill: none; stroke: var(--sch-ink, #1f2937); stroke-width: 9; stroke-opacity: 0.16; stroke-linecap: round; stroke-linejoin: round; }
.sch-probe-badge circle { stroke: var(--sch-bg, #ffffff); stroke-width: 2; }
.sch-hitbox { fill: transparent; stroke: none; pointer-events: all; cursor: pointer; }
.sch-net-label { white-space: pre; }
.sch-hit { fill: none; stroke: transparent; stroke-width: 12; cursor: pointer; pointer-events: stroke; }
.sch-hit:hover { stroke: var(--sch-wire, #2563eb); stroke-opacity: 0.15; }
`;
