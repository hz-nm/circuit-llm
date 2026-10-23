import type { TurnStep } from "./useDesignTurn";

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent align-[-2px]"
    />
  );
}

function StepLine({ step, current }: { step: TurnStep; current: boolean }) {
  switch (step.kind) {
    case "attempt":
      return (
        <li className="flex items-center gap-2">
          {current ? <Spinner /> : <span aria-hidden="true" className="w-3 text-center text-muted">·</span>}
          <span>
            Asking <strong>{step.label}</strong> <span className="text-muted">({step.model})</span>…
            {step.maxAttempts > 1 && (
              <span className="text-muted">
                {" "}
                attempt {step.attempt}/{step.maxAttempts}
              </span>
            )}
          </span>
        </li>
      );
    case "validation":
      return (
        <li>
          <details className="group">
            <summary className="cursor-pointer text-warn">
              The circuit had {step.problems.length} problem{step.problems.length === 1 ? "" : "s"}; asking the model
              to repair it
            </summary>
            <ul className="mt-1 list-disc space-y-0.5 pl-8 text-muted">
              {step.problems.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </details>
        </li>
      );
    case "endpoint_failed":
      return (
        <li className="text-warn">
          <strong>{step.label}</strong> failed: {step.error}. Falling back to the next model…
        </li>
      );
    case "completed":
      return <li className="text-ok">Design accepted. Saving…</li>;
    case "failed":
      return <li className="text-danger">{step.error}</li>;
  }
}

export function TurnProgress({ steps, running }: { steps: TurnStep[]; running: boolean }) {
  return (
    <div role="status" aria-live="polite" className="rounded-lg border border-line bg-sunken px-3 py-2 text-xs">
      {steps.length === 0 ? (
        <p className="flex items-center gap-2">
          <Spinner /> Starting…
        </p>
      ) : (
        <ol className="space-y-1">
          {steps.map((step, i) => (
            <StepLine key={i} step={step} current={running && i === steps.length - 1} />
          ))}
        </ol>
      )}
    </div>
  );
}
