import type { Component } from "../../api/types";
import { formatSI } from "../../lib/si";
import { SYMBOLS } from "./symbols";

/** Short value text for a component, e.g. "4.7 kΩ", "sine 1 V @ 1 kHz", "2N3904" (mirrors the backend). */
export function componentSummary(component: Component): string {
  const symbol = SYMBOLS[component.kind];
  if (symbol.summary) return symbol.summary(component) ?? "";
  const unit = symbol.valueUnit ?? "";
  const parts: string[] = [];
  if (component.value !== undefined && component.value !== null && symbol.valueUnit !== null) {
    parts.push(formatSI(component.value, symbol.valueUnit));
  }
  const waveform = component.waveform;
  if (waveform) {
    if (waveform.shape === "sine") {
      parts.push(`sine ${formatSI(waveform.amplitude, unit)} @ ${formatSI(waveform.frequency, "Hz")}`);
    } else if (waveform.shape === "pulse") {
      parts.push(`pulse ${formatSI(waveform.initial, unit)}→${formatSI(waveform.pulsed, unit)}`);
    } else {
      const shown = waveform.points.slice(0, 4).map(([, v]) => formatSI(v, unit));
      parts.push(`pwl ${shown.join(" → ")}${waveform.points.length > 4 ? " …" : ""}`);
    }
  }
  if (component.ac_magnitude) parts.push(`AC ${component.ac_magnitude}`);
  const model = component.model ?? symbol.defaultModel;
  if (model) parts.push(model);
  return parts.join(", ");
}

/** Nets with generated names (N001, net_3, 7, ...) are not worth labelling on the schematic. */
export function isNamedNet(net: string): boolean {
  return !/^(?:n|net|node)?_?\d+$/i.test(net);
}
