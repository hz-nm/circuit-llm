import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "../../api/client";
import { streamDesignTurn } from "../../api/designTurn";
import { keys } from "../../api/queries";
import type { Issue, ProjectDetail, StreamEvent, TurnSaved } from "../../api/types";

/** One line of live progress shown while a design turn runs. */
export type TurnStep =
  | { kind: "attempt"; label: string; model: string; attempt: number; maxAttempts: number }
  | { kind: "planned"; families: string[]; plan: string; fallback: boolean }
  | { kind: "validation"; attempt: number; problems: string[] }
  | { kind: "endpoint_failed"; label: string; error: string }
  | { kind: "completed"; model: string; warnings: Issue[] }
  | { kind: "failed"; error: string };

export interface TurnState {
  running: boolean;
  /** The user's message while the turn is in flight (before the server echoes it back). */
  pendingContent: string | null;
  steps: TurnStep[];
  error: string | null;
}

const IDLE: TurnState = { running: false, pendingContent: null, steps: [], error: null };

/** Fold a stream event into the progress list (pure, so it is easy to reason about). */
export function applyEvent(steps: TurnStep[], event: StreamEvent, labels: Map<string, string>): TurnStep[] {
  switch (event.type) {
    case "planned":
      return [...steps, { kind: "planned", families: event.families, plan: event.plan, fallback: event.fallback }];
    case "attempt_started":
      labels.set(event.endpoint_id, event.endpoint_label);
      return [
        ...steps,
        { kind: "attempt", label: event.endpoint_label, model: event.model, attempt: event.attempt, maxAttempts: event.max_attempts },
      ];
    case "validation_failed":
      return [...steps, { kind: "validation", attempt: event.attempt, problems: event.problems }];
    case "endpoint_failed":
      return [...steps, { kind: "endpoint_failed", label: labels.get(event.endpoint_id) ?? event.endpoint_id, error: event.error }];
    case "completed":
      return [...steps, { kind: "completed", model: event.model, warnings: event.warnings ?? [] }];
    case "failed":
      return [...steps, { kind: "failed", error: event.error }];
    case "saved":
      return steps;
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Run chat turns against the SSE endpoint, exposing live progress and an abort handle. */
export function useDesignTurn(projectId: string, onSaved: (saved: TurnSaved) => void) {
  const qc = useQueryClient();
  const [state, setState] = useState<TurnState>(IDLE);
  const controller = useRef<AbortController | null>(null);

  // Abort an in-flight turn if the panel unmounts (e.g. the user switches project).
  useEffect(() => () => controller.current?.abort(), []);

  const applySaved = useCallback(
    (saved: TurnSaved) => {
      // Show the persisted messages immediately, then refetch for the authoritative state.
      qc.setQueryData<ProjectDetail>(keys.project(projectId), (detail) => {
        if (!detail) return detail;
        const version = saved.version;
        return {
          ...detail,
          messages: [...detail.messages, saved.user_message, saved.assistant_message],
          latest: version ?? detail.latest,
          versions: version
            ? [...detail.versions, { number: version.number, source: "llm", title: version.circuit.title, created_at: version.created_at }]
            : detail.versions,
        };
      });
      if (saved.version) qc.setQueryData(keys.version(projectId, saved.version.number), saved.version);
      void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true });
      void qc.invalidateQueries({ queryKey: keys.projects });
    },
    [qc, projectId],
  );

  const send = useCallback(
    async (content: string) => {
      if (controller.current) return;
      const abort = new AbortController();
      controller.current = abort;
      setState({ running: true, pendingContent: content, steps: [], error: null });
      const labels = new Map<string, string>();
      let saved: TurnSaved | null = null;
      try {
        for await (const event of streamDesignTurn(projectId, content, abort.signal)) {
          if (event.type === "saved") saved = event;
          else setState((s) => ({ ...s, steps: applyEvent(s.steps, event, labels) }));
        }
        if (saved) {
          applySaved(saved);
          setState(IDLE);
          onSaved(saved);
        } else if (abort.signal.aborted) {
          setState(IDLE);
          void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true });
        } else {
          // The refetch below brings back the stored user message, so drop the optimistic copy.
          setState((s) => ({ ...s, running: false, pendingContent: null, error: "The connection closed before the turn was saved." }));
          void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true });
        }
      } catch (error) {
        if (isAbort(error) || abort.signal.aborted) {
          setState(IDLE);
        } else {
          setState((s) => ({ ...s, running: false, pendingContent: null, error: errorMessage(error) }));
        }
        // The server may have stored the user message already; resync.
        void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true });
      } finally {
        controller.current = null;
      }
    },
    [projectId, applySaved, onSaved, qc],
  );

  const abort = useCallback(() => controller.current?.abort(), []);
  const dismiss = useCallback(() => setState(IDLE), []);

  return { state, send, abort, dismiss };
}
