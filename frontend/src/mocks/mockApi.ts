/**
 * In-memory fake of the backend API for `npm run dev:mock`: lets the whole UI run
 * (including streamed design turns) without the server or any LLM. Dev-only.
 */
import type {
  Circuit,
  EndpointIn,
  EndpointOut,
  Issue,
  MessageRecord,
  ProjectRecord,
  SimulationResult,
  StreamEvent,
  VersionOut,
  VersionSummary,
} from "../api/types";
import {
  dcSweepResult,
  ledCircuit,
  ledOpResult,
  opampAmplifier,
  opampTranResult,
  rcAcResult,
  rcLowPass,
  transistorSwitch,
} from "./circuits";

interface MockProject {
  record: ProjectRecord;
  messages: MessageRecord[];
  versions: { summary: VersionSummary; circuit: Circuit }[];
  simulations: Map<number, SimulationResult>;
}

const now = () => new Date().toISOString();
const uid = () => Math.random().toString(16).slice(2, 14);
const sleep = (ms: number, signal?: AbortSignal | null) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });

const state = {
  models: [] as (EndpointOut & { key: string })[],
  projects: new Map<string, MockProject>(),
  messageId: 1,
};

function seed() {
  const id = "demo";
  const p: MockProject = {
    record: { id, title: ledCircuit.title, created_at: now(), updated_at: now(), latest_version: 1 },
    messages: [],
    versions: [{ summary: { number: 1, source: "llm", title: ledCircuit.title, created_at: now() }, circuit: ledCircuit }],
    simulations: new Map([[1, ledOpResult]]),
  };
  p.messages.push(
    { id: state.messageId++, role: "user", content: "A red LED from 9 V with a current-limiting resistor", version_number: null, meta: { error: false, warnings: [] }, created_at: now() },
    {
      id: state.messageId++,
      role: "assistant",
      content: "Here's a **red LED** driven from 9 V through **R1 = 470 Ω**:\n\n- LED forward voltage ≈ 1.8 V\n- Current ≈ (9 − 1.8) / 470 ≈ **15 mA**\n\nI added an operating-point analysis so you can check the node voltages.",
      version_number: 1,
      meta: { endpoint_id: "m1", model: "openai/gpt-oss-120b", error: false, warnings: [] },
      created_at: now(),
    },
  );
  state.projects.set(id, p);
  state.models.push({
    id: "m1",
    label: "NVIDIA NIM",
    provider: "openai_compatible",
    model: "openai/gpt-oss-120b",
    base_url: "https://integrate.api.nvidia.com/v1",
    effective_base_url: "https://integrate.api.nvidia.com/v1",
    output_mode: "auto",
    temperature: 0.2,
    max_output_tokens: 16384,
    timeout_s: 180,
    enabled: true,
    has_api_key: true,
    api_key_hint: "…k3Yz",
    key: "nvapi-mock-k3Yz",
  });
}

// ---------------------------------------------------------------------------- derived views

function issuesFor(circuit: Circuit): Issue[] {
  const issues: Issue[] = [];
  const nets = new Map<string, number>();
  for (const c of circuit.components) for (const n of Object.values(c.pins)) nets.set(n, (nets.get(n) ?? 0) + 1);
  if (!nets.has("GND")) issues.push({ severity: "error", code: "no_ground", message: "The circuit has no GND reference node." });
  for (const [net, count] of nets) {
    if (count < 2 && net !== "GND") issues.push({ severity: "warning", code: "dangling_net", message: `Net ${net} connects to only one pin.`, net });
  }
  return issues;
}

function mermaidFor(circuit: Circuit): string {
  const lines = ["flowchart LR"];
  for (const c of circuit.components) lines.push(`    C_${c.id}["<b>${c.id}</b><br/>${c.kind}"]`);
  const nets = new Set(circuit.components.flatMap((c) => Object.values(c.pins)));
  for (const n of nets) lines.push(`    N_${n}((${n === "GND" ? "⏚ GND" : n}))`);
  for (const c of circuit.components) for (const [pin, net] of Object.entries(c.pins)) lines.push(`    C_${c.id} ---|"${pin}"| N_${net}`);
  return lines.join("\n");
}

function versionOut(p: MockProject, n: number): VersionOut | null {
  const v = p.versions.find((x) => x.summary.number === n);
  if (!v) return null;
  return { number: n, source: v.summary.source, created_at: v.summary.created_at, circuit: v.circuit, issues: issuesFor(v.circuit), mermaid: mermaidFor(v.circuit) };
}

function addVersion(p: MockProject, circuit: Circuit, source: VersionSummary["source"]): VersionOut {
  const number = p.versions.length + 1;
  p.versions.push({ summary: { number, source, title: circuit.title, created_at: now() }, circuit });
  p.record = { ...p.record, latest_version: number, updated_at: now() };
  return versionOut(p, number)!;
}

function simulate(circuit: Circuit): SimulationResult {
  if (circuit.title === rcLowPass.title) return rcAcResult;
  if (circuit.title === opampAmplifier.title) return opampTranResult;
  if (circuit.title === transistorSwitch.title) return dcSweepResult;
  return ledOpResult;
}

// ---------------------------------------------------------------------------- design turns

function pickCircuit(text: string): Circuit {
  const t = text.toLowerCase();
  if (/filter|rc|low.?pass|bode/.test(t)) return rcLowPass;
  if (/op.?amp|amplifier|gain/.test(t)) return opampAmplifier;
  if (/transistor|switch|npn|relay/.test(t)) return transistorSwitch;
  return ledCircuit;
}

function sseResponse(projectId: string, content: string, signal: AbortSignal | null | undefined): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: StreamEvent) => controller.enqueue(encoder.encode(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`));
      try {
        const p = state.projects.get(projectId)!;
        const userMessage: MessageRecord = { id: state.messageId++, role: "user", content, version_number: null, meta: { error: false, warnings: [] }, created_at: now() };
        p.messages.push(userMessage);
        const enabled = state.models.filter((m) => m.enabled);
        const first = enabled[0];
        if (!first) {
          send({ type: "failed", error: "No enabled model endpoints are configured." });
          return;
        }
        controller.enqueue(encoder.encode(": keep-alive\n\n"));
        send({ type: "attempt_started", endpoint_id: first.id, endpoint_label: first.label, model: first.model, attempt: 1, max_attempts: 3 });
        await sleep(1200, signal);
        if (/fail|broken/.test(content.toLowerCase())) {
          send({ type: "endpoint_failed", endpoint_id: first.id, error: "HTTP 429: rate limited" });
          await sleep(400, signal);
          send({ type: "failed", error: "Every model endpoint failed. Check the Models settings." });
          const message: MessageRecord = { id: state.messageId++, role: "assistant", content: "Every model endpoint failed. Check the Models settings.", version_number: null, meta: { error: true, warnings: [] }, created_at: now() };
          p.messages.push(message);
          send({ type: "saved", user_message: userMessage, assistant_message: message, version: null });
          return;
        }
        send({
          type: "validation_failed",
          endpoint_id: first.id,
          attempt: 1,
          problems: ["Component D1: unknown pin 'k2'; valid pins are anode, cathode.", "Net LED_A connects to only one pin."],
        });
        await sleep(300, signal);
        send({ type: "attempt_started", endpoint_id: first.id, endpoint_label: first.label, model: first.model, attempt: 2, max_attempts: 3 });
        await sleep(1200, signal);
        const circuit = pickCircuit(content);
        const reply = `I designed **${circuit.title}**.\n\n${circuit.description}\n\n| Part | Value |\n|---|---|\n${circuit.components
          .map((c) => `| ${c.id} | ${c.value ?? c.model ?? "—"} |`)
          .join("\n")}`;
        const warnings: Issue[] = [{ severity: "warning", code: "mock", message: "This reply came from the mock API (no LLM was called)." }];
        send({ type: "completed", reply, circuit, warnings, endpoint_id: first.id, model: first.model });
        await sleep(200, signal);
        const version = addVersion(p, circuit, "llm");
        p.simulations.set(version.number, simulate(circuit));
        if (p.record.title === "Untitled circuit") p.record = { ...p.record, title: circuit.title };
        const message: MessageRecord = { id: state.messageId++, role: "assistant", content: reply, version_number: version.number, meta: { endpoint_id: first.id, model: first.model, error: false, warnings }, created_at: now() };
        p.messages.push(message);
        send({ type: "saved", user_message: userMessage, assistant_message: message, version });
      } catch {
        // aborted: just end the stream
      } finally {
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      }
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

// ---------------------------------------------------------------------------- routing

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const notFound = () => json({ detail: "not found" }, 404);

function endpointOut(m: EndpointOut & { key: string }): EndpointOut {
  const { key, ...rest } = m;
  return { ...rest, has_api_key: key.length > 0, api_key_hint: key.length >= 8 ? `…${key.slice(-4)}` : null };
}

async function handle(method: string, path: string, body: unknown, signal: AbortSignal | null | undefined): Promise<Response> {
  await sleep(120);
  const seg = path.split("/").filter(Boolean).slice(1); // drop "api"

  if (seg[0] === "health") return json({ version: "0.1.0-mock", ngspice: { available: true, path: null } });

  if (seg[0] === "models") {
    if (seg.length === 1 && method === "GET") return json(state.models.map(endpointOut));
    if (seg.length === 1 && method === "POST") {
      const b = body as EndpointIn;
      const m = { ...b, id: uid(), base_url: b.base_url ?? null, effective_base_url: b.base_url ?? "(provider default)", output_mode: b.output_mode ?? "auto", temperature: b.temperature ?? 0.2, max_output_tokens: b.max_output_tokens ?? 16384, timeout_s: b.timeout_s ?? 180, enabled: b.enabled ?? true, has_api_key: false, api_key_hint: null, key: b.api_key ?? "" };
      state.models.push(m);
      return json(endpointOut(m), 201);
    }
    if (seg[1] === "order" && method === "PUT") {
      const ids = (body as { ids: string[] }).ids;
      state.models.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
      return json(state.models.map(endpointOut));
    }
    const i = state.models.findIndex((m) => m.id === seg[1]);
    if (i < 0) return notFound();
    const current = state.models[i]!;
    if (seg[2] === "test") return json({ ok: true, latency_ms: 420, message: "mock endpoint replied" });
    if (method === "PUT") {
      const b = body as EndpointIn;
      const key = b.api_key === null || b.api_key === undefined ? current.key : b.api_key;
      state.models[i] = { ...current, ...b, base_url: b.base_url ?? null, effective_base_url: b.base_url ?? current.effective_base_url, key, has_api_key: false, api_key_hint: null } as EndpointOut & { key: string };
      return json(endpointOut(state.models[i]!));
    }
    if (method === "DELETE") {
      state.models.splice(i, 1);
      return new Response(null, { status: 204 });
    }
  }

  if (seg[0] === "projects") {
    if (seg.length === 1 && method === "GET") return json([...state.projects.values()].map((p) => p.record).reverse());
    if (seg.length === 1 && method === "POST") {
      const id = uid();
      const title = (body as { title?: string } | null)?.title ?? "Untitled circuit";
      const record: ProjectRecord = { id, title, created_at: now(), updated_at: now(), latest_version: null };
      state.projects.set(id, { record, messages: [], versions: [], simulations: new Map() });
      return json(record, 201);
    }
    const p = state.projects.get(seg[1] ?? "");
    if (!p) return notFound();
    if (seg.length === 2) {
      if (method === "GET") {
        const latest = p.versions.length ? versionOut(p, p.versions.length) : null;
        return json({ project: p.record, messages: p.messages, versions: p.versions.map((v) => v.summary), latest });
      }
      if (method === "PATCH") {
        p.record = { ...p.record, title: (body as { title: string }).title, updated_at: now() };
        return json(p.record);
      }
      if (method === "DELETE") {
        state.projects.delete(p.record.id);
        return new Response(null, { status: 204 });
      }
    }
    if (seg[2] === "messages" && method === "POST") return sseResponse(p.record.id, (body as { content: string }).content, signal);
    if (seg[2] === "circuit" && method === "PUT") {
      const circuit = (body as { circuit: Circuit }).circuit;
      if (!Array.isArray(circuit.components) || circuit.components.length === 0) {
        return json({ detail: [{ loc: ["body", "circuit", "components"], msg: "List should have at least 1 item after validation", type: "too_short" }] }, 422);
      }
      return json(addVersion(p, circuit, "manual"), 201);
    }
    if (seg[2] === "versions") {
      const n = Number(seg[3]);
      const v = versionOut(p, n);
      if (!v) return notFound();
      if (seg.length === 4) return json(v);
      if (seg[4] === "restore") return json(addVersion(p, v.circuit, "restore"), 201);
      if (seg[4] === "simulation") {
        const r = p.simulations.get(n);
        return r ? json(r) : json({ detail: "this version has not been simulated yet" }, 404);
      }
      if (seg[4] === "simulate") {
        await sleep(600);
        const r = simulate(v.circuit);
        p.simulations.set(n, r);
        return json(r);
      }
      if (seg[4] === "spice") return new Response(simulate(v.circuit).netlist, { headers: { "Content-Type": "text/plain" } });
    }
  }
  return notFound();
}

export function installMockApi(): void {
  seed();
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request ? request.url : String(input), window.location.origin);
    if (!url.pathname.startsWith("/api/")) return realFetch(input, init);
    const method = (init?.method ?? request?.method ?? "GET").toUpperCase();
    const rawBody = init?.body ?? (request && method !== "GET" ? await request.clone().text() : null);
    const body: unknown = typeof rawBody === "string" && rawBody ? JSON.parse(rawBody) : null;
    return handle(method, url.pathname, body, init?.signal ?? request?.signal);
  };
  console.info("[mock] circuits-llm mock API installed (no backend, no LLM).");
}
