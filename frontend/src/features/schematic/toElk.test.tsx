import ELK from "elkjs/lib/elk.bundled.js";
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MOCK_CIRCUITS, ledCircuit, opampAmplifier, rcLowPass } from "../../mocks/circuits";
import { findJunctions, layoutCircuit } from "./layout";
import { SCHEMATIC_CSS, SchematicContent } from "./SchematicSvg";
import { SYMBOLS } from "./symbols";
import { circuitToElk } from "./toElk";

describe("circuitToElk", () => {
  it("makes one node per component with fixed-position ports for routed pins", () => {
    const { graph } = circuitToElk(rcLowPass);
    expect(graph.children?.map((n) => n.id)).toEqual(["V1", "R1", "C1"]);
    const r1 = graph.children!.find((n) => n.id === "R1")!;
    expect(r1.layoutOptions?.["elk.portConstraints"]).toBe("FIXED_POS");
    expect(r1.ports?.map((p) => p.id)).toEqual(["R1::1", "R1::2"]);
  });

  it("never routes GND: grounded pins get their own ground symbol instead of a port", () => {
    const { graph, components } = circuitToElk(rcLowPass);
    const portIds = graph.children!.flatMap((n) => n.ports ?? []).map((p) => p.id);
    expect(portIds).not.toContain("V1::-");
    expect(portIds).not.toContain("C1::2");
    expect(components.get("C1")!.attachments.filter((a) => a.type === "ground")).toHaveLength(1);
    expect(components.get("V1")!.attachments.filter((a) => a.type === "ground")).toHaveLength(1);
    const edgeNets = (graph.edges ?? []).map((e) => e.id);
    expect(edgeNets.some((id) => id.includes("GND"))).toBe(false);
  });

  it("turns shunt two-terminal parts vertical, with the grounded pin at the bottom", () => {
    const { components } = circuitToElk(rcLowPass);
    const c1 = components.get("C1")!;
    expect(c1.rotation).toBe(90);
    const port = c1.ports.find((p) => p.pin === "1")!;
    expect(port.side).toBe("NORTH");
    expect(components.get("R1")!.rotation).toBe(0);
  });

  it("connects each net as a star from one root port", () => {
    const { graph } = circuitToElk(opampAmplifier);
    const fb = (graph.edges ?? []).filter((e) => e.id.startsWith("net:FB:"));
    expect(fb).toHaveLength(2); // U1.in-, RF.1, RG.1 → 2 edges
    const sources = new Set(fb.flatMap((e) => e.sources));
    expect(sources.size).toBe(1);
    // The net name is attached as a label to exactly one edge of the net.
    expect(fb.filter((e) => e.labels?.length).length).toBe(1);
  });

  it("omits unconnected optional pins (op-amp supplies)", () => {
    const circuit = {
      ...opampAmplifier,
      components: opampAmplifier.components.map((c) =>
        c.id === "U1" ? { ...c, pins: { "in+": "IN", "in-": "FB", out: "OUT" } } : c,
      ),
    };
    const u1 = circuitToElk(circuit).graph.children!.find((n) => n.id === "U1")!;
    expect(u1.ports?.map((p) => p.id).sort()).toEqual(["U1::in+", "U1::in-", "U1::out"]);
  });

  it("annotates nets with operating-point voltages when given", () => {
    const { graph } = circuitToElk(ledCircuit, { nodeVoltages: { vcc: 9, LED_A: 1.83 } });
    const labels = (graph.edges ?? []).flatMap((e) => e.labels ?? []).map((l) => l.text);
    expect(labels).toEqual(expect.arrayContaining(["VCC = 9.00 V", "LED_A = 1.83 V"]));
  });

  it("has a symbol for every kind whose pins sit on the symbol's box edge", () => {
    for (const [kind, symbol] of Object.entries(SYMBOLS)) {
      for (const pin of symbol.pins) {
        const onEdge = pin.x === 0 || pin.y === 0 || pin.x === symbol.width || pin.y === symbol.height;
        expect(onEdge, `${kind}.${pin.name}`).toBe(true);
      }
    }
  });
});

describe("findJunctions", () => {
  it("puts a dot where three branches of a net meet, not where different nets cross", () => {
    const wires = [
      { id: "a", net: "N", points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 20 }] },
      { id: "b", net: "N", points: [{ x: 0, y: 0 }, { x: 40, y: 0 }] },
      { id: "c", net: "M", points: [{ x: 30, y: -10 }, { x: 30, y: 10 }] },
    ];
    expect(findJunctions(wires)).toEqual([{ x: 20, y: 0 }]);
  });
});

describe("layoutCircuit", () => {
  it("lays out every mock circuit without overlapping components", async () => {
    const elk = new ELK();
    const outDir = process.env.SCHEMATIC_OUT;
    for (const circuit of MOCK_CIRCUITS) {
      const schematic = await layoutCircuit(elk, circuit, {
        nodeVoltages: circuit === ledCircuit ? { VCC: 9, LED_A: 1.83 } : null,
      });
      expect(schematic.components).toHaveLength(circuit.components.length);
      expect(schematic.wires.length).toBeGreaterThan(0);
      const boxes = schematic.components.map((c) => ({ x: c.x, y: c.y, w: c.placed.width, h: c.placed.height }));
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i]!;
          const b = boxes[j]!;
          const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
          expect(overlap, `${circuit.title}: components ${i} and ${j} overlap`).toBe(false);
        }
      }
      if (outDir) {
        // Visual check: SCHEMATIC_OUT=<dir> npx vitest run toElk
        mkdirSync(outDir, { recursive: true });
        const svg = renderToStaticMarkup(
          <svg xmlns="http://www.w3.org/2000/svg" width={schematic.width} height={schematic.height} viewBox={`0 0 ${schematic.width} ${schematic.height}`}>
            <style>{SCHEMATIC_CSS}</style>
            <rect width="100%" height="100%" fill="white" />
            <SchematicContent schematic={schematic} />
          </svg>,
        );
        writeFileSync(join(outDir, `${circuit.title.replace(/\W+/g, "_")}.svg`), svg);
      }
    }
  });
});
