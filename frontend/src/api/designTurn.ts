import { toApiError } from "./client";
import { readSse } from "./sse";
import type { StreamEvent, StreamEventType } from "./types";

const EVENT_TYPES: ReadonlySet<string> = new Set<StreamEventType>([
  "planned",
  "attempt_started",
  "validation_failed",
  "endpoint_failed",
  "completed",
  "failed",
  "saved",
]);

/** Parse one SSE `data:` payload into a StreamEvent, or return null if it isn't one. */
export function parseStreamEvent(data: string): StreamEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null || !("type" in value)) return null;
  const type = (value as { type: unknown }).type;
  if (typeof type !== "string" || !EVENT_TYPES.has(type)) return null;
  // The server is the source of these payloads and they are generated from the same schema.
  return value as StreamEvent;
}

/**
 * Start a design turn (`POST /api/projects/{id}/messages`) and yield its stream events.
 * Abort via `signal`; an aborted fetch rejects with a DOMException named "AbortError".
 */
export async function* streamDesignTurn(
  projectId: string,
  content: string,
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw toApiError(response.status, body);
  }
  if (!response.body) throw new Error("The server returned an empty stream.");

  for await (const message of readSse(response.body)) {
    const event = parseStreamEvent(message.data);
    if (event) yield event;
  }
}
