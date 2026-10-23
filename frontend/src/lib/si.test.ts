import { describe, expect, it } from "vitest";
import { formatSI } from "./si";

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
