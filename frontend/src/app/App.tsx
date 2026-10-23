import { lazy, Suspense } from "react";
import { useHealth } from "../api/queries";
import { ProjectView } from "../features/project/ProjectView";
import { ProjectSidebar } from "../features/projects/ProjectSidebar";
import { ModelsSettings } from "../features/models/ModelsSettings";
import { Button } from "../ui/Button";
import { useTheme } from "../ui/theme";
import { useRoute } from "./route";

// Dev-only page (#/dev) that renders the mock circuits and results; compiled out of production builds.
const DevGallery = import.meta.env.DEV ? lazy(() => import("../dev/DevGallery")) : null;

const THEME_LABEL = { light: "Light", dark: "Dark", system: "System" } as const;

export function App() {
  const { route, navigate } = useRoute();
  const theme = useTheme();
  const health = useHealth();
  const ngspiceMissing = health.data !== undefined && !health.data.ngspice.available;
  const projectId = route.page === "project" ? route.projectId : null;

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line bg-panel px-3">
        <a href="#/" className="flex items-center gap-2 font-semibold tracking-tight">
          <svg viewBox="0 0 32 32" className="h-5 w-5" aria-hidden="true">
            <rect width="32" height="32" rx="7" className="fill-accent" />
            <path d="M4 16h6l2-5 4 10 4-10 2 5h6" fill="none" stroke="white" strokeWidth="2.4" strokeLinejoin="round" />
          </svg>
          circuits-llm
        </a>
        {health.data && <span className="text-xs text-muted">v{health.data.version}</span>}
        <div className="flex-1" />
        <Button size="sm" variant="ghost" onClick={theme.cycle} title="Switch theme (system → light → dark)">
          Theme: {THEME_LABEL[theme.choice]}
        </Button>
        <Button
          size="sm"
          variant={route.page === "settings" ? "primary" : "secondary"}
          onClick={() => navigate(route.page === "settings" ? { page: "home" } : { page: "settings" })}
        >
          Models
        </Button>
      </header>

      {ngspiceMissing && (
        <div role="status" className="border-b border-line bg-warn-soft px-4 py-1.5 text-xs text-warn">
          ngspice was not found, so simulation is disabled. Install ngspice or set{" "}
          <code className="font-mono">CIRCUITS_LLM_NGSPICE_PATH</code>, then restart the server.
        </div>
      )}
      {health.isError && (
        <div role="alert" className="border-b border-line bg-danger-soft px-4 py-1.5 text-xs text-danger">
          Cannot reach the circuits-llm server. Is it running?
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {route.page === "settings" ? (
          <ModelsSettings onClose={() => navigate({ page: "home" })} />
        ) : route.page === "dev" && DevGallery ? (
          <Suspense fallback={<p className="p-4 text-sm text-muted">Loading…</p>}>
            <DevGallery />
          </Suspense>
        ) : (
          <>
            <ProjectSidebar
              selectedId={projectId}
              onSelect={(id) => navigate({ page: "project", projectId: id, version: null })}
              onDeleted={(id) => id === projectId && navigate({ page: "home" }, true)}
            />
            {route.page === "project" ? (
              <ProjectView
                key={route.projectId}
                projectId={route.projectId}
                version={route.version}
                simulationAvailable={health.data?.ngspice.available ?? true}
                onSelectVersion={(n) => navigate({ page: "project", projectId: route.projectId, version: n })}
                onOpenSettings={() => navigate({ page: "settings" })}
              />
            ) : (
              <Welcome />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Welcome() {
  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md text-center">
        <h1 className="text-lg font-semibold">Design circuits by chatting</h1>
        <p className="mt-2 text-sm text-muted">
          Create a project in the sidebar and describe the circuit you want. The model drafts a netlist, the
          backend checks it, and ngspice simulates it.
        </p>
      </div>
    </main>
  );
}
