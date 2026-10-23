import { useState } from "react";
import { MOCK_CIRCUITS, dcSweepResult, failedResult, ledCircuit, ledOpResult, opampTranResult, rcAcResult } from "../mocks/circuits";
import { SchematicView } from "../features/schematic/SchematicView";
import { SimulationResults } from "../features/simulation/SimulationResults";

/** Dev-only visual check of every mock circuit and simulation result (open #/dev in `npm run dev`). */
export default function DevGallery() {
  const [index, setIndex] = useState(0);
  const circuit = MOCK_CIRCUITS[index]!;
  const op = ledOpResult.analyses?.[0];
  const voltages = circuit === ledCircuit && op?.type === "op" ? op.node_voltages : null;

  return (
    <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
      <div className="flex flex-wrap gap-1 border-b border-line bg-panel p-2">
        {MOCK_CIRCUITS.map((c, i) => (
          <button
            key={c.title}
            type="button"
            onClick={() => setIndex(i)}
            className={`rounded-md px-2 py-1 text-xs ${i === index ? "bg-accent text-accent-ink" : "hover:bg-sunken"}`}
          >
            {c.title}
          </button>
        ))}
      </div>
      <div className="h-[520px] shrink-0 border-b border-line">
        <SchematicView circuit={circuit} nodeVoltages={voltages} />
      </div>
      <div className="space-y-4 p-4">
        {[ledOpResult, rcAcResult, opampTranResult, dcSweepResult, failedResult].map((r, i) => (
          <SimulationResults key={i} result={r} />
        ))}
      </div>
    </main>
  );
}
