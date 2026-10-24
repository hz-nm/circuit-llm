import { useEffect, useMemo, useRef } from "react";
import { BenchChecks } from "./BenchChecks";
import { useSimulationSession } from "./session";

/** The last "show the checks" request already scrolled to (so tab revisits don't re-scroll). */
let handledChecksRequest = 0;
import { SimulationResults, type PlotLinks } from "./SimulationResults";

/** Simulation tab: results of the selected version (runs are started from the run bar). */
export function SimulationView() {
  const { result, version, running, probes, cursor, driver, checks, nav, navigate, setPinned } = useSimulationSession();
  const checksRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (nav?.focus !== "checks" || nav.seq === handledChecksRequest || !checksRef.current) return;
    handledChecksRequest = nav.seq;
    checksRef.current.scrollIntoView({ block: "start" });
    checksRef.current.focus({ preventScroll: true });
  }, [nav, checks.length]);

  const showComponent = (id: string) => {
    setPinned((list) => (list.includes(id) ? list : [...list, id]));
    navigate("schematic");
  };
  const analyses = version.circuit.analyses ?? [];
  const links = useMemo<PlotLinks>(
    () => ({
      showsTrace: probes.showsTrace,
      toggleNet: probes.toggle,
      cursor,
      driver,
      components: probes.components,
      togglePlot: probes.togglePlot,
      circuit: version.circuit,
    }),
    [probes, cursor, driver, version.circuit],
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="space-y-4 p-4">
        {result === undefined && <p className="text-sm text-muted">Checking for a cached result…</p>}
        {result === null && (
          <p className="text-sm text-muted">
            {running
              ? "Simulating…"
              : analyses.length > 0
                ? `This version has not been simulated yet. Press ▶ Run (F5) to run ${analyses.map((a) => a.type).join(", ")}.`
                : "This circuit defines no analyses. Set a stop time in the run bar to run a transient, or add analyses in the Netlist tab."}
          </p>
        )}
        {checks.length > 0 && <BenchChecks ref={checksRef} checks={checks} onShow={showComponent} />}
        {result && <SimulationResults result={result} links={links} />}
      </div>
    </div>
  );
}
