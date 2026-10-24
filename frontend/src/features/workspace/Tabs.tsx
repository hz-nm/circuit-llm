import { useRef, type KeyboardEvent } from "react";

export type TabId = "schematic" | "mermaid" | "netlist" | "simulation";

const TABS: readonly { id: TabId; label: string }[] = [
  { id: "schematic", label: "Schematic" },
  { id: "mermaid", label: "Mermaid" },
  { id: "netlist", label: "Netlist" },
  { id: "simulation", label: "Simulation" },
];

/** WAI-ARIA tabs: arrow keys / Home / End move between tabs. */
export function Tabs({ active, onChange, highlight = null }: { active: TabId; onChange: (tab: TabId) => void; highlight?: TabId | null }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const last = TABS.length - 1;
    const next =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    onChange(TABS[next]!.id);
    refs.current[next]?.focus();
  };

  return (
    <div role="tablist" aria-label="Workspace views" className="flex gap-1 border-b border-line bg-panel px-2">
      {TABS.map((tab, i) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            id={`tab-${tab.id}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={`panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-accent ${
              selected ? "border-accent font-medium text-ink" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {tab.label}
            {highlight === tab.id && (
              <>
                <span aria-hidden="true" className="ml-1.5 inline-block h-2 w-2 animate-pulse rounded-full bg-accent align-middle" />
                <span className="sr-only"> (new results)</span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}
