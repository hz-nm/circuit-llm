import type { LaidOutComponent, Schematic } from "./layout";
import { GroundGlyph } from "./symbols";
import { rotationTransform, type Point } from "./toElk";

const toPath = (points: readonly Point[]) =>
  points.map((p, i) => `${i === 0 ? "M" : "L"}${round(p.x)} ${round(p.y)}`).join("");

const round = (n: number) => Math.round(n * 10) / 10;

function ComponentGlyph({ item, highlighted }: { item: LaidOutComponent; highlighted: boolean }) {
  const { placed } = item;
  const { symbol, rotation, offset, component } = placed;
  return (
    <g
      transform={`translate(${round(item.x)} ${round(item.y)})`}
      className={highlighted ? "sch-component sch-highlight" : "sch-component"}
      data-component={component.id}
    >
      <title>{`${component.id} (${component.kind})`}</title>
      <g transform={`translate(${offset.x} ${offset.y}) ${rotationTransform(symbol.width, symbol.height, rotation)}`}>
        {symbol.draw(component, placed.connected)}
      </g>
      {placed.ports.map((port) => port.lead && <path key={port.pin} d={toPath(port.lead)} className="sch-wire" />)}
      {placed.attachments.map((a, i) =>
        a.type === "ground" ? (
          <g key={i} className="sch-ground">
            <path d={toPath(a.wire)} className="sch-wire" />
            <GroundGlyph x={a.glyph.x} y={a.glyph.y} up={a.up} />
          </g>
        ) : (
          <g key={i}>
            <path d={toPath(a.wire)} className="sch-wire" />
            <text x={a.anchor.x} y={a.anchor.y} textAnchor={a.align} dominantBaseline="central" className="sch-net-label">
              {a.text}
            </text>
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

export interface SchematicSvgProps {
  schematic: Schematic;
  highlight?: ReadonlySet<string>;
}

/** Pure SVG rendering of a laid-out schematic (no interactivity; testable with renderToStaticMarkup). */
export function SchematicContent({ schematic, highlight }: SchematicSvgProps) {
  return (
    <g className="sch">
      <g className="sch-wires">
        {schematic.wires.map((wire) => (
          <path key={wire.id} d={toPath(wire.points)} className="sch-wire" data-net={wire.net} />
        ))}
      </g>
      {schematic.junctions.map((j) => (
        <circle key={`${j.x},${j.y}`} cx={round(j.x)} cy={round(j.y)} r={3} className="sch-junction" />
      ))}
      {schematic.components.map((item) => (
        <ComponentGlyph key={item.placed.component.id} item={item} highlighted={highlight?.has(item.placed.component.id) ?? false} />
      ))}
      {schematic.components.map((item) => (
        <ComponentLabel key={item.placed.component.id} item={item} />
      ))}
      {schematic.netLabels.map((label) => (
        <text
          key={`${label.net}:${label.x}:${label.y}`}
          x={round(label.x + label.width / 2)}
          y={round(label.y + label.height / 2)}
          textAnchor="middle"
          dominantBaseline="central"
          className="sch-net-label"
        >
          {label.text}
        </text>
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
.sch-net-label { font: 600 10.5px ui-monospace, SFMono-Regular, Menlo, monospace; fill: var(--sch-net, #0f766e); stroke: var(--sch-bg, #ffffff); stroke-width: 4px; stroke-linejoin: round; paint-order: stroke; }
`;
