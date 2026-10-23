import { useState, type FormEvent } from "react";
import { errorMessage } from "../../api/client";
import { useCreateProject, useDeleteProject, useProjects, useRenameProject } from "../../api/queries";
import type { ProjectRecord } from "../../api/types";
import { Button } from "../../ui/Button";

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDeleted: (id: string) => void;
}

export function ProjectSidebar({ selectedId, onSelect, onDeleted }: Props) {
  const projects = useProjects();
  const create = useCreateProject();

  const onCreate = () => create.mutate(undefined, { onSuccess: (project) => onSelect(project.id) });

  return (
    <nav aria-label="Projects" className="flex w-60 shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex items-center justify-between px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Projects</h2>
        <Button size="sm" variant="primary" onClick={onCreate} disabled={create.isPending}>
          + New
        </Button>
      </div>
      {create.isError && <p className="px-3 text-xs text-danger">{errorMessage(create.error)}</p>}
      <ul className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {projects.isPending && <li className="px-2 py-1 text-xs text-muted">Loading…</li>}
        {projects.isError && <li className="px-2 py-1 text-xs text-danger">{errorMessage(projects.error)}</li>}
        {projects.data?.length === 0 && (
          <li className="px-2 py-1 text-xs text-muted">No projects yet. Create one to start designing.</li>
        )}
        {projects.data?.map((project) => (
          <ProjectItem
            key={project.id}
            project={project}
            selected={project.id === selectedId}
            onSelect={() => onSelect(project.id)}
            onDeleted={() => onDeleted(project.id)}
          />
        ))}
      </ul>
    </nav>
  );
}

function ProjectItem({
  project,
  selected,
  onSelect,
  onDeleted,
}: {
  project: ProjectRecord;
  selected: boolean;
  onSelect: () => void;
  onDeleted: () => void;
}) {
  const [mode, setMode] = useState<"view" | "rename" | "confirm-delete">("view");
  const [title, setTitle] = useState(project.title);
  const rename = useRenameProject();
  const remove = useDeleteProject();

  const submitRename = (event: FormEvent) => {
    event.preventDefault();
    const next = title.trim();
    if (!next || next === project.title) {
      setMode("view");
      return;
    }
    rename.mutate({ id: project.id, title: next }, { onSuccess: () => setMode("view") });
  };

  if (mode === "rename") {
    return (
      <li className="px-1 py-0.5">
        <form onSubmit={submitRename} className="flex gap-1">
          <label className="sr-only" htmlFor={`rename-${project.id}`}>
            Project title
          </label>
          <input
            id={`rename-${project.id}`}
            autoFocus
            value={title}
            maxLength={120}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setMode("view")}
            className="min-w-0 flex-1 rounded border border-line bg-bg px-1.5 py-0.5 text-sm"
          />
          <Button size="sm" type="submit" variant="primary" disabled={rename.isPending}>
            Save
          </Button>
        </form>
        {rename.isError && <p className="text-xs text-danger">{errorMessage(rename.error)}</p>}
      </li>
    );
  }

  if (mode === "confirm-delete") {
    return (
      <li className="rounded-md bg-danger-soft px-2 py-1.5 text-xs">
        <p>
          Delete <strong>{project.title}</strong> and all its versions?
        </p>
        <div className="mt-1.5 flex gap-1">
          <Button
            size="sm"
            variant="danger"
            autoFocus
            disabled={remove.isPending}
            onClick={() => remove.mutate(project.id, { onSuccess: onDeleted })}
          >
            Delete
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setMode("view")}>
            Cancel
          </Button>
        </div>
      </li>
    );
  }

  return (
    <li className="group relative">
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected ? "page" : undefined}
        className={`w-full rounded-md px-2 py-1.5 pr-14 text-left text-sm focus-visible:outline-2 focus-visible:outline-accent ${
          selected ? "bg-accent-soft font-medium text-ink" : "hover:bg-sunken"
        }`}
      >
        <span className="block truncate">{project.title}</span>
        <span className="block text-[11px] text-muted">
          {project.latest_version ? `v${project.latest_version} · ` : ""}
          {new Date(project.updated_at).toLocaleDateString()}
        </span>
      </button>
      <div className="absolute right-1 top-1.5 hidden gap-0.5 group-focus-within:flex group-hover:flex">
        <IconButton
          label={`Rename ${project.title}`}
          onClick={() => {
            setTitle(project.title);
            setMode("rename");
          }}
        >
          ✎
        </IconButton>
        <IconButton label={`Delete ${project.title}`} onClick={() => setMode("confirm-delete")}>
          ✕
        </IconButton>
      </div>
    </li>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-6 w-6 items-center justify-center rounded text-xs text-muted hover:bg-panel hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
    >
      {children}
    </button>
  );
}
