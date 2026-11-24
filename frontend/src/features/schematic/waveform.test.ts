import { describe, expect, it } from "vitest";
import type { Component } from "../../api/types";
import { componentSummary } from "./componentText";
import { stimulusText } from "./stimulus";

const generator = (waveform: Component["waveform"]): Component => ({ id: "FG1", kind: "function_generator", pins: { "+": "A", "-": "GND" }, waveform });
const pulse = (rise: number, width: number, fall: number) => ({ shape: "pulse" as const, initial: 0, pulsed: 5, delay: 0, rise, width, fall, period: 1e-3 });

describe("waveform names", () => {
  it("recovers square, PWM, triangle and sawtooth from pulse timings", () => {
    expect(componentSummary(generator(pulse(1e-9, 0.5e-3, 1e-9)))).toBe("square 0 V→5 V @ 1 kHz");
    expect(componentSummary(generator(pulse(1e-9, 0.25e-3, 1e-9)))).toBe("pulse 0 V→5 V @ 1 kHz, 25%");
    expect(componentSummary(generator(pulse(0.5e-3 - 1e-9, 2e-9, 0.5e-3 - 1e-9)))).toMatch(/^triangle /);
    expect(componentSummary(generator(pulse(0.998e-3, 1e-9, 1e-6)))).toMatch(/^sawtooth /);
  });

  it("labels latching switches on/off and push buttons pressed/released", () => {
    const toggle: Component = { id: "SW1", kind: "switch", model: "toggle", pins: { "1": "A", "2": "B" }, stimulus: 1 };
    expect(stimulusText(toggle)).toBe("on");
    expect(stimulusText({ ...toggle, model: "push_button" })).toBe("pressed");
  });
});
