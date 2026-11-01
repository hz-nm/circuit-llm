import { describe, expect, it } from "vitest";
import type { Component } from "../../api/types";
import { sensorReadout } from "./SensorSlider";
import { STIMULUS } from "./stimulus";

describe("sensorReadout", () => {
  it("shows an LDR's resistance, sense voltage and current at a fixed width", () => {
    const ldr: Component = { id: "LDR1", kind: "ldr", pins: { "1": "VBAT", "2": "SENSE" } };
    const volts: Record<string, number> = { VBAT: 12, SENSE: 3.9 };
    const text = (lux: number, sense: number) =>
      sensorReadout(ldr, STIMULUS.ldr!, lux, (n) => (n === "SENSE" ? sense : volts[n]), () => sense / 10000);
    const a = text(120, 3.9);
    const plain = a.split(String.fromCharCode(0x2007)).join(" ");
    expect(plain).toContain("20.8 kΩ · SENSE  3.90  V");
    expect(text(5, 0.5).length).toBe(a.length); // no jitter while dragging
  });
});
