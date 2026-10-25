import { useState } from "react";
import { Button } from "../../ui/Button";

/** Generated Arduino sketches (one per board) with Copy and "Download .ino". */
export function SketchSection({ sketches }: { sketches: Record<string, string> }) {
  const [status, setStatus] = useState<string | null>(null);
  const entries = Object.entries(sketches);
  if (entries.length === 0) return null;

  const copy = async (id: string, code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setStatus(`Copied ${id}.ino`);
    } catch {
      setStatus("Copy failed");
    }
  };
  const download = (id: string, code: string) => {
    const url = URL.createObjectURL(new Blob([code], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${id}.ino`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <details open className="max-h-[45%] shrink-0 overflow-y-auto border-t border-line bg-panel">
      <summary className="cursor-pointer px-3 py-1.5 text-xs font-semibold">
        Sketch{entries.length > 1 ? "es" : ""} <span className="font-normal text-muted">(generated Arduino code)</span>
        {status && <span className="ml-2 font-normal text-ok">{status}</span>}
      </summary>
      {entries.map(([id, code]) => (
        <section key={id} aria-label={`Sketch for ${id}`} className="px-3 pb-3">
          <div className="mb-1 flex items-center gap-2">
            <span className="font-mono text-xs font-semibold">{id}.ino</span>
            <div className="flex-1" />
            <Button size="sm" onClick={() => void copy(id, code)}>
              Copy
            </Button>
            <Button size="sm" onClick={() => download(id, code)}>
              Download .ino
            </Button>
          </div>
          <pre className="overflow-x-auto rounded-md border border-line bg-sunken p-2 font-mono text-xs leading-relaxed">{code}</pre>
        </section>
      ))}
    </details>
  );
}
