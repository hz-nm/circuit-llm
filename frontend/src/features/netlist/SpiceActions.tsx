import { useState } from "react";
import { errorMessage, toApiError } from "../../api/client";
import { Button } from "../../ui/Button";

async function fetchSpice(projectId: string, versionNumber: number): Promise<string> {
  // text/plain response, so plain fetch is simpler than the JSON client here.
  const response = await fetch(
    `/api/projects/${encodeURIComponent(projectId)}/versions/${versionNumber}/spice`,
  );
  if (!response.ok) throw toApiError(response.status, await response.json().catch(() => null));
  return response.text();
}

/** "Copy SPICE" and "Download .cir" for the version's ngspice deck. */
export function SpiceActions({ projectId, versionNumber }: { projectId: string; versionNumber: number }) {
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: (deck: string) => Promise<void> | void, done: string) => {
    setBusy(true);
    setStatus(null);
    try {
      await action(await fetchSpice(projectId, versionNumber));
      setStatus(done);
    } catch (e) {
      setStatus(`Failed: ${errorMessage(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const copy = () => run((deck) => navigator.clipboard.writeText(deck), "Copied");
  const download = () =>
    run((deck) => {
      const url = URL.createObjectURL(new Blob([deck], { type: "text/plain" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `circuit-v${versionNumber}.cir`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "Downloaded");

  return (
    <div className="flex items-center gap-1.5">
      {status && (
        <span role="status" className={`text-xs ${status.startsWith("Failed") ? "text-danger" : "text-ok"}`}>
          {status}
        </span>
      )}
      <Button size="sm" onClick={copy} disabled={busy} title="Copy the ngspice deck for this version">
        Copy SPICE
      </Button>
      <Button size="sm" onClick={download} disabled={busy} title="Download the ngspice deck (.cir)">
        Download .cir
      </Button>
    </div>
  );
}
