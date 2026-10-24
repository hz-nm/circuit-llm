import { useCallback, useMemo, useState } from "react";
import type { Circuit, SimulationResult, Trace } from "../../api/types";
import { netKey } from "./live";

/** The user's changes relative to the default probes (keys are upper-cased net names). */
interface ProbeOverrides {
  added: string[];
  removed: string[];
  /** Components whose V-across and current the user added to the plots (upper-cased ids). */
  components: string[];
}

const storageKey = (projectId: string, version: number) => `circuits-llm:probes:${projectId}:${version}`;

function load(key: string): ProbeOverrides {
  try {
    const raw = localStorage.getItem(key);
    const value: unknown = raw ? JSON.parse(raw) : null;
    if (value && typeof value === "object" && "added" in value && "removed" in value) {
      const v = value as { added: unknown; removed: unknown; components?: unknown };
      const strings = (list: unknown) => (Array.isArray(list) ? list.filter((s): s is string => typeof s === "string") : []);
      if (Array.isArray(v.added) && Array.isArray(v.removed)) {
        return { added: strings(v.added), removed: strings(v.removed), components: strings(v.components) };
      }
    }
  } catch {
    /* storage unavailable or corrupt */
  }
  return { added: [], removed: [], components: [] };
}

/** Nets probed by default: traces the backend marked `probed`, plus the circuit's voltage probes. */
export function defaultProbedNets(circuit: Circuit, result: SimulationResult | null | undefined): Set<string> {
  const nets = new Set<string>();
  for (const p of circuit.probes ?? []) if (p.kind === "voltage") nets.add(netKey(p.target));
  for (const a of result?.analyses ?? []) {
    if (a.type === "op") continue;
    for (const t of a.traces) if (t.net && t.probed !== false) nets.add(netKey(t.net));
  }
  nets.delete("GND");
  return nets;
}

export interface Probes {
  /** Effective probed nets (upper-cased). */
  nets: ReadonlySet<string>;
  isProbed: (net: string) => boolean;
  toggle: (net: string) => void;
  /** Whether a trace should be plotted: probed by default or by the user, and not un-probed. */
  showsTrace: (trace: Trace) => boolean;
  /** Components added to the plots from the multimeter ("Plot"). */
  components: ReadonlySet<string>;
  togglePlot: (componentId: string) => void;
}

export function useProbes(projectId: string, version: number, circuit: Circuit, result: SimulationResult | null | undefined): Probes {
  const key = storageKey(projectId, version);
  const [state, setState] = useState(() => ({ key, overrides: load(key) }));
  // Reload when switching version (state is keyed so this stays render-pure).
  const overrides = state.key === key ? state.overrides : load(key);

  const defaults = useMemo(() => defaultProbedNets(circuit, result), [circuit, result]);
  const nets = useMemo(() => {
    const set = new Set(defaults);
    for (const n of overrides.added) set.add(n);
    for (const n of overrides.removed) set.delete(n);
    return set;
  }, [defaults, overrides]);

  const save = useCallback(
    (next: ProbeOverrides) => {
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* storage unavailable */
      }
      setState({ key, overrides: next });
    },
    [key],
  );

  const toggle = useCallback(
    (net: string) => {
      const k = netKey(net);
      if (k === "GND") return;
      const added = new Set(overrides.added);
      const removed = new Set(overrides.removed);
      if (nets.has(k)) {
        added.delete(k);
        if (defaults.has(k)) removed.add(k);
      } else {
        removed.delete(k);
        if (!defaults.has(k)) added.add(k);
      }
      save({ ...overrides, added: [...added], removed: [...removed] });
    },
    [nets, defaults, overrides, save],
  );

  const components = useMemo(() => new Set(overrides.components), [overrides]);
  const togglePlot = useCallback(
    (componentId: string) => {
      const k = netKey(componentId);
      const next = new Set(components);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      save({ ...overrides, components: [...next] });
    },
    [components, overrides, save],
  );

  return useMemo(
    () => ({
      nets,
      isProbed: (net: string) => nets.has(netKey(net)),
      toggle,
      showsTrace: (trace: Trace) => {
        if (trace.net) return nets.has(netKey(trace.net));
        if (trace.component && components.has(netKey(trace.component))) return true;
        return trace.probed !== false;
      },
      components,
      togglePlot,
    }),
    [nets, toggle, components, togglePlot],
  );
}
