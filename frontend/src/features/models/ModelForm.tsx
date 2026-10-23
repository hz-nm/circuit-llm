import { useId, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, errorMessage } from "../../api/client";
import { useSaveModel } from "../../api/queries";
import type { EndpointIn, EndpointOut, ProviderKind } from "../../api/types";
import { Button } from "../../ui/Button";
import { OUTPUT_MODES, PRESETS, PROVIDER_LABEL, presetDefaults } from "./presets";

interface Props {
  /** The endpoint being edited, or null to create one. */
  existing: EndpointOut | null;
  onDone: () => void;
}

function fromExisting(e: EndpointOut): EndpointIn {
  return {
    label: e.label,
    provider: e.provider,
    model: e.model,
    api_key: null,
    base_url: e.base_url,
    output_mode: e.output_mode,
    temperature: e.temperature,
    max_output_tokens: e.max_output_tokens,
    timeout_s: e.timeout_s,
    enabled: e.enabled,
  };
}

const inputClass = "w-full rounded-md border border-line bg-bg px-2 py-1.5 text-sm outline-none focus:border-accent";

function Field({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

export function ModelForm({ existing, onDone }: Props) {
  const id = useId();
  const [presetId, setPresetId] = useState(existing ? "" : PRESETS[0]!.id);
  const [form, setForm] = useState<EndpointIn>(() => (existing ? fromExisting(existing) : presetDefaults(PRESETS[0]!)));
  const [keyInput, setKeyInput] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const save = useSaveModel();
  const preset = PRESETS.find((p) => p.id === presetId);

  const set = <K extends keyof EndpointIn>(key: K, value: EndpointIn[K]) => setForm((f) => ({ ...f, [key]: value }));

  const choosePreset = (next: string) => {
    setPresetId(next);
    const p = PRESETS.find((x) => x.id === next);
    if (p) setForm((f) => ({ ...presetDefaults(p), enabled: f.enabled }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    // Write-only key: blank keeps the stored key (null), "clear" sends "".
    const api_key = clearKey ? "" : keyInput.trim() || null;
    const body: EndpointIn = { ...form, api_key, base_url: form.base_url?.trim() || null };
    save.mutate({ id: existing?.id ?? null, body }, { onSuccess: onDone });
  };

  const problems = save.error instanceof ApiError ? save.error.problems : [];
  const outputHelp = OUTPUT_MODES.find((m) => m.value === form.output_mode)?.help;

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-panel p-4">
      <h3 className="text-sm font-semibold">{existing ? `Edit ${existing.label}` : "Add a model"}</h3>

      {!existing && (
        <fieldset>
          <legend className="mb-1 text-xs font-medium">Provider preset</legend>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <label
                key={p.id}
                className={`cursor-pointer rounded-full border px-2.5 py-1 text-xs has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
                  presetId === p.id ? "border-accent bg-accent-soft text-ink" : "border-line text-muted hover:text-ink"
                }`}
              >
                <input type="radio" name={`${id}-preset`} value={p.id} checked={presetId === p.id} onChange={() => choosePreset(p.id)} className="sr-only" />
                {p.name}
              </label>
            ))}
          </div>
          {preset?.note && <p className="mt-1 text-[11px] text-muted">{preset.note}</p>}
        </fieldset>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Label" htmlFor={`${id}-label`}>
          <input id={`${id}-label`} required maxLength={80} value={form.label} onChange={(e) => set("label", e.target.value)} className={inputClass} />
        </Field>
        <Field label="Provider API" htmlFor={`${id}-provider`}>
          <select id={`${id}-provider`} value={form.provider} onChange={(e) => set("provider", e.target.value as ProviderKind)} className={inputClass}>
            {(Object.keys(PROVIDER_LABEL) as ProviderKind[]).map((p) => (
              <option key={p} value={p}>
                {PROVIDER_LABEL[p]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Model" htmlFor={`${id}-model`}>
          <input
            id={`${id}-model`}
            required
            maxLength={200}
            value={form.model}
            placeholder={preset?.modelPlaceholder}
            onChange={(e) => set("model", e.target.value)}
            className={`${inputClass} font-mono`}
          />
        </Field>
        <Field
          label="Base URL"
          htmlFor={`${id}-base`}
          hint={existing ? `Effective: ${existing.effective_base_url}` : "Leave blank for the provider's default."}
        >
          <input
            id={`${id}-base`}
            type="url"
            maxLength={500}
            value={form.base_url ?? ""}
            placeholder="provider default"
            onChange={(e) => set("base_url", e.target.value)}
            className={`${inputClass} font-mono`}
          />
        </Field>
      </div>

      <Field
        label="API key"
        htmlFor={`${id}-key`}
        hint={
          existing?.has_api_key ? (
            <>
              A key is stored{existing.api_key_hint ? ` (ending ${existing.api_key_hint})` : ""}. Leave blank to keep it.
            </>
          ) : preset && !preset.needsKey ? (
            "Not needed for local servers."
          ) : preset?.keyUrl ? (
            <>
              Get one at <span className="font-mono">{preset.keyUrl}</span>. Keys stay in your local database and are never shown again.
            </>
          ) : (
            "Stored locally and never shown again."
          )
        }
      >
        <div className="flex items-center gap-2">
          <input
            id={`${id}-key`}
            type="password"
            autoComplete="off"
            maxLength={500}
            value={keyInput}
            disabled={clearKey}
            placeholder={existing?.has_api_key ? "•••••••• (unchanged)" : ""}
            onChange={(e) => setKeyInput(e.target.value)}
            className={`${inputClass} font-mono`}
          />
          {existing?.has_api_key && (
            <label className="flex shrink-0 items-center gap-1 text-xs">
              <input type="checkbox" checked={clearKey} onChange={(e) => setClearKey(e.target.checked)} />
              Clear stored key
            </label>
          )}
        </div>
      </Field>

      <details className="rounded-md border border-line px-3 py-2">
        <summary className="cursor-pointer text-xs font-medium">Advanced</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field label="Output mode" htmlFor={`${id}-mode`} hint={outputHelp}>
            <select id={`${id}-mode`} value={form.output_mode} onChange={(e) => set("output_mode", e.target.value as EndpointIn["output_mode"])} className={inputClass}>
              {OUTPUT_MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Temperature" htmlFor={`${id}-temp`} hint="0 to 2. Low values give more consistent netlists.">
            <input id={`${id}-temp`} type="number" min={0} max={2} step={0.1} value={form.temperature} onChange={(e) => set("temperature", Number(e.target.value))} className={inputClass} />
          </Field>
          <Field label="Max output tokens" htmlFor={`${id}-tokens`}>
            <input id={`${id}-tokens`} type="number" min={256} max={65536} step={256} value={form.max_output_tokens} onChange={(e) => set("max_output_tokens", Number(e.target.value))} className={inputClass} />
          </Field>
          <Field label="Timeout (seconds)" htmlFor={`${id}-timeout`}>
            <input id={`${id}-timeout`} type="number" min={1} max={600} value={form.timeout_s} onChange={(e) => set("timeout_s", Number(e.target.value))} className={inputClass} />
          </Field>
        </div>
      </details>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.enabled ?? true} onChange={(e) => set("enabled", e.target.checked)} />
        Enabled (used in the fallback chain)
      </label>

      {save.isError && (
        <div role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-xs text-danger">
          <p>{errorMessage(save.error)}</p>
          {problems.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {problems.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : existing ? "Save changes" : "Add model"}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
