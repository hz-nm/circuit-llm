import { useState } from "react";
import { errorMessage } from "../../api/client";
import { useRestoreVersion, useSimulation, useVersion } from "../../api/queries";
import type { ProjectDetail, VersionOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { ErrorBoundary } from "../../ui/ErrorBoundary";
import { MermaidView } from "../mermaid/MermaidView";
import { NetlistEditor } from "../netlist/NetlistEditor";
import { SchematicView } from "../schematic/SchematicView";
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
      <Tabs active={tab} onChange={setTab} />
      <div
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        className="relative min-h-0 flex-1 overflow-hidden"
      >
        <ErrorBoundary resetKey={`${tab}:${selected}`} label="This view failed to render.">
          {version.isError && <p className="p-4 text-sm text-danger">{errorMessage(version.error)}</p>}
          {version.isPending && <p className="p-4 text-sm text-muted">Loading version {selected}…</p>}
          {data && (
            <TabContent
              tab={tab}
              projectId={projectId}
              version={data}
              simulationAvailable={simulationAvailable}
              onSaved={(n) => onSelectVersion(n)}
            />
          )}
        </ErrorBoundary>
      </div>
    </>
  );
}

function TabContent({
  tab,
  projectId,
  version,
  simulationAvailable,
  onSaved,
}: {
  tab: TabId;
  projectId: string;
  version: VersionOut;
  simulationAvailable: boolean;
  onSaved: (n: number) => void;
}) {
  const simulation = useSimulation(projectId, version.number);
  const op = simulation.data?.ok ? simulation.data.analyses?.find((a) => a.type === "op") : undefined;
  const nodeVoltages = op && op.type === "op" ? op.node_voltages : null;

  switch (tab) {
    case "schematic":
      return <SchematicView circuit={version.circuit} nodeVoltages={nodeVoltages} issues={version.issues} />;
    case "mermaid":
      return <MermaidView source={version.mermaid} />;
    case "netlist":
      return <NetlistEditor key={version.number} projectId={projectId} version={version} onSaved={onSaved} />;
    case "simulation":
      return <SimulationView projectId={projectId} version={version} available={simulationAvailable} />;
  }
}
