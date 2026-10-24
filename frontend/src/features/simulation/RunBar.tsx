import { useEffect, useId, useState } from "react";
import type { SimulationResult } from "../../api/types";
import { formatEng, parseEng } from "../../lib/si";
import { Button } from "../../ui/Button";
import { useSimulationSession, type RunOptions, type RunStatus } from "./session";

function statusText(status: RunStatus, cached: SimulationResult | null | undefined): { text: string; tone: "muted" | "ok" | "danger" | "warn" } {
  switch (status.kind) {
    case "ready":
      if (cached?.ok) return { text: `Cached result (${cached.duration_ms} ms) ✓`, tone: "ok" };
      if (cached) return { text: `Cached run failed: ${cached.error ?? "simulator error"}`, tone: "danger" };
      return { text: "Ready", tone: "muted" };
    case "running":
      return { text: "Running…", tone: "muted" };
    case "done":
      return { text: `Done in ${status.ms} ms ✓`, tone: "ok" };
    case "failed":
      return { text: `Failed: ${status.reason}`, tone: "danger" };
    case "stopped":
      return { text: "Stopped", tone: "warn" };
    case "blocked":
      return { text: status.reason, tone: "warn" };
  }
}

const TONE = { muted: "text-muted", ok: "text-ok", danger: "text-danger", warn: "text-warn" } as const;

/** Simulink-style toolbar: Run/Stop, transient stop time and step overrides, auto-run, status. */
export function RunBar() {
  const session = useSimulationSession();
  const { version, status, running, run, stop, autoRun, setAutoRun, checks, navigate } = session;
  // Failed expectations are also error checks; the expectations chip covers them, so skip them here.
  const ratingChecks = checks.filter((c) => c.code !== "expectation_failed");
  const ratingErrors = ratingChecks.filter((c) => c.severity === "error").length;
  const ratingWarnings = ratingChecks.length - ratingErrors;
  const settled = status.kind === "done" || status.kind === "ready";
  const showChecks = settled && ratingChecks.length > 0;
  const expectations = session.result?.ok ? (session.result.expectations ?? []) : [];
  const passed = expectations.filter((e) => e.passed).length;
  const id = useId();

  const tran = (version.circuit.analyses ?? []).find((a) => a.type === "tran");
  const [stopText, setStopText] = useState(tran ? formatEng(tran.stop_time) : "");
  const [stepText, setStepText] = useState(tran?.step_time ? formatEng(tran.step_time) : "");

  const stopTime = stopText.trim() ? parseEng(stopText) : null;
  const stepTime = stepText.trim() ? parseEng(stepText) : null;
  const stopInvalid = stopText.trim() !== "" && (stopTime === null || stopTime <= 0);
  const stepInvalid = stepText.trim() !== "" && (stepTime === null || stepTime <= 0);

  // Only send overrides that differ from the circuit's own transient settings.
  const options = (): RunOptions => {
    const o: RunOptions = {};
    if (stopTime !== null && stopTime !== tran?.stop_time) o.stop_time = stopTime;
    if (stepTime !== null && stepTime !== tran?.step_time) o.step_time = stepTime;
    if (o.step_time !== undefined && o.stop_time === undefined && tran) o.stop_time = tran.stop_time;
    return o;
  };
  const canRun = !running && !stopInvalid && !stepInvalid;
  const onRun = () => canRun && run(options(), true);

  // F5 or Ctrl/Cmd+Enter runs (only those keys are intercepted). Ctrl+Enter is left to text areas.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const inTextArea = event.target instanceof HTMLTextAreaElement;
      const isRun = event.key === "F5" || (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !inTextArea);
      if (!isRun) return;
      event.preventDefault();
      document.getElementById(`${id}-run`)?.click();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [id]);

  const { text, tone } = statusText(status, session.result);
  const inputClass = (invalid: boolean) =>
    `w-20 rounded-md border bg-bg px-2 py-1 font-mono text-xs outline-none focus:border-accent ${invalid ? "border-danger" : "border-line"}`;

  return (
    <div role="toolbar" aria-label="Simulation" className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-sunken px-3 py-1.5">
      {running ? (
        <Button size="sm" variant="danger" onClick={stop} title="Abort the running simulation">
          ■ Stop
        </Button>
      ) : (
        <Button id={`${id}-run`} size="sm" variant="primary" onClick={onRun} disabled={!canRun} title="Run simulation (F5 or Ctrl+Enter)">
          ▶ Run
        </Button>
      )}
      <label className="flex items-center gap-1.5 text-xs text-muted" htmlFor={`${id}-stop`}>
        Stop time
        <input
          id={`${id}-stop`}
          value={stopText}
          onChange={(e) => setStopText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onRun()}
          placeholder={tran ? "" : "circuit's"}
          aria-invalid={stopInvalid}
          title="Transient stop time, e.g. 5m or 10u (seconds). Empty uses the circuit's."
          className={inputClass(stopInvalid)}
        />
      </label>
      <label className="flex items-center gap-1.5 text-xs text-muted" htmlFor={`${id}-step`}>
        Step
        <input
          id={`${id}-step`}
          value={stepText}
          onChange={(e) => setStepText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onRun()}
          placeholder="auto"
          aria-invalid={stepInvalid}
          title="Transient time step, e.g. 10u. Empty uses the circuit's (or automatic)."
          className={inputClass(stepInvalid)}
        />
      </label>
      <label className="flex items-center gap-1.5 text-xs text-muted">
        <input type="checkbox" checked={autoRun} onChange={(e) => setAutoRun(e.target.checked)} />
        Auto-run
      </label>
      <span role="status" aria-live="polite" className={`min-w-0 flex-1 truncate text-right text-xs ${TONE[tone]}`} title={text}>
        {stopInvalid || stepInvalid ? <span className="text-danger">Use a time like 5m or 10u</span> : text}
      </span>
      {settled && expectations.length > 0 && (
        <button
          type="button"
          onClick={() => navigate("simulation", "expectations")}
          title="Show the expectations in the Simulation tab"
          className={`shrink-0 rounded-full px-2 py-0.5 font-mono text-xs font-medium focus-visible:outline-2 focus-visible:outline-accent ${
            passed === expectations.length ? "text-ok hover:bg-sunken" : "bg-danger-soft text-danger hover:brightness-95"
          }`}
        >
          {passed === expectations.length ? "✓" : "✗"} {passed}/{expectations.length}
        </button>
      )}
      {showChecks && (
        <button
          type="button"
          onClick={() => navigate("simulation", "checks")}
          title="Show the bench checks in the Simulation tab"
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs focus-visible:outline-2 focus-visible:outline-accent ${
            ratingErrors > 0 ? "bg-danger-soft font-medium text-danger hover:brightness-95" : "text-warn hover:bg-warn-soft"
          }`}
        >
          {ratingErrors > 0
            ? `⚠ ${ratingErrors} rating problem${ratingErrors === 1 ? "" : "s"}${ratingWarnings ? ` · ${ratingWarnings} warning${ratingWarnings === 1 ? "" : "s"}` : ""}`
            : `${ratingWarnings} rating note${ratingWarnings === 1 ? "" : "s"}`}
        </button>
      )}
    </div>
  );
}
