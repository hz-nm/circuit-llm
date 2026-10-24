import { describe, expect, it } from "vitest";
import type { Component } from "../../api/types";
import { meterReadings } from "./readings";

const value = (rows: ReturnType<typeof meterReadings>, label: string) => rows.find((r) => r.label === label)?.value;

describe("meterReadings", () => {
  const volts: Record<string, number> = { VCC: 9, LED_A: 1.9, D: 3, G: 5 };
  const v = (net: string) => volts[net];

  it("gives a two-pin part its pin voltages, V across, I through and P", () => {
    const r1: Component = { id: "R1", kind: "resistor", pins: { "1": "VCC", "2": "LED_A" }, value: 470 };
    const rows = meterReadings(r1, v, (id) => (id === "R1" ? 0.0151 : undefined));
    expect(rows.map((r) => r.label)).toEqual(["V(1)", "V(2)", "V across", "I through", "P"]);
    expect(value(rows, "V across")).toBeCloseTo(7.1);
    expect(value(rows, "P")).toBeCloseTo(7.1 * 0.0151);
  });

  it("treats GND as 0 V and leaves unrecorded currents empty", () => {
    const d1: Component = { id: "D1", kind: "led", pins: { anode: "LED_A", cathode: "GND" } };
    const rows = meterReadings(d1, v, () => undefined);
    expect(value(rows, "V across")).toBeCloseTo(1.9);
    expect(value(rows, "I through")).toBeNull();
    expect(value(rows, "P")).toBeNull();
  });

  it("shows V_GS, V_DS, I_D and P for a MOSFET", () => {
    const m1: Component = { id: "M1", kind: "nmos", pins: { drain: "D", gate: "G", source: "GND" } };
    const rows = meterReadings(m1, v, (id) => (id === "M1" ? 2 : undefined));
    expect(value(rows, "V_GS")).toBe(5);
    expect(value(rows, "V_DS")).toBe(3);
    expect(value(rows, "I_D")).toBe(2);
    expect(value(rows, "P")).toBe(6);
  });

  it("gives resistive sensors their stimulus and effective resistance", () => {
    const ldr: Component = { id: "LDR1", kind: "ldr", pins: { "1": "VCC", "2": "LED_A" }, stimulus: 500 };
    const rows = meterReadings(ldr, v, () => 0.001, (id) => (id === "LDR1" ? 120 : undefined));
    expect(value(rows, "light")).toBe(120); // recorded stimulus wins over the constant
    expect(value(rows, "R")).toBeCloseTo(7100);
  });
});
