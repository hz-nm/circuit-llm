/**
 * Schematic symbol registry: one entry per catalog component kind.
 *
 * Each symbol is drawn in a canonical orientation in a local box of
 * `width` x `height` (y down). Pins sit on the box edge at fixed positions and
 * their names are exactly the catalog's canonical pin names
 * (backend/src/circuits_llm/domain/catalog.py). Adding a component kind means
 * adding one entry here; `Record<ComponentKind, ...>` makes the compiler insist.
 */
import type { ReactNode } from "react";
import { formatSI } from "../../lib/si";
import type { Component, ComponentKind } from "../../api/types";


/** Kinds with a symbol (every catalog kind; the compiler checks the registry is complete). */
export type SymbolKind = ComponentKind;

export type Side = "NORTH" | "EAST" | "SOUTH" | "WEST";

export interface PinDef {
  name: string;
  x: number;
  y: number;
  side: Side;
  /** Optional pins (op-amp supplies) are only drawn when connected. */
  optional?: boolean;
}

/**
 * How the layout may orient the symbol:
 * - `two-terminal`: horizontal by default, turned vertical when one pin is grounded
 *   (so shunt elements hang down to their ground symbol);
 * - `vertical`: drawn vertically, flipped when its top pin is grounded;
 * - `fixed`: never rotated.
 */
export type Orientation = "two-terminal" | "vertical" | "fixed";

export interface SymbolDef {
  width: number;
  height: number;
  pins: readonly PinDef[];
  orientation: Orientation;
  /** Where the id/value label goes relative to the (oriented) symbol. */
  labelSide: "top" | "right" | "right-top";
  /** Unit of `component.value` (for SI formatting), and the model used when none is given. */
  valueUnit: string | null;
  defaultModel: string | null;
  draw: (component: Component, connected: ReadonlySet<string>) => ReactNode;
  /** Custom value text for the label (default: value with unit, then model). */
  summary?: (component: Component) => string | null;
}

// ---------------------------------------------------------------------------- helpers

const twoTerminalPins = (names: readonly [string, string], width: number, y: number): PinDef[] => [
  { name: names[0], x: 0, y, side: "WEST" },
  { name: names[1], x: width, y, side: "EAST" },
];

function Leads({ x1, x2, y, w }: { x1: number; x2: number; y: number; w: number }) {
  return <path d={`M0 ${y}H${x1}M${x2} ${y}H${w}`} />;
}

const LED_COLORS: Record<string, string> = {
  red: "#ef4444",
  green: "#22c55e",
  yellow: "#eab308",
  blue: "#3b82f6",
  white: "#f8fafc",
  infrared: "#7c3aed",
};

/** Diode body shared by diode/LED/zener: anode on the left, cathode bar at x=38. */
function DiodeBody({ fill, bar }: { fill: string; bar: string }) {
  return (
    <>
      <Leads x1={22} x2={38} y={15} w={60} />
      <path d="M22 5L38 15L22 25Z" fill={fill} strokeLinejoin="round" />
      <path d={bar} />
    </>
  );
}

function Arrow({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const size = 4;
  const a1 = angle + Math.PI * 0.82;
  const a2 = angle - Math.PI * 0.82;
  const head = `M${x2} ${y2}L${x2 + size * Math.cos(a1)} ${y2 + size * Math.sin(a1)}L${x2 + size * Math.cos(a2)} ${y2 + size * Math.sin(a2)}Z`;
  return (
    <>
      <path d={`M${x1} ${y1}L${x2} ${y2}`} />
      <path d={head} fill="currentColor" strokeWidth={1} />
    </>
  );
}

/** BJT body; `emitterTop` is true for PNP (emitter drawn at the top, arrow pointing in). */
function Bjt({ emitterTop }: { emitterTop: boolean }) {
  // Lines from the base bar to the top (y=12) and bottom (y=48) leads.
  const emitterArrow = emitterTop ? (
    <Arrow x1={40} y1={12} x2={27} y2={21} />
  ) : (
    <Arrow x1={24} y1={36} x2={37} y2={45.5} />
  );
  return (
    <>
      <circle cx={32} cy={30} r={19} className="sym-body" />
      <path d="M0 30H22M22 17V43" />
      <path d="M22 24L40 12V0M22 36L40 48V60" />
      {emitterArrow}
    </>
  );
}

/** Enhancement MOSFET; `nChannel` sets the arrow direction and drain/source placement. */
function Mosfet({ nChannel }: { nChannel: boolean }) {
  return (
    <>
      <path d="M0 40H18M18 18V42" />
      <path d="M24 15V25M24 25V35M24 35V45" strokeDasharray="8 3" strokeDashoffset={-1} />
      <path d="M24 20H40V0M24 40H40V60M40 30V40" />
      {nChannel ? <Arrow x1={40} y1={30} x2={26} y2={30} /> : <Arrow x1={25} y1={30} x2={39} y2={30} />}
    </>
  );
}

/** Small "+" / "−" marks drawn with lines so they survive rotation. */
function Plus({ x, y, s = 3.5 }: { x: number; y: number; s?: number }) {
  return <path d={`M${x - s} ${y}H${x + s}M${x} ${y - s}V${y + s}`} strokeWidth={1.5} />;
}
function Minus({ x, y, s = 3.5 }: { x: number; y: number; s?: number }) {
  return <path d={`M${x - s} ${y}H${x + s}`} strokeWidth={1.5} />;
}

// ---------------------------------------------------------------------------- sensors

/** Small text drawn as part of a symbol (no stroke, so it reads at any zoom). */
function SymbolText({ x, y, text, size = 8 }: { x: number; y: number; text: string; size?: number }) {
  return (
    <text x={x} y={y} fontSize={size} fontWeight={700} textAnchor="middle" dominantBaseline="central" fill="currentColor" stroke="none" fontFamily="ui-sans-serif, system-ui, sans-serif">
      {text}
    </text>
  );
}

/** Two arrows pointing at (x, y) from the upper left: light falling on a sensor. */
function IncomingLight({ x, y }: { x: number; y: number }) {
  return (
    <g strokeWidth={1.25}>
      <Arrow x1={x - 12} y1={y - 12} x2={x - 3} y2={y - 3} />
      <Arrow x1={x - 4} y1={y - 14} x2={x + 5} y2={y - 5} />
    </g>
  );
}

const ZIGZAG = (y: number) => `M15 ${y}L17.5 ${y - 6}L22.5 ${y + 6}L27.5 ${y - 6}L32.5 ${y + 6}L37.5 ${y - 6}L42.5 ${y + 6}L45 ${y}`;

/** Two-pin sensor in a 60 x 20 box (pins 1 west, 2 east), like a resistor. */
function sensor(extra: Partial<SymbolDef> & Pick<SymbolDef, "draw">): SymbolDef {
  return {
    width: 60,
    height: 20,
    pins: twoTerminalPins(["1", "2"], 60, 10),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: null,
    defaultModel: null,
    ...extra,
  };
}

// ---------------------------------------------------------------------------- registry

// ---------------------------------------------------------------------------- logic gates

type GateBody = "and" | "or" | "xor" | "not";

/** Body outline of an IEEE distinctive-shape gate in a 90 x 60 box (body spans x 20..70). */
const GATE_BODY: Record<GateBody, string> = {
  and: "M20 8H45A22 22 0 0 1 45 52H20Z",
  or: "M18 8Q44 8 68 30Q44 52 18 52Q29 30 18 8Z",
  xor: "M22 8Q47 8 70 30Q47 52 22 52Q33 30 22 8ZM15 8Q26 30 15 52",
  not: "M22 12L62 30L22 48Z",
};

/** Where an input lead meets the body (the OR/XOR back is curved). */
const GATE_INPUT_END: Record<GateBody, number> = { and: 20, or: 25, xor: 18, not: 22 };
/** Where the body (or its bubble) ends on the output side. */
const GATE_OUTPUT_START: Record<GateBody, number> = { and: 67, or: 68, xor: 70, not: 62 };

function gate(body: GateBody, options: { inverted?: boolean; schmitt?: boolean; inputs: 1 | 2 }): SymbolDef {
  const inputY = options.inputs === 1 ? [30] : [15, 45];
  const inputNames = options.inputs === 1 ? ["a"] : ["a", "b"];
  const out = GATE_OUTPUT_START[body] + (options.inverted ? 8 : 0);
  return {
    width: 90,
    height: 60,
    pins: [
      ...inputNames.map((name, i): PinDef => ({ name, x: 0, y: inputY[i]!, side: "WEST" })),
      { name: "y", x: 90, y: 30, side: "EAST" },
      { name: "vdd", x: 45, y: 0, side: "NORTH", optional: true },
      { name: "vss", x: 45, y: 60, side: "SOUTH", optional: true },
    ],
    orientation: "fixed",
    labelSide: "right-top",
    valueUnit: null,
    defaultModel: null,
    summary: () => null,
    draw: (_c, connected) => (
      <>
        <path d={inputY.map((y) => `M0 ${y}H${GATE_INPUT_END[body]}`).join("") + `M${out} 30H90`} />
        {connected.has("vdd") && <path d={`M45 0V${body === "not" ? 21 : 9}`} />}
        {connected.has("vss") && <path d={`M45 60V${body === "not" ? 39 : 51}`} />}
        <path d={GATE_BODY[body]} strokeLinejoin="round" className="sym-body" />
        {options.inverted && <circle cx={GATE_OUTPUT_START[body] + 4} cy={30} r={4} className="sym-body" />}
        {options.schmitt && <path d="M28 34H38V26M34 34V26H44" strokeWidth={1.25} />}
      </>
    ),
  };
}

// ---------------------------------------------------------------------------- registry

export const SYMBOLS: Record<SymbolKind, SymbolDef> = {
  resistor: {
    width: 60,
    height: 20,
    pins: twoTerminalPins(["1", "2"], 60, 10),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: "Ω",
    defaultModel: null,
    draw: () => (
      <>
        <Leads x1={15} x2={45} y={10} w={60} />
        <path
          d="M15 10L17.5 4L22.5 16L27.5 4L32.5 16L37.5 4L42.5 16L45 10"
          strokeLinejoin="round"
        />
      </>
    ),
  },
  capacitor: {
    width: 60,
    height: 30,
    pins: twoTerminalPins(["1", "2"], 60, 15),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: "F",
    defaultModel: null,
    draw: () => (
      <>
        <Leads x1={26} x2={34} y={15} w={60} />
        <path d="M26 3V27M34 3V27" strokeWidth={2.5} />
      </>
    ),
  },
  inductor: {
    width: 60,
    height: 20,
    pins: twoTerminalPins(["1", "2"], 60, 14),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: "H",
    defaultModel: null,
    draw: () => (
      <path d="M0 14H14a4 4 0 0 1 8 0a4 4 0 0 1 8 0a4 4 0 0 1 8 0a4 4 0 0 1 8 0H60" />
    ),
  },
  voltage_source: {
    width: 40,
    height: 60,
    pins: [
      { name: "+", x: 20, y: 0, side: "NORTH" },
      { name: "-", x: 20, y: 60, side: "SOUTH" },
    ],
    orientation: "vertical",
    labelSide: "right",
    valueUnit: "V",
    defaultModel: null,
    draw: (c) => (
      <>
        <path d="M20 0V15M20 45V60" />
        <circle cx={20} cy={30} r={15} className="sym-body" />
        {c.waveform?.shape === "sine" ? (
          <path d="M12 30q4-9 8 0t8 0" />
        ) : c.waveform?.shape === "pulse" ? (
          <path d="M11 34H15V25H23V34H29" strokeLinejoin="round" />
        ) : c.waveform?.shape === "pwl" ? (
          <path d="M11 26L17 34H23L29 26" strokeLinejoin="round" />
        ) : null}
        <Plus x={20} y={c.waveform ? 20 : 23} s={3} />
        <Minus x={20} y={c.waveform ? 40 : 38} s={3} />
      </>
    ),
  },
  current_source: {
    width: 40,
    height: 60,
    pins: [
      { name: "out", x: 20, y: 0, side: "NORTH" },
      { name: "in", x: 20, y: 60, side: "SOUTH" },
    ],
    orientation: "vertical",
    labelSide: "right",
    valueUnit: "A",
    defaultModel: null,
    draw: () => (
      <>
        <path d="M20 0V15M20 45V60" />
        <circle cx={20} cy={30} r={15} className="sym-body" />
        <Arrow x1={20} y1={40} x2={20} y2={19} />
      </>
    ),
  },
  diode: {
    width: 60,
    height: 30,
    pins: twoTerminalPins(["anode", "cathode"], 60, 15),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: null,
    defaultModel: "1N4148",
    draw: () => <DiodeBody fill="currentColor" bar="M38 5V25" />,
  },
  led: {
    width: 60,
    height: 30,
    pins: twoTerminalPins(["anode", "cathode"], 60, 15),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: null,
    defaultModel: "red",
    draw: (c) => (
      <>
        <DiodeBody fill={LED_COLORS[(c.model ?? "red").toLowerCase()] ?? LED_COLORS.red!} bar="M38 5V25" />
        <g strokeWidth={1.25}>
          <Arrow x1={30} y1={4} x2={37} y2={-3} />
          <Arrow x1={36} y1={7} x2={43} y2={0} />
        </g>
        {c.model?.toLowerCase() === "infrared" && <SymbolText x={11} y={26} text="IR" size={7} />}
      </>
    ),
  },
  zener: {
    width: 60,
    height: 30,
    pins: twoTerminalPins(["anode", "cathode"], 60, 15),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: "V",
    defaultModel: null,
    draw: () => <DiodeBody fill="currentColor" bar="M34 3L38 5V25L42 27" />,
  },
  npn: {
    width: 60,
    height: 60,
    pins: [
      { name: "collector", x: 40, y: 0, side: "NORTH" },
      { name: "base", x: 0, y: 30, side: "WEST" },
      { name: "emitter", x: 40, y: 60, side: "SOUTH" },
    ],
    orientation: "fixed",
    labelSide: "right",
    valueUnit: null,
    defaultModel: "2N3904",
    draw: () => <Bjt emitterTop={false} />,
  },
  pnp: {
    width: 60,
    height: 60,
    pins: [
      { name: "emitter", x: 40, y: 0, side: "NORTH" },
      { name: "base", x: 0, y: 30, side: "WEST" },
      { name: "collector", x: 40, y: 60, side: "SOUTH" },
    ],
    orientation: "fixed",
    labelSide: "right",
    valueUnit: null,
    defaultModel: "2N3906",
    draw: () => <Bjt emitterTop />,
  },
  nmos: {
    width: 50,
    height: 60,
    pins: [
      { name: "drain", x: 40, y: 0, side: "NORTH" },
      { name: "gate", x: 0, y: 40, side: "WEST" },
      { name: "source", x: 40, y: 60, side: "SOUTH" },
    ],
    orientation: "fixed",
    labelSide: "right",
    valueUnit: null,
    defaultModel: "2N7000",
    draw: () => <Mosfet nChannel />,
  },
  pmos: {
    width: 50,
    height: 60,
    pins: [
      { name: "source", x: 40, y: 0, side: "NORTH" },
      { name: "gate", x: 0, y: 40, side: "WEST" },
      { name: "drain", x: 40, y: 60, side: "SOUTH" },
    ],
    orientation: "fixed",
    labelSide: "right",
    valueUnit: null,
    defaultModel: "BS250",
    draw: () => <Mosfet nChannel={false} />,
  },
  opamp: {
    width: 80,
    height: 80,
    pins: [
      { name: "in-", x: 0, y: 24, side: "WEST" },
      { name: "in+", x: 0, y: 56, side: "WEST" },
      { name: "out", x: 80, y: 40, side: "EAST" },
      { name: "v+", x: 40, y: 0, side: "NORTH", optional: true },
      { name: "v-", x: 40, y: 80, side: "SOUTH", optional: true },
    ],
    orientation: "fixed",
    labelSide: "right-top",
    valueUnit: null,
    defaultModel: "ideal",
    draw: (_c, connected) => (
      <>
        <path d="M0 24H16M0 56H16M64 40H80" />
        {connected.has("v+") && <path d="M40 0V24" />}
        {connected.has("v-") && <path d="M40 80V56" />}
        <path d="M16 8L64 40L16 72Z" strokeLinejoin="round" className="sym-body" />
        <Minus x={23} y={24} />
        <Plus x={23} y={56} />
      </>
    ),
  },
  not_gate: gate("not", { inputs: 1, inverted: true }),
  schmitt_inverter: gate("not", { inputs: 1, inverted: true, schmitt: true }),
  and_gate: gate("and", { inputs: 2 }),
  nand_gate: gate("and", { inputs: 2, inverted: true }),
  or_gate: gate("or", { inputs: 2 }),
  nor_gate: gate("or", { inputs: 2, inverted: true }),
  xor_gate: gate("xor", { inputs: 2 }),
  // Light arrows and the NTC mark sit inside the box (above the body) so labels never overlap them.
  ldr: sensor({
    height: 34,
    pins: twoTerminalPins(["1", "2"], 60, 24),
    defaultModel: "GL5528",
    draw: () => (
      <>
        <Leads x1={15} x2={45} y={24} w={60} />
        <path d={ZIGZAG(24)} strokeLinejoin="round" />
        <IncomingLight x={27} y={16} />
      </>
    ),
  }),
  thermistor: sensor({
    height: 34,
    pins: twoTerminalPins(["1", "2"], 60, 22),
    valueUnit: "Ω",
    defaultModel: "B3950",
    draw: () => (
      <>
        <Leads x1={15} x2={45} y={22} w={60} />
        <path d={ZIGZAG(22)} strokeLinejoin="round" />
        {/* NTC: diagonal with a foot, and "-t°" */}
        <path d="M10 33H16L44 8" strokeWidth={1.25} />
        <SymbolText x={53} y={6} text="-t°" size={7} />
      </>
    ),
  }),
  gas_sensor: sensor({
    height: 30,
    pins: twoTerminalPins(["1", "2"], 60, 15),
    defaultModel: "MQ-2",
    draw: () => (
      <>
        <Leads x1={17} x2={43} y={15} w={60} />
        <rect x={17} y={3} width={26} height={24} rx={4} className="sym-body" />
        <circle cx={30} cy={15} r={8} strokeWidth={1} strokeDasharray="2 2" />
        <SymbolText x={30} y={15} text="MQ" size={7} />
      </>
    ),
  }),
  photodiode: {
    width: 60,
    height: 44,
    pins: twoTerminalPins(["anode", "cathode"], 60, 29),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: null,
    defaultModel: "BPW34",
    draw: () => (
      <>
        <g transform="translate(0 14)">
          <DiodeBody fill="none" bar="M38 5V25" />
        </g>
        <IncomingLight x={30} y={20} />
      </>
    ),
  },
  phototransistor: {
    width: 60,
    height: 60,
    pins: [
      { name: "collector", x: 40, y: 0, side: "NORTH" },
      { name: "emitter", x: 40, y: 60, side: "SOUTH" },
    ],
    orientation: "fixed",
    labelSide: "right",
    valueUnit: null,
    defaultModel: "TEPT5700",
    draw: () => (
      <>
        <circle cx={32} cy={30} r={19} className="sym-body" />
        <path d="M22 17V43" />
        <path d="M22 24L40 12V0M22 36L40 48V60" />
        <Arrow x1={24} y1={36} x2={37} y2={45.5} />
        <IncomingLight x={18} y={24} />
      </>
    ),
  },
  pir: {
    width: 70,
    height: 60,
    pins: [
      { name: "vcc", x: 35, y: 0, side: "NORTH" },
      { name: "out", x: 70, y: 30, side: "EAST" },
      { name: "gnd", x: 35, y: 60, side: "SOUTH" },
    ],
    orientation: "fixed",
    labelSide: "right-top",
    valueUnit: null,
    defaultModel: "HC-SR501",
    draw: () => (
      <>
        <path d="M35 0V12M35 48V60M58 30H70" />
        <rect x={18} y={12} width={40} height={36} rx={3} className="sym-body" />
        {/* Fresnel dome on the sensing face */}
        <path d="M18 20A10 10 0 0 0 18 40" className="sym-body" />
        <path d="M14 26H18M13 30H18M14 34H18" strokeWidth={0.75} />
        <SymbolText x={38} y={24} text="PIR" size={8} />
        <SymbolText x={46} y={30} text="out" size={6} />
        <SymbolText x={35} y={17} text="+" size={7} />
        <SymbolText x={35} y={43} text="−" size={7} />
      </>
    ),
  },
  potentiometer: {
    width: 60,
    height: 30,
    pins: [
      { name: "1", x: 0, y: 20, side: "WEST" },
      { name: "w", x: 30, y: 0, side: "NORTH" },
      { name: "2", x: 60, y: 20, side: "EAST" },
    ],
    orientation: "fixed",
    labelSide: "top",
    valueUnit: "Ω",
    defaultModel: null,
    draw: () => (
      <>
        <Leads x1={15} x2={45} y={20} w={60} />
        <path d={ZIGZAG(20)} strokeLinejoin="round" />
        {/* Wiper: lead from w ending in an arrow on the track */}
        <Arrow x1={30} y1={0} x2={30} y2={12} />
      </>
    ),
  },
  lamp: {
    width: 60,
    height: 30,
    pins: twoTerminalPins(["1", "2"], 60, 15),
    orientation: "two-terminal",
    labelSide: "top",
    valueUnit: "W",
    defaultModel: null,
    // value = rated power, model = rated voltage: "50 W @ 12V".
    summary: (c) =>
      [c.value !== undefined && c.value !== null ? formatSI(c.value, "W") : null, c.model].filter(Boolean).join(" @ ") || null,
    draw: () => (
      <>
        <Leads x1={19} x2={41} y={15} w={60} />
        <circle cx={30} cy={15} r={11} className="sym-body" />
        <path d="M22.2 7.2L37.8 22.8M37.8 7.2L22.2 22.8" />
      </>
    ),
  },
};

export function symbolFor(kind: SymbolKind): SymbolDef {
  return SYMBOLS[kind];
}

/** Ground symbol (three bars) with its top-centre at (x, y); `up` draws it pointing up. */
export function GroundGlyph({ x, y, up = false }: { x: number; y: number; up?: boolean }) {
  const d = up ? -1 : 1;
  return (
    <path
      d={`M${x - 8} ${y}H${x + 8}M${x - 5} ${y + 4 * d}H${x + 5}M${x - 2} ${y + 8 * d}H${x + 2}`}
    />
  );
}
