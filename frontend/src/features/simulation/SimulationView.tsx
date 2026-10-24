import { useEffect, useMemo, useRef } from "react";
import { BenchChecks } from "./BenchChecks";
import { useSimulationSession } from "./session";

/** The last "show the checks" request already scrolled to (so tab revisits don't re-scroll). */
let handledRequest = 0;
import { SimulationResults, type PlotLinks } from "./SimulationResults";

/** Simulation tab: results of the selected version (runs are started from the run bar). */
export function SimulationView() {
  const { result, version, running, probes, cursor, driver, checks, nav, navigate, setPinned } = useSimulationSession();
  const checksRef = useRef<HTMLElement>(null);
  // Failed expectations have their own panel; Bench checks lists only rating problems.
  const ratingChecks = checks.filter((c) => c.code !== "expectation_failed");
  const expectationsRef = useRef<HTMLElement>(null);
  const expectations = result?.ok ? (result.expectations ?? []) : [];

  useEffect(() => {
    const target = nav?.focus === "checks" ? checksRef.current : nav?.focus === "expectations" ? expectationsRef.current : null;
    if (!nav || !target || nav.seq === handledRequest) return;
    handledRequest = nav.seq;
    target.scrollIntoView({ block: "start" });
    target.focus({ preventScroll: true });
  }, [nav, checks.length, expectations.length]);

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
        {expectations.length > 0 && (
          <section ref={expectationsRef} tabIndex={-1} aria-label="Expectations" className="rounded-lg border border-line bg-panel p-3 outline-none focus-visible:ring-2 focus-visible:ring-accent">
            <h3 className="mb-2 text-sm font-semibold">
              Expectations{" "}
              <span className="text-xs font-normal text-muted">
                {expectations.filter((e) => e.passed).length}/{expectations.length} met
              </span>
            </h3>
            <ul className="space-y-1.5 text-xs">
              {expectations.map((e, i) => (
                <li key={i} className="flex gap-2">
                  <span aria-label={e.passed ? "passed" : "failed"} className={`font-bold ${e.passed ? "text-ok" : "text-danger"}`}>
                    {e.passed ? "✓" : "✗"}
                  </span>
                  <span>
                    <strong>{e.description}</strong> <span className="text-muted">{e.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {ratingChecks.length > 0 && <BenchChecks ref={checksRef} checks={ratingChecks} onShow={showComponent} />}
        {result && <SimulationResults result={result} links={links} />}
      </div>
    </div>
  );
}
