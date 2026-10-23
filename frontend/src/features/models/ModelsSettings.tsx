import { useState } from "react";
import { errorMessage } from "../../api/client";
import { useDeleteModel, useModels, useReorderModels, useSaveModel, useTestModel } from "../../api/queries";
import type { EndpointOut, EndpointTestResult } from "../../api/types";
import { Button } from "../../ui/Button";
import { ModelForm } from "./ModelForm";
import { OUTPUT_MODES, PROVIDER_LABEL } from "./presets";

type Editing = { mode: "none" } | { mode: "new" } | { mode: "edit"; endpoint: EndpointOut };

export function ModelsSettings({ onClose }: { onClose: () => void }) {
  const models = useModels();
  const reorder = useReorderModels();
  const [editing, setEditing] = useState<Editing>({ mode: "none" });
  const list = models.data ?? [];

  const move = (index: number, delta: -1 | 1) => {
    const ids = list.map((m) => m.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target]!, ids[index]!];
    reorder.mutate(ids);
  };

  return (
    <main className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        <div className="flex items-center gap-3">
          <h1 className="flex-1 text-lg font-semibold">Models</h1>
          <Button onClick={onClose}>Back to projects</Button>
        </div>
        <p className="text-sm text-muted">
          Each design request tries the enabled models <strong>top to bottom</strong>. If a model errors or keeps
          producing invalid circuits, the next one takes over. API keys are stored only in your local database and are
          never sent back to the browser.
        </p>

        {models.isError && <p className="text-sm text-danger">{errorMessage(models.error)}</p>}
        {reorder.isError && <p className="text-sm text-danger">{errorMessage(reorder.error)}</p>}

        <ol className="space-y-2" aria-label="Fallback chain">
          {list.map((model, i) =>
            editing.mode === "edit" && editing.endpoint.id === model.id ? (
              <li key={model.id}>
                <ModelForm existing={model} onDone={() => setEditing({ mode: "none" })} />
              </li>
            ) : (
              <ModelRow
                key={model.id}
                model={model}
                position={i + 1}
                isFirst={i === 0}
                isLast={i === list.length - 1}
                reordering={reorder.isPending}
                onMove={(d) => move(i, d)}
                onEdit={() => setEditing({ mode: "edit", endpoint: model })}
              />
            ),
          )}
        </ol>
        {models.isSuccess && list.length === 0 && editing.mode !== "new" && (
          <p className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">No models yet. Add one to start designing.</p>
        )}

        {editing.mode === "new" ? (
          <ModelForm existing={null} onDone={() => setEditing({ mode: "none" })} />
        ) : (
          <Button variant="primary" onClick={() => setEditing({ mode: "new" })}>
            + Add model
          </Button>
        )}

        <section className="rounded-lg border border-line bg-panel p-4 text-xs text-muted">
          <h2 className="mb-1 text-sm font-semibold text-ink">Output modes</h2>
          <dl className="space-y-1">
            {OUTPUT_MODES.map((m) => (
              <div key={m.value}>
                <dt className="inline font-medium text-ink">{m.label}: </dt>
                <dd className="inline">{m.help}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </main>
  );
}

function ModelRow({
  model,
  position,
  isFirst,
  isLast,
  reordering,
  onMove,
  onEdit,
}: {
  model: EndpointOut;
  position: number;
  isFirst: boolean;
  isLast: boolean;
  reordering: boolean;
  onMove: (delta: -1 | 1) => void;
  onEdit: () => void;
}) {
  const save = useSaveModel();
  const remove = useDeleteModel();
  const test = useTestModel();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const result: EndpointTestResult | undefined = test.data;

  const toggleEnabled = () =>
    save.mutate({
      id: model.id,
      body: {
        label: model.label,
        provider: model.provider,
        model: model.model,
        api_key: null, // keep the stored key
        base_url: model.base_url,
        output_mode: model.output_mode,
        temperature: model.temperature,
        max_output_tokens: model.max_output_tokens,
        timeout_s: model.timeout_s,
        enabled: !model.enabled,
      },
    });

  return (
    <li className={`rounded-lg border border-line bg-panel p-3 ${model.enabled ? "" : "opacity-70"}`}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-sunken text-xs font-semibold" aria-label={`Position ${position}`}>
          {position}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {model.label} {!model.enabled && <span className="text-xs font-normal text-muted">(disabled)</span>}
          </p>
          <p className="truncate text-xs text-muted">
            {PROVIDER_LABEL[model.provider]} · <span className="font-mono">{model.model}</span> · {model.effective_base_url}
            {" · "}
            {model.has_api_key ? `key ${model.api_key_hint ?? "set"}` : "no key"}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" aria-label={`Move ${model.label} up`} disabled={isFirst || reordering} onClick={() => onMove(-1)}>
            ↑
          </Button>
          <Button size="sm" variant="ghost" aria-label={`Move ${model.label} down`} disabled={isLast || reordering} onClick={() => onMove(1)}>
            ↓
          </Button>
          <label className="mx-1 flex items-center gap-1 text-xs">
            <input type="checkbox" checked={model.enabled} disabled={save.isPending} onChange={toggleEnabled} />
            Enabled
          </label>
          <Button size="sm" onClick={() => test.mutate(model.id)} disabled={test.isPending}>
            {test.isPending ? "Testing…" : "Test"}
          </Button>
          <Button size="sm" onClick={onEdit}>
            Edit
          </Button>
          {confirmDelete ? (
            <>
              <Button size="sm" variant="danger" autoFocus disabled={remove.isPending} onClick={() => remove.mutate(model.id)}>
                Confirm delete
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <Button size="sm" variant="danger" onClick={() => setConfirmDelete(true)}>
              Delete
            </Button>
          )}
        </div>
      </div>
      {(result || test.isError || save.isError || remove.isError) && (
        <p role="status" className={`mt-2 text-xs ${result?.ok ? "text-ok" : "text-danger"}`}>
          {result
            ? `${result.ok ? "✓ Works" : "✗ Failed"} (${result.latency_ms} ms): ${result.message}`
            : errorMessage(test.error ?? save.error ?? remove.error)}
        </p>
      )}
    </li>
  );
}
