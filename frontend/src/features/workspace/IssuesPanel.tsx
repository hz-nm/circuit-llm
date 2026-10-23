import { useState } from "react";
import type { Issue } from "../../api/types";

/** Compact ERC summary chip that expands into the full list of issues. */
export function IssuesPanel({ issues }: { issues: Issue[] }) {
  const [open, setOpen] = useState(false);
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");

  if (issues.length === 0) {
    return <span className="rounded-full bg-sunken px-2 py-0.5 text-xs text-ok">ERC clean</span>;
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="erc-issues"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs hover:bg-sunken focus-visible:outline-2 focus-visible:outline-accent"
      >
        {errors.length > 0 && <span className="font-medium text-danger">{errors.length} error{errors.length === 1 ? "" : "s"}</span>}
        {warnings.length > 0 && <span className="font-medium text-warn">{warnings.length} warning{warnings.length === 1 ? "" : "s"}</span>}
        <span aria-hidden="true" className="text-muted">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <ul
          id="erc-issues"
          className="absolute right-0 top-8 z-20 max-h-80 w-[28rem] max-w-[80vw] space-y-1 overflow-y-auto rounded-lg border border-line bg-panel p-2 text-xs shadow-lg"
        >
          {[...errors, ...warnings].map((issue, i) => (
            <li
              key={i}
              className={`rounded-md px-2 py-1.5 ${issue.severity === "error" ? "bg-danger-soft" : "bg-warn-soft"}`}
            >
              <span className={`font-semibold ${issue.severity === "error" ? "text-danger" : "text-warn"}`}>
                {issue.severity === "error" ? "Error" : "Warning"}
              </span>
              {(issue.component_id || issue.net) && (
                <span className="ml-1 font-mono text-muted">
                  [{[issue.component_id, issue.net && `net ${issue.net}`].filter(Boolean).join(", ")}]
                </span>
              )}
              <p className="mt-0.5">{issue.message}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
