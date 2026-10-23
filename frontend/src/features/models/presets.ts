import type { EndpointIn, OutputMode, ProviderKind } from "../../api/types";

export interface ProviderPreset {
  id: string;
  name: string;
  provider: ProviderKind;
  baseUrl: string | null;
  /** Suggested model id (users can type any id their provider serves). */
  model: string;
  modelPlaceholder: string;
  needsKey: boolean;
  keyUrl?: string;
  note?: string;
}

export const PRESETS: readonly ProviderPreset[] = [
  {
    id: "anthropic",
    name: "Anthropic",
    provider: "anthropic",
    baseUrl: null,
    model: "claude-sonnet-5-5",
    modelPlaceholder: "claude-sonnet-5-5",
    needsKey: true,
    keyUrl: "https://console.anthropic.com/settings/keys",
  },
  {
    id: "openai",
    name: "OpenAI",
    provider: "openai_compatible",
    baseUrl: "https://api.openai.com/v1",
    model: "",
    modelPlaceholder: "e.g. gpt-4.1",
    needsKey: true,
    keyUrl: "https://platform.openai.com/api-keys",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    provider: "openrouter",
    baseUrl: null,
    model: "openai/gpt-oss-120b",
    modelPlaceholder: "vendor/model, e.g. openai/gpt-oss-120b",
    needsKey: true,
    keyUrl: "https://openrouter.ai/keys",
  },
  {
    id: "gemini",
    name: "Google Gemini",
    provider: "gemini",
    baseUrl: null,
    model: "",
    modelPlaceholder: "e.g. gemini-2.5-flash",
    needsKey: true,
    keyUrl: "https://aistudio.google.com/apikey",
  },
  {
    id: "nvidia",
    name: "NVIDIA NIM",
    provider: "openai_compatible",
    baseUrl: "https://integrate.api.nvidia.com/v1",
    model: "openai/gpt-oss-120b",
    modelPlaceholder: "e.g. openai/gpt-oss-120b",
    needsKey: true,
    keyUrl: "https://build.nvidia.com/",
    note: "NVIDIA's hosted endpoints speak the OpenAI API.",
  },
  {
    id: "ollama",
    name: "Ollama (local)",
    provider: "openai_compatible",
    baseUrl: "http://localhost:11434/v1",
    model: "",
    modelPlaceholder: "a pulled model, e.g. qwen2.5:14b",
    needsKey: false,
    note: "Runs on your machine; no key needed. Larger models follow the netlist format more reliably.",
  },
  {
    id: "lmstudio",
    name: "LM Studio (local)",
    provider: "openai_compatible",
    baseUrl: "http://localhost:1234/v1",
    model: "",
    modelPlaceholder: "the model id shown in LM Studio",
    needsKey: false,
    note: "Start LM Studio's local server first; no key needed.",
  },
];

export const PROVIDER_LABEL: Record<ProviderKind, string> = {
  anthropic: "Anthropic",
  openai_compatible: "OpenAI-compatible",
  openrouter: "OpenRouter",
  gemini: "Gemini",
};

export const OUTPUT_MODES: readonly { value: OutputMode; label: string; help: string }[] = [
  { value: "auto", label: "Auto (recommended)", help: "Uses the strictest mode the provider supports and falls back gracefully if it is rejected." },
  { value: "json_schema", label: "JSON schema", help: "The provider enforces the exact netlist schema. Most reliable when supported." },
  { value: "json_object", label: "JSON object", help: "The provider guarantees valid JSON, but not its shape." },
  { value: "text", label: "Plain text", help: "No constraints; the JSON is extracted from the reply. For models without JSON support." },
];

export function presetDefaults(preset: ProviderPreset): EndpointIn {
  return {
    label: preset.name,
    provider: preset.provider,
    model: preset.model,
    api_key: null,
    base_url: preset.baseUrl,
    output_mode: "auto",
    temperature: 0.2,
    max_output_tokens: 16384,
    timeout_s: 180,
    enabled: true,
  };
}
