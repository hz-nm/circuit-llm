import { errorMessage } from "../../api/client";
import { useRunSimulation, useSimulation } from "../../api/queries";
import type { SimulationResult, VersionOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { SimulationResults } from "./SimulationResults";

interface Props {
  projectId: string;
  version: VersionOut;
  available: boolean;
}

export function SimulationView({ projectId, version, available }: Props) {
  const cached = useSimulation(projectId, version.number);
  const run = useRunSimulation(projectId, version.number);
  const errors = version.issues.filter((i) => i.severity === "error");
  const analyses = version.circuit.analyses ?? [];
  const result: SimulationResult | null | undefined = cached.data;

  const blocked = !available
    ? "ngspice is not available on the server."
    : errors.length > 0
      ? `Fix the ${errors.length} ERC error${errors.length === 1 ? "" : "s"} first.`
      : analyses.length === 0
        ? "This circuit defines no analyses (op, dc, ac or tran). Ask for one in the chat or add it in the Netlist tab."
        : null;

  return (
    <div className="h-full overflow-y-auto">
      <div className="sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b border-line bg-panel/95 px-4 py-2 backdrop-blur">
        <Button variant="primary" size="sm" onClick={() => run.mutate()} disabled={blocked !== null || run.isPending}>
          {run.isPending ? "Simulating…" : result ? "Re-run simulation" : "Run simulation"}
        </Button>
        <span className="text-xs text-muted">
          {blocked ??
            (result
              ? `${result.ok ? "Result" : "Failed run"} for v${version.number}${result.duration_ms ? ` · ${result.duration_ms} ms` : ""}`
              : `Analyses: ${analyses.map((a) => a.type).join(", ")}`)}
        </span>
      </div>

      <div className="space-y-4 p-4">
        {run.isError && (
          <p role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-3 py-2 text-sm text-danger">
            {errorMessage(run.error)}
          </p>
        )}
        {cached.isPending && <p className="text-sm text-muted">Checking for a cached result…</p>}
        {cached.isError && <p className="text-sm text-danger">{errorMessage(cached.error)}</p>}
        {result === null && !run.isPending && (
          <p className="text-sm text-muted">This version has not been simulated yet.</p>
        )}
        {result && <SimulationResults result={result} />}
      </div>
    </div>
  );
}
