import { Button } from "../../ui/Button";

/** Shown instead of the chat when no model is configured (or all are disabled). */
export function Onboarding({ onOpenSettings, hasDisabledModels }: { onOpenSettings: () => void; hasDisabledModels: boolean }) {
  return (
    <div className="flex flex-1 flex-col justify-center p-6 text-sm">
      <h2 className="text-base font-semibold">Connect a model to start designing</h2>
      {hasDisabledModels ? (
        <p className="mt-2 text-muted">All your models are disabled. Enable at least one in the Models settings.</p>
      ) : (
        <>
          <p className="mt-2 text-muted">
            circuits-llm works with any model you have access to. Your keys stay on this machine.
          </p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-muted">
            <li>
              <strong className="text-ink">Hosted:</strong> Anthropic, OpenAI, OpenRouter, Google Gemini or NVIDIA NIM (paste an API key).
            </li>
            <li>
              <strong className="text-ink">Local:</strong> Ollama or LM Studio (no key; just a running server).
            </li>
            <li>Add several to build a fallback chain: if one fails, the next takes over.</li>
          </ul>
        </>
      )}
      <div className="mt-4">
        <Button variant="primary" onClick={onOpenSettings}>
          {hasDisabledModels ? "Open Models settings" : "Add a model"}
        </Button>
      </div>
      <p className="mt-6 text-xs text-muted">
        Meanwhile you can still browse, hand-edit and simulate existing versions in the workspace.
      </p>
    </div>
  );
}
