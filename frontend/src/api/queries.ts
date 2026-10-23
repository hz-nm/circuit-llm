import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, unwrapOrNull } from "./client";
import type { Circuit, EndpointIn, ProjectDetail, SimulationResult, VersionOut } from "./types";

export const keys = {
  health: ["health"] as const,
  models: ["models"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  version: (id: string, n: number) => ["project", id, "version", n] as const,
  simulation: (id: string, n: number) => ["project", id, "simulation", n] as const,
};

// --------------------------------------------------------------------------- system

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: () => unwrap(api.GET("/api/health")),
    staleTime: 60_000,
    retry: 1,
  });
}

// --------------------------------------------------------------------------- models

export function useModels() {
  return useQuery({ queryKey: keys.models, queryFn: () => unwrap(api.GET("/api/models")) });
}

export function useSaveModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string | null; body: EndpointIn }) =>
      id
        ? unwrap(api.PUT("/api/models/{endpoint_id}", { params: { path: { endpoint_id: id } }, body }))
        : unwrap(api.POST("/api/models", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.models }),
  });
}

export function useDeleteModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/models/{endpoint_id}", { params: { path: { endpoint_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.models }),
  });
}

export function useReorderModels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => unwrap(api.PUT("/api/models/order", { body: { ids } })),
    onSuccess: (models) => qc.setQueryData(keys.models, models),
  });
}

export function useTestModel() {
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/models/{endpoint_id}/test", { params: { path: { endpoint_id: id } } })),
  });
}

// --------------------------------------------------------------------------- projects

export function useProjects() {
  return useQuery({ queryKey: keys.projects, queryFn: () => unwrap(api.GET("/api/projects")) });
}

export function useProject(id: string | null) {
  return useQuery({
    queryKey: keys.project(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}", { params: { path: { project_id: id! } } })),
    enabled: id !== null,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) =>
      unwrap(api.POST("/api/projects", { body: { title: title ?? "Untitled circuit" } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  });
}

export function useRenameProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      unwrap(api.PATCH("/api/projects/{project_id}", { params: { path: { project_id: id } }, body: { title } })),
    onSuccess: (_record, { id }) => {
      void qc.invalidateQueries({ queryKey: keys.projects });
      void qc.invalidateQueries({ queryKey: keys.project(id) });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/projects/{project_id}", { params: { path: { project_id: id } } })),
    onSuccess: (_void, id) => {
      qc.removeQueries({ queryKey: keys.project(id) });
      void qc.invalidateQueries({ queryKey: keys.projects });
    },
  });
}

/** Refresh everything derived from a project after it changed on the server. */
export function useRefreshProject() {
  const qc = useQueryClient();
  return (id: string) =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.project(id), exact: true }),
      qc.invalidateQueries({ queryKey: keys.projects }),
    ]);
}

// --------------------------------------------------------------------------- versions

/**
 * The version to display. Uses the project's `latest` when it matches, so the
 * common case needs no extra request.
 */
export function useVersion(projectId: string | null, number: number | null, detail: ProjectDetail | undefined) {
  const latest = detail?.latest ?? undefined;
  const isLatest = latest !== undefined && latest.number === number;
  return useQuery({
    queryKey: keys.version(projectId ?? "", number ?? 0),
    queryFn: () =>
      unwrap(
        api.GET("/api/projects/{project_id}/versions/{number}", {
          params: { path: { project_id: projectId!, number: number! } },
        }),
      ),
    enabled: projectId !== null && number !== null && !isLatest,
    initialData: isLatest ? latest : undefined,
    staleTime: Infinity, // versions are immutable
  });
}

function rememberVersion(qc: ReturnType<typeof useQueryClient>, projectId: string, version: VersionOut) {
  qc.setQueryData(keys.version(projectId, version.number), version);
  void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true });
  void qc.invalidateQueries({ queryKey: keys.projects });
}

export function useSaveCircuit(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (circuit: Circuit) =>
      unwrap(
        api.PUT("/api/projects/{project_id}/circuit", {
          params: { path: { project_id: projectId } },
          body: { circuit },
        }),
      ),
    onSuccess: (version) => rememberVersion(qc, projectId, version),
  });
}

export function useRestoreVersion(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (number: number) =>
      unwrap(
        api.POST("/api/projects/{project_id}/versions/{number}/restore", {
          params: { path: { project_id: projectId, number } },
        }),
      ),
    onSuccess: (version) => rememberVersion(qc, projectId, version),
  });
}

// --------------------------------------------------------------------------- simulation

export function useSimulation(projectId: string, number: number) {
  return useQuery({
    queryKey: keys.simulation(projectId, number),
    queryFn: () =>
      unwrapOrNull(
        api.GET("/api/projects/{project_id}/versions/{number}/simulation", {
          params: { path: { project_id: projectId, number } },
        }),
      ),
    staleTime: Infinity,
  });
}

export function useRunSimulation(projectId: string, number: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/projects/{project_id}/versions/{number}/simulate", {
          params: { path: { project_id: projectId, number } },
        }),
      ),
    onSuccess: (result: SimulationResult) => qc.setQueryData(keys.simulation(projectId, number), result),
  });
}
