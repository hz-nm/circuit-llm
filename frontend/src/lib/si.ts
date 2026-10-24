const PREFIXES: readonly (readonly [number, string])[] = [
  [1e12, "T"],
  [1e9, "G"],
  [1e6, "M"],
  [1e3, "k"],
  [1, ""],
  [1e-3, "m"],
  [1e-6, "µ"],
  [1e-9, "n"],
  [1e-12, "p"],
  [1e-15, "f"],
];

function trimNumber(value: number, precision: number): string {
  // toPrecision then strip trailing zeros, without falling into exponent notation.
  const text = Number(value.toPrecision(precision)).toString();
  return text.includes("e") ? value.toFixed(Math.max(0, precision - 1)) : text;
}

/**
 * Format a value with an SI prefix, matching the backend's `format_si`:
 * `formatSI(4700, "Ω") === "4.7 kΩ"`, `formatSI(1e-7, "F") === "100 nF"`.
 */
export function formatSI(value: number, unit = "", precision = 3): string {
  if (!Number.isFinite(value)) return `${value} ${unit}`.trim();
  if (value === 0) return `0 ${unit}`.trim();
  const magnitude = Math.abs(value);
  const [scale, prefix] =
    PREFIXES.find(([s]) => magnitude >= s * 0.999_999) ?? PREFIXES[PREFIXES.length - 1]!;
  return `${trimNumber(value / scale, precision)} ${prefix}${unit}`.trim();
}

/** Compact axis-tick formatting (no space, short), e.g. "10k", "1.5m". */
export function formatTick(value: number, unit = ""): string {
  if (value === 0) return `0${unit}`;
  return formatSI(value, unit, 3).replace(" ", "");
}

const ENG_PREFIX: Record<string, number> = {
  T: 1e12,
  G: 1e9,
  M: 1e6,
  k: 1e3,
  K: 1e3,
  m: 1e-3,
  u: 1e-6,
  µ: 1e-6,
  μ: 1e-6,
  n: 1e-9,
  p: 1e-12,
  f: 1e-15,
};

/**
 * Parse engineering notation such as "5m", "10u", "2.5 ms", "1e-3" or "1meg"
 * (an optional trailing unit is ignored). Returns null for anything else.
 */
export function parseEng(text: string): number | null {
  const match = /^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*((?:[mM][eE][gG])|[TGMkKmuµμnpf])?\s*([a-zA-Z]{0,3})\s*$/.exec(text);
  if (!match) return null;
  const [, number, prefix = "", unit = ""] = match;
  // "1s" is a unit, but "1m" alone is milli; reject an unknown unit glued to nothing.
  if (unit && !/^(s|sec|v|a|hz)$/i.test(unit)) return null;
  const multiplier = prefix.toLowerCase() === "meg" ? 1e6 : prefix ? ENG_PREFIX[prefix]! : 1;
  const value = Number(number) * multiplier;
  return Number.isFinite(value) ? value : null;
}

/** Compact, typeable engineering text for an input field, e.g. 0.003 → "3m", 1e-5 → "10u". */
export function formatEng(value: number): string {
  return formatSI(value, "", 4).replace(" ", "").replace("µ", "u");
}

const FIGURE_SPACE = "\u2007"; // as wide as a digit in tabular/monospace fonts

/**
 * Fixed-width live readout, e.g. " 16.3  V", "−1.25 mA", "  142 mW": a sign
 * column, a 3-significant-digit mantissa padded to 4 characters, and an SI
 * prefix padded to 1 character. Every value with the same unit renders as a
 * string of the same length, so animated readouts (in a monospace or
 * tabular-nums font) never change width.
 */
export function formatReadout(value: number, unit: string): string {
  if (!Number.isFinite(value)) return `${FIGURE_SPACE}${"–".padStart(4, FIGURE_SPACE)} ${FIGURE_SPACE}${unit}`;
  const magnitude = Math.abs(value);
  let scale = 1;
  let prefix = "";
  if (magnitude >= 1e-15) {
    const found = PREFIXES.find(([s]) => magnitude >= s * 0.9995) ?? PREFIXES[PREFIXES.length - 1]!;
    [scale, prefix] = found;
  }
  let mantissa = magnitude / scale;
  // Rounding can carry into the next prefix (999.7 m -> 1.00).
  if (Number(mantissa.toPrecision(3)) >= 1000 && scale < 1e12) {
    const next = PREFIXES[PREFIXES.findIndex(([s]) => s === scale) - 1]!;
    [scale, prefix] = next;
    mantissa = magnitude / scale;
  }
  const digits = mantissa === 0 ? "0.00" : mantissa.toPrecision(3);
  const sign = value < 0 && Number(digits) !== 0 ? "−" : FIGURE_SPACE;
  return `${sign}${digits.padStart(4, FIGURE_SPACE)} ${(prefix || FIGURE_SPACE)}${unit}`;
}
