import { describe, expect, it } from "vitest";
import type { Circuit } from "../../api/types";
import { ledCircuit, opampAmplifier } from "../../mocks/circuits";
import { flowSpeed, pinCurrents, pinKey } from "./currentFlow";

describe("pinCurrents", () => {
  it("follows the single loop of an LED circuit", () => {
    const recorded: Record<string, number> = { V1: -0.015, R1: 0.015, D1: 0.015 };
    const pins = pinCurrents(ledCircuit, (id) => recorded[id]);
    expect(pins.get(pinKey("R1", "1"))).toBe(0.015); // into R1 from VCC
    expect(pins.get(pinKey("R1", "2"))).toBe(-0.015); // out of R1 into LED_A
    expect(pins.get(pinKey("D1", "anode"))).toBe(0.015);
    expect(pins.get(pinKey("V1", "+"))).toBe(-0.015); // the source pushes current out of +
  });

  it("fills a single unknown pin per net with Kirchhoff's current law", () => {
    // Op-amp output is unknown; inputs draw nothing; RF and RL currents are known.
    const recorded: Record<string, number> = { RF: -0.0005, RG: 0.0005, RL: 0.0005 };
    const pins = pinCurrents(opampAmplifier, (id) => recorded[id]);
    // Net OUT: U1.out + RF.2 (+0.0005) + RL.1 (+0.0005) = 0 -> out = -1 mA (current leaves the op-amp).
    expect(pins.get(pinKey("U1", "out"))).toBeCloseTo(-0.001);
  });

  it("splits current between two branches of a divider", () => {
    const circuit: Circuit = {
      title: "split",
      description: "",
      components: [
        { id: "V1", kind: "voltage_source", pins: { "+": "A", "-": "GND" }, value: 5 },
        { id: "R1", kind: "resistor", pins: { "1": "A", "2": "GND" }, value: 1000 },
        { id: "R2", kind: "resistor", pins: { "1": "A", "2": "GND" }, value: 4000 },
      ],
    };
    const pins = pinCurrents(circuit, (id) => ({ R1: 0.005, R2: 0.00125 })[id]);
    expect(pins.get(pinKey("V1", "+"))).toBeCloseTo(-0.00625); // KCL at net A
  });
});

describe("flowSpeed", () => {
  it("is logarithmic, signed, and zero below 1 µA or when off", () => {
    expect(flowSpeed(1e-7, "conventional")).toBe(0);
    expect(flowSpeed(1, "off")).toBe(0);
    expect(flowSpeed(1, "conventional")).toBeGreaterThan(flowSpeed(1e-3, "conventional"));
    expect(flowSpeed(1e-3, "electrons")).toBe(-flowSpeed(1e-3, "conventional"));
  });
});
