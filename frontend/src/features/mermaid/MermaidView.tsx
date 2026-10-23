import { useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { useIsDark } from "../../ui/theme";

type Mermaid = typeof import("mermaid").default;
let mermaidPromise: Promise<Mermaid> | null = null;

/** Mermaid is large; load it the first time the tab is opened. */
function loadMermaid(): Promise<Mermaid> {
  mermaidPromise ??= import("mermaid").then((m) => m.default);
  return mermaidPromise;
}

let renderCount = 0;

/**
 * Mermaid 11 runs labels through a markdown parser, so an edge label such as
 * `"+"` or `"-"` (voltage-source pins) is read as a list item and rendered as
 * "Unsupported markdown: list". A zero-width space in front keeps it literal.
 */
export function protectLabels(source: string): string {
  return source.replace(/\|"([+\-*]|\d+\.)/g, '|"​$1');
}

async function renderDiagram(source: string, dark: boolean, baseId: string): Promise<string> {
  const mermaid = await loadMermaid();
  mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: dark ? "dark" : "default" });
  const id = `mmd-${baseId.replace(/[^a-zA-Z0-9]/g, "")}-${++renderCount}`;
  const { svg } = await mermaid.render(id, protectLabels(source));
  return svg;
}

export function MermaidView({ source }: { source: string }) {
  const dark = useIsDark();
  const baseId = useId();
  const diagram = useQuery({
    queryKey: ["mermaid", source, dark],
    queryFn: () => renderDiagram(source, dark, baseId),
    staleTime: Infinity,
    retry: false,
  });

  return (
    <div className="h-full overflow-auto p-4">
      <div className="rounded-lg border border-line bg-panel p-4">
        {diagram.isPending && <p className="text-sm text-muted">Rendering diagram…</p>}
        {diagram.isError && (
          <p className="text-sm text-danger">Mermaid could not render this diagram: {String(diagram.error)}</p>
        )}
        {diagram.data && (
          // The SVG comes from mermaid with securityLevel "strict" (sanitised labels, no scripts).
          <div className="mermaid-view flex justify-center" dangerouslySetInnerHTML={{ __html: diagram.data }} />
        )}
      </div>
      <details className="mt-4" open>
        <summary className="cursor-pointer text-xs font-medium text-muted">Mermaid source</summary>
        <pre className="mt-2 overflow-x-auto rounded-lg border border-line bg-sunken p-3 font-mono text-xs">{source}</pre>
      </details>
    </div>
  );
}
