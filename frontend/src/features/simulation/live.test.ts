import { describe, expect, it } from "vitest";
import { opampTranResult } from "../../mocks/circuits";
import { buildLiveVoltages, defaultDriver, sampleAt, voltageColor, voltagesAt } from "./live";

describe("live voltages", () => {
  it("interpolates between samples and clamps at the ends", () => {
    const xs = [0, 1, 2];
    const ys = [0, 10, -10];
    expect(sampleAt(xs, ys, 0.25)).toBeCloseTo(2.5);
    expect(sampleAt(xs, ys, 1.5)).toBeCloseTo(0);
    expect(sampleAt(xs, ys, -1)).toBe(0);
    expect(sampleAt(xs, ys, 9)).toBe(-10);
  });

  it("builds per-net arrays from every node-voltage trace of the driving sweep", () => {
    const driver = defaultDriver(opampTranResult);
    const live = buildLiveVoltages(opampTranResult, driver);
    expect(live?.kind).toBe("sweep");
    // Probed and recorded-only nets are both available; the current trace is not a net.
    const at = voltagesAt(live!, 0.25e-3);
    expect([...at.keys()].sort()).toEqual(["FB", "IN", "OUT", "VNEG", "VPOS"]);
    expect(at.get("IN")).toBeCloseTo(0.5, 2);
    expect(live!.maxAbs).toBe(12);
  });

  it("maps voltages onto a diverging scale with a neutral midpoint", () => {
    expect(voltageColor(0, 5, false)).toBe("rgb(156, 163, 175)");
    expect(voltageColor(5, 5, false)).toBe("rgb(220, 38, 38)");
    expect(voltageColor(-50, 5, false)).toBe("rgb(29, 78, 216)");
  });
});
