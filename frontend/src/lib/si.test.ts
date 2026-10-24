import { describe, expect, it } from "vitest";
import { formatEng, formatSI, parseEng } from "./si";

describe("formatSI", () => {
  it("uses SI prefixes like the backend", () => {
    expect(formatSI(4700, "Ω")).toBe("4.7 kΩ");
    expect(formatSI(1e-7, "F")).toBe("100 nF");
    expect(formatSI(2.2e-6, "F")).toBe("2.2 µF");
    expect(formatSI(9, "V")).toBe("9 V");
    expect(formatSI(-0.0123, "A")).toBe("-12.3 mA");
    expect(formatSI(0, "V")).toBe("0 V");
  });
});

describe("parseEng", () => {
  it("parses engineering notation with optional units", () => {
    expect(parseEng("5m")).toBeCloseTo(5e-3);
    expect(parseEng("10u")).toBeCloseTo(1e-5);
    expect(parseEng("2.5 ms")).toBeCloseTo(2.5e-3);
    expect(parseEng("1e-3")).toBeCloseTo(1e-3);
    expect(parseEng("1meg")).toBe(1e6);
    expect(parseEng("abc")).toBeNull();
    expect(parseEng("")).toBeNull();
    expect(formatEng(0.003)).toBe("3m");
    expect(formatEng(1e-5)).toBe("10u");
  });
});
