import { forwardRef } from "react";
import type { Issue } from "../../api/types";

interface Props {
  checks: Issue[];
  /** Show the part on the schematic with its meter pinned. */
  onShow: (componentId: string) => void;
}

/** Post-simulation rating checks: errors (a real part would fail) first, then advisory warnings. */
export const BenchChecks = forwardRef<HTMLElement, Props>(function BenchChecks({ checks, onShow }, ref) {
  const errors = checks.filter((c) => c.severity === "error").length;
  return (
    <section
      ref={ref}
      tabIndex={-1}
      aria-label="Bench checks"
      className={`rounded-lg border p-3 outline-none focus-visible:ring-2 focus-visible:ring-accent ${
        errors > 0 ? "border-danger/40 bg-danger-soft/50" : "border-warn/40 bg-warn-soft/50"
      }`}
    >
      <h3 className="text-sm font-semibold">
        Bench checks{" "}
        <span className={`text-xs font-normal ${errors > 0 ? "text-danger" : "text-warn"}`}>
          {errors > 0 ? `${errors} rating problem${errors === 1 ? "" : "s"}` : "advisory"}
          {checks.length - errors > 0 && ` · ${checks.length - errors} warning${checks.length - errors === 1 ? "" : "s"}`}
        </span>
      </h3>
      <p className="mb-2 text-xs text-muted">Component ratings checked against the simulated currents, voltages and power.</p>
      <ul className="space-y-1">
        {checks.map((check, i) => {
          const error = check.severity === "error";
          const content = (
            <>
              <span className={`mr-1.5 font-semibold ${error ? "text-danger" : "text-warn"}`}>{error ? "Error" : "Warning"}</span>
              {check.component_id && <span className="mr-1.5 font-mono font-semibold">{check.component_id}</span>}
              <span>{check.message}</span>
            </>
          );
          return (
            <li key={i}>
              {check.component_id ? (
                <button
                  type="button"
                  onClick={() => onShow(check.component_id!)}
                  title={`Show ${check.component_id} on the schematic with its meter pinned`}
                  className="w-full rounded-md bg-panel px-2 py-1.5 text-left text-xs hover:bg-sunken focus-visible:outline-2 focus-visible:outline-accent"
                >
                  {content}
                </button>
              ) : (
                <div className="rounded-md bg-panel px-2 py-1.5 text-xs">{content}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
});
