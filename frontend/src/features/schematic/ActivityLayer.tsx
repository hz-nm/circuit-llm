import { BUZZER_SOUNDING_A } from "../multimeter/readings";
import { netKey } from "../simulation/live";
import type { Schematic } from "./layout";
import { rotatePoint } from "./toElk";

/** Seconds per revolution of the motor indicator: loosely follows rpm on a log scale. */
export function spinSeconds(rpm: number): number {
  return Math.min(4, Math.max(0.25, 3.5 - 0.75 * Math.log10(Math.max(1, rpm))));
}

/**
 * Small "it's working" cues at the cursor: sound waves next to a buzzer that
 * draws more than half its rated current, and a rotating ring around a turning
 * motor. Pure CSS animation (disabled for prefers-reduced-motion).
 */
export function ActivityLayer({
  schematic,
  currents,
  outputs,
}: {
  schematic: Schematic;
  currents: ReadonlyMap<string, number> | null;
  outputs: ReadonlyMap<string, number> | null;
}) {
  return (
    <g aria-hidden="true">
      {schematic.components.map((item) => {
        const { component, symbol, rotation, offset } = item.placed;
        const kind = component.kind;
        if (kind === "buzzer") {
          const current = currents?.get(netKey(component.id));
          if (current === undefined || Math.abs(current) <= BUZZER_SOUNDING_A) return null;
          const at = rotatePoint({ x: 30, y: 6 }, symbol.width, symbol.height, rotation);
          return (
            <g key={component.id} transform={`translate(${item.x + offset.x + at.x + 14} ${item.y + offset.y + at.y})`} className="sch-sound">
              <path d="M0 -5A7 7 0 0 1 0 5" />
              <path d="M4 -9A11 11 0 0 1 4 9" />
            </g>
          );
        }
        if (kind === "dc_motor") {
          const rpm = outputs?.get(netKey(component.id));
          if (rpm === undefined || rpm <= 0.5) return null;
          const c = rotatePoint({ x: 30, y: 20 }, symbol.width, symbol.height, rotation);
          return (
            <circle
              key={component.id}
              cx={item.x + offset.x + c.x}
              cy={item.y + offset.y + c.y}
              r={17}
              className="sch-spin"
              style={{ animationDuration: `${spinSeconds(rpm)}s` }}
            />
          );
        }
        return null;
      })}
    </g>
  );
}

/** Styles for the activity cues (appended to the schematic CSS). */
export const ACTIVITY_CSS = `
.sch-sound path { fill: none; stroke: var(--sch-flow, #d97706); stroke-width: 1.75; stroke-linecap: round; animation: sch-pulse 0.6s ease-in-out infinite; }
.sch-sound path + path { animation-delay: 0.3s; }
.sch-spin { fill: none; stroke: var(--sch-flow, #d97706); stroke-width: 2; stroke-dasharray: 5 6; transform-box: fill-box; transform-origin: center; animation: sch-rotate 1s linear infinite; }
@keyframes sch-pulse { 0%, 100% { opacity: 0.15; } 50% { opacity: 1; } }
@keyframes sch-rotate { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .sch-sound path, .sch-spin { animation: none; } }
`;
