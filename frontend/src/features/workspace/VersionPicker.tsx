import type { VersionSummary } from "../../api/types";

const SOURCE_LABEL: Record<VersionSummary["source"], string> = {
  llm: "AI",
  manual: "edited",
  restore: "restored",
};

interface Props {
  versions: VersionSummary[];
  selected: number;
  latest: number | null;
  onSelect: (n: number | null) => void;
}

export function VersionPicker({ versions, selected, latest, onSelect }: Props) {
  const sorted = [...versions].sort((a, b) => b.number - a.number);
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      Version
      <select
        value={selected}
        onChange={(e) => {
          const n = Number(e.target.value);
          onSelect(n === latest ? null : n);
        }}
        className="rounded-md border border-line bg-bg px-1.5 py-1 text-xs text-ink"
      >
        {sorted.map((v) => (
          <option key={v.number} value={v.number}>
            v{v.number} · {SOURCE_LABEL[v.source]} · {new Date(v.created_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
            {v.number === latest ? " (latest)" : ""}
          </option>
        ))}
        {!sorted.some((v) => v.number === selected) && <option value={selected}>v{selected}</option>}
      </select>
    </label>
  );
}
