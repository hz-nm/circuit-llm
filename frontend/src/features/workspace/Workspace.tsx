import { useEffect, useState } from "react";
import { errorMessage } from "../../api/client";
import { useRestoreVersion, useVersion } from "../../api/queries";
import type { ProjectDetail, VersionOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { ErrorBoundary } from "../../ui/ErrorBoundary";
import { MermaidView } from "../mermaid/MermaidView";
import { NetlistEditor } from "../netlist/NetlistEditor";
import { SchematicView } from "../schematic/SchematicView";
import { RunBar } from "../simulation/RunBar";
import { SimulationSessionProvider, useSimulationSession } from "../simulation/session";
import { SimulationView } from "../simulation/SimulationView";
import { IssuesPanel } from "./IssuesPanel";
import { Tabs, type TabId } from "./Tabs";
import { VersionPicker } from "./VersionPicker";

interface Props {
  projectId: string;
  detail: ProjectDetail;
  selected: number | null;
  simulationAvailable: boolean;
  onSelectVersion: (n: number | null) => void;
}

export function Workspace({ projectId, detail, selected, simulationAvailable, onSelectVersion }: Props) {
  const [tab, setTab] = useState<TabId>("schematic");
  const version = useVersion(projectId, selected, detail);
  const restore = useRestoreVersion(projectId);
  const latestNumber = detail.latest?.number ?? null;

  if (selected === null) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-muted">
        <div>
          <p className="font-medium text-ink">No circuit yet</p>
          <p className="mt-1">Describe what you want in the chat, and the design will appear here.</p>
        </div>
      </div>
    );
  }

  const data = version.data;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-panel px-3 py-2">
        <VersionPicker versions={detail.versions} selected={selected} latest={latestNumber} onSelect={onSelectVersion} />
        {selected !== latestNumber && (
          <Button
            size="sm"
            onClick={() => restore.mutate(selected, { onSuccess: (v) => onSelectVersion(v.number) })}
            disabled={restore.isPending}
            title="Copy this version to a new latest version"
          >
            Restore as latest
          </Button>
        )}
        {restore.isError && <span className="text-xs text-danger">{errorMessage(restore.error)}</span>}
        <h2 className="min-w-0 flex-1 truncate text-sm font-medium" title={data?.circuit.title}>
          {data?.circuit.title}
        </h2>
        {data && <IssuesPanel issues={data.issues} />}
      </div>
      {version.isError && <p className="p-4 text-sm text-danger">{errorMessage(version.error)}</p>}
      {version.isPending && <p className="p-4 text-sm text-muted">Loading version {selected}…</p>}
      {data && (
        <SimulationSessionProvider key={`${projectId}:${data.number}`} projectId={projectId} version={data} available={simulationAvailable}>
          <RunBar />
          <WorkspaceTabs tab={tab} setTab={setTab} projectId={projectId} version={data} onSaved={(n) => onSelectVersion(n)} />
        </SimulationSessionProvider>
      )}
    </>
  );
}

/** Tabs + panel; after a run, results are surfaced without the user hunting for them. */
function WorkspaceTabs({
  tab,
  setTab,
  projectId,
  version,
  onSaved,
}: {
  tab: TabId;
  setTab: (tab: TabId) => void;
  projectId: string;
  version: VersionOut;
  onSaved: (n: number) => void;
}) {
  const { lastRun } = useSimulationSession();
  const [unseen, setUnseen] = useState(false);

  // A manual run from Mermaid/Netlist jumps to the plots; an auto-run only highlights the tab.
  // On the Schematic tab the live schematic lights up by itself.
  useEffect(() => {
    if (lastRun.count === 0) return;
    if (tab === "mermaid" || tab === "netlist") {
      if (lastRun.manual) setTab("simulation");
      else setUnseen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react to new runs only
  }, [lastRun]);

  const select = (next: TabId) => {
    if (next === "simulation") setUnseen(false);
    setTab(next);
  };

  return (
    <>
      <Tabs active={tab} onChange={select} highlight={unseen && tab !== "simulation" ? "simulation" : null} />
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="relative min-h-0 flex-1 overflow-hidden">
        <ErrorBoundary resetKey={`${tab}:${version.number}`} label="This view failed to render.">
          <TabContent tab={tab} projectId={projectId} version={version} onSaved={onSaved} />
        </ErrorBoundary>
      </div>
    </>
  );
}

function TabContent({
  tab,
  projectId,
  version,
  onSaved,
}: {
  tab: TabId;
  projectId: string;
  version: VersionOut;
  onSaved: (n: number) => void;
}) {
  switch (tab) {
    case "schematic":
      return <LiveSchematic version={version} />;
    case "mermaid":
      return <MermaidView source={version.mermaid} />;
    case "netlist":
      return <NetlistEditor key={version.number} projectId={projectId} version={version} onSaved={onSaved} />;
    case "simulation":
      return <SimulationView />;
  }
}

function LiveSchematic({ version }: { version: VersionOut }) {
  const session = useSimulationSession();
  return <SchematicView circuit={version.circuit} issues={version.issues} session={session} />;
}
