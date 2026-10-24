import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, errorMessage, unwrap } from "../../api/client";
import { keys, useSimulation } from "../../api/queries";
import type { SimulationResult, VersionOut } from "../../api/types";
import { buildLiveVoltages, CursorStore, defaultDriver, isDrivable, type LiveVoltages } from "./live";
import { useProbes, type Probes } from "./probes";

export type RunStatus =
  | { kind: "ready" }
  | { kind: "running"; startedAt: number }
  | { kind: "done"; ms: number }
  | { kind: "failed"; reason: string }
  | { kind: "stopped" }
  | { kind: "blocked"; reason: string };

export interface RunOptions {
  stop_time?: number;
  step_time?: number;
}

export interface SimulationSession {
  projectId: string;
  version: VersionOut;
  /** Cached or freshly computed result; null = never simulated; undefined = loading. */
  result: SimulationResult | null | undefined;
  status: RunStatus;
  running: boolean;
  run: (options?: RunOptions, manual?: boolean) => void;
  stop: () => void;
  autoRun: boolean;
  setAutoRun: (on: boolean) => void;
  /** Increments after every successful run; `manual` tells whether the user asked for it. */
  lastRun: { count: number; manual: boolean };
  /** Index of the analysis that drives the live schematic (tran/dc), or null. */
  driver: number | null;
  setDriver: (index: number) => void;
  live: LiveVoltages | null;
  cursor: CursorStore;
  probes: Probes;
}

const Context = createContext<SimulationSession | null>(null);

export function useSimulationSession(): SimulationSession {
  const session = useContext(Context);
  if (!session) throw new Error("useSimulationSession must be used inside <SimulationSessionProvider>");
  return session;
}

const AUTO_RUN_KEY = "circuits-llm:auto-run";

/** Versions auto-run in this page session (module-level so remounts don't re-run a failing version). */
const autoAttempted = new Set<string>();

function readAutoRun(): boolean {
  try {
    return localStorage.getItem(AUTO_RUN_KEY) !== "off";
  } catch {
    return true;
  }
}

interface Props {
  projectId: string;
  version: VersionOut;
  available: boolean;
  children: ReactNode;
}

/** Why a version can't be simulated right now, or null if it can. */
function blockedReason(version: VersionOut, available: boolean, options?: RunOptions): string | null {
  if (!available) return "No simulator (ngspice missing)";
  const errors = version.issues.filter((i) => i.severity === "error").length;
  if (errors > 0) return `Fix ${errors} ERC error${errors === 1 ? "" : "s"} first`;
  if ((version.circuit.analyses ?? []).length === 0 && !options?.stop_time) return "No analyses (set a stop time to run a transient)";
  return null;
}

export function SimulationSessionProvider({ projectId, version, available, children }: Props) {
  const qc = useQueryClient();
  const cached = useSimulation(projectId, version.number);
  const result = cached.data;
  const [status, setStatus] = useState<RunStatus>({ kind: "ready" });
  const [autoRun, setAutoRunState] = useState(readAutoRun);
  const [lastRun, setLastRun] = useState({ count: 0, manual: false });
  const controller = useRef<AbortController | null>(null);

  const versionKey = `${projectId}:${version.number}`;

  // The provider is keyed by version, so state starts fresh; abort an in-flight run on unmount.
  useEffect(() => () => controller.current?.abort(), []);

  const run = useCallback(
    (options?: RunOptions, manual = true) => {
      const blocked = blockedReason(version, available, options);
      if (blocked) {
        setStatus({ kind: "blocked", reason: blocked });
        return;
      }
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      const startedAt = performance.now();
      setStatus({ kind: "running", startedAt });
      const body = options && (options.stop_time || options.step_time) ? options : undefined;
      unwrap(
        api.POST("/api/projects/{project_id}/versions/{number}/simulate", {
          params: { path: { project_id: projectId, number: version.number } },
          body,
          signal: abort.signal,
        }),
      )
        .then((res) => {
          if (abort.signal.aborted) return;
          qc.setQueryData(keys.simulation(projectId, version.number), res);
          setStatus(
            res.ok
              ? { kind: "done", ms: res.duration_ms || Math.round(performance.now() - startedAt) }
              : { kind: "failed", reason: res.error ?? "the simulator reported an error" },
          );
          setLastRun((r) => ({ count: r.count + 1, manual }));
        })
        .catch((error: unknown) => {
          if (abort.signal.aborted) setStatus({ kind: "stopped" });
          else setStatus({ kind: "failed", reason: errorMessage(error) });
        })
        .finally(() => {
          if (controller.current === abort) controller.current = null;
        });
    },
    [projectId, version, available, qc],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  const setAutoRun = useCallback((on: boolean) => {
    setAutoRunState(on);
    try {
      localStorage.setItem(AUTO_RUN_KEY, on ? "on" : "off");
    } catch {
      /* storage unavailable */
    }
  }, []);

  // Auto-run: a version with no cached result (manual edit, restore, first open) runs once.
  useEffect(() => {
    if (!autoRun || !cached.isSuccess || result !== null) return;
    if (autoAttempted.has(versionKey)) return;
    if (blockedReason(version, available)) return;
    autoAttempted.add(versionKey);
    run(undefined, false);
  }, [autoRun, cached.isSuccess, result, versionKey, version, available, run]);

  // Driving analysis: user choice if still valid, else the default (transient, then DC).
  const [chosenDriver, setDriver] = useState<number | null>(null);
  const analyses = result?.ok ? (result.analyses ?? []) : [];
  const chosen = chosenDriver !== null ? analyses[chosenDriver] : undefined;
  const driver = chosen && isDrivable(chosen) ? chosenDriver : defaultDriver(result);
  const live = useMemo(() => buildLiveVoltages(result, driver), [result, driver]);

  const [cursor] = useState(() => new CursorStore());
  // Keep the cursor where it was if the new sweep still covers it (e.g. a re-run), else rewind.
  useEffect(() => {
    if (live?.kind !== "sweep") {
      cursor.set(null, "scrubber");
      return;
    }
    const first = live.x[0] ?? 0;
    const last = live.x[live.x.length - 1] ?? first;
    const current = cursor.get();
    cursor.set(current !== null && current >= first && current <= last ? current : first, "scrubber");
  }, [live, cursor]);

  const probes = useProbes(projectId, version.number, version.circuit, result);
  const running = status.kind === "running";
  const shownStatus = useMemo<RunStatus>(
    () => (status.kind === "ready" && !available ? { kind: "blocked", reason: "No simulator (ngspice missing)" } : status),
    [status, available],
  );

  const session = useMemo<SimulationSession>(
    () => ({
      projectId,
      version,
      result,
      status: shownStatus,
      running,
      run,
      stop,
      autoRun,
      setAutoRun,
      lastRun,
      driver,
      setDriver,
      live,
      cursor,
      probes,
    }),
    [projectId, version, result, shownStatus, running, run, stop, autoRun, setAutoRun, lastRun, driver, live, cursor, probes],
  );

  return <Context.Provider value={session}>{children}</Context.Provider>;
}
