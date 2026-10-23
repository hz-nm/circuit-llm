import { useMemo, useState } from "react";
import { ApiError, errorMessage } from "../../api/client";
import { useSaveCircuit } from "../../api/queries";
import type { Circuit, VersionOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { SpiceActions } from "./SpiceActions";

interface Props {
  projectId: string;
  version: VersionOut;
  onSaved: (n: number) => void;
}

const pretty = (circuit: Circuit) => JSON.stringify(circuit, null, 2);

function parseCircuit(text: string): { circuit: Circuit | null; error: string | null } {
  try {
    const value: unknown = JSON.parse(text);
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return { circuit: null, error: "The netlist must be a JSON object." };
    }
    // Full validation happens on the server (it reports every problem at once).
    return { circuit: value as Circuit, error: null };
  } catch (e) {
    return { circuit: null, error: errorMessage(e) };
  }
}

export function NetlistEditor({ projectId, version, onSaved }: Props) {
  const original = useMemo(() => pretty(version.circuit), [version.circuit]);
  const [text, setText] = useState(original);
  const save = useSaveCircuit(projectId);
  const dirty = text !== original;
  const parsed = useMemo(() => parseCircuit(text), [text]);

  const onSave = () => {
    if (!parsed.circuit) return;
    save.mutate(parsed.circuit, { onSuccess: (v) => onSaved(v.number) });
  };

  const serverError = save.error instanceof ApiError ? save.error : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <Button variant="primary" size="sm" onClick={onSave} disabled={!dirty || !parsed.circuit || save.isPending}>
          {save.isPending ? "Saving…" : "Save as new version"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setText(original)} disabled={!dirty}>
          Revert
        </Button>
        <span className="text-xs text-muted">
          {dirty ? "Unsaved changes" : `Editing a copy of v${version.number}`}
        </span>
        <div className="flex-1" />
        <SpiceActions projectId={projectId} versionNumber={version.number} />
      </div>

      {(parsed.error || save.isError) && (
        <div role="alert" className="border-b border-line bg-danger-soft px-3 py-2 text-xs text-danger">
          {parsed.error ? (
            <p>Invalid JSON: {parsed.error}</p>
          ) : (
            <>
              <p className="font-medium">{errorMessage(save.error)}</p>
              {serverError && serverError.problems.length > 0 && (
                <ul className="mt-1 list-disc space-y-0.5 pl-5 font-mono">
                  {serverError.problems.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}

      <label htmlFor="netlist-json" className="sr-only">
        Circuit netlist (JSON)
      </label>
      <textarea
        id="netlist-json"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          // Tab inserts two spaces; Escape then Tab leaves the editor (keyboard users aren't trapped).
          if (e.key === "Tab" && !e.shiftKey && !e.altKey && e.currentTarget.dataset.escaped !== "1") {
            e.preventDefault();
            const el = e.currentTarget;
            const { selectionStart: s, selectionEnd: end } = el;
            setText(text.slice(0, s) + "  " + text.slice(end));
            requestAnimationFrame(() => el.setSelectionRange(s + 2, s + 2));
          }
          e.currentTarget.dataset.escaped = e.key === "Escape" ? "1" : "0";
          if ((e.ctrlKey || e.metaKey) && e.key === "s") {
            e.preventDefault();
            if (dirty && parsed.circuit) onSave();
          }
        }}
        spellCheck={false}
        className="min-h-0 flex-1 resize-none bg-sunken p-3 font-mono text-xs leading-relaxed outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
      />
      <p className="border-t border-line px-3 py-1 text-[11px] text-muted">
        Tab indents · Esc then Tab leaves the editor · Ctrl+S saves. Saved versions are checked by the ERC; errors appear in
        the issues panel.
      </p>
    </div>
  );
}
