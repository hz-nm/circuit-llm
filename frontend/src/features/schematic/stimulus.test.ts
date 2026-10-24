import { describe, expect, it } from "vitest";
import type { Component } from "../../api/types";
import { formatStimulus, STIMULUS, stimulusText } from "./stimulus";

describe("sensor stimulus text", () => {
  it("describes constant and pwl environments", () => {
    const ldr: Component = { id: "LDR1", kind: "ldr", pins: { "1": "A", "2": "B" }, stimulus: { shape: "pwl", points: [[0, 1000], [0.4, 0.5], [0.6, 0.5], [1, 1000]] } };
    expect(stimulusText(ldr)).toBe("light pwl 1000 → 0.5 → 1000 lux");
    expect(stimulusText({ ...ldr, stimulus: 500 })).toBe("light 500 lux");
  });

  it("formats light at a fixed width across its range", () => {
    const light = STIMULUS.ldr!;
    const lengths = new Set([0.5, 10.5, 33, 999.9, 1000].map((v) => formatStimulus(v, light).length));
    expect(lengths.size).toBe(1);
  });
});
