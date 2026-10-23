import { errorMessage } from "../../api/client";
import { useModels, useProject } from "../../api/queries";
import { ChatPanel } from "../chat/ChatPanel";
import { Onboarding } from "../models/Onboarding";
import { Workspace } from "../workspace/Workspace";

interface Props {
  projectId: string;
  /** Version picked by the user; null means "the latest". */
  version: number | null;
  simulationAvailable: boolean;
  onSelectVersion: (n: number | null) => void;
  onOpenSettings: () => void;
}

export function ProjectView({ projectId, version, simulationAvailable, onSelectVersion, onOpenSettings }: Props) {
  const project = useProject(projectId);
  const models = useModels();
  const hasModels = (models.data ?? []).some((m) => m.enabled);

  if (project.isError) {
    return (
      <main className="flex-1 p-6 text-sm">
        <p className="text-danger">Could not load this project: {errorMessage(project.error)}</p>
      </main>
    );
  }
  const detail = project.data;
  const selected = version ?? detail?.latest?.number ?? null;

  return (
    <div className="flex min-w-0 flex-1">
      <section aria-label="Chat" className="flex w-[400px] shrink-0 flex-col border-r border-line bg-panel">
        {models.isSuccess && !hasModels ? (
          <Onboarding onOpenSettings={onOpenSettings} hasDisabledModels={(models.data ?? []).length > 0} />
        ) : (
          <ChatPanel
            projectId={projectId}
            messages={detail?.messages ?? []}
            loading={project.isPending}
            selectedVersion={selected}
            onOpenVersion={onSelectVersion}
          />
        )}
      </section>
      <main className="flex min-w-0 flex-1 flex-col">
        {detail ? (
          <Workspace
            projectId={projectId}
            detail={detail}
            selected={selected}
            simulationAvailable={simulationAvailable}
            onSelectVersion={onSelectVersion}
          />
        ) : (
          <p className="p-6 text-sm text-muted">Loading project…</p>
        )}
      </main>
    </div>
  );
}
