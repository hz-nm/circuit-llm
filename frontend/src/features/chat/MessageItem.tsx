import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { MessageRecord } from "../../api/types";

interface Props {
  message: MessageRecord;
  selectedVersion: number | null;
  onOpenVersion: (n: number) => void;
}

export function UserBubble({ content, pending = false }: { content: string; pending?: boolean }) {
  return (
    <div className="flex justify-end">
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-accent px-3 py-2 text-sm text-accent-ink ${pending ? "opacity-80" : ""}`}
      >
        {content}
      </div>
    </div>
  );
}

export function MessageItem({ message, selectedVersion, onOpenVersion }: Props) {
  if (message.role === "user") return <UserBubble content={message.content} />;

  const meta = message.meta;
  const warnings = meta?.warnings ?? [];
  const isError = meta?.error ?? false;
  const version = message.version_number;

  return (
    <div className="flex flex-col gap-1">
      <div
        className={`rounded-2xl rounded-bl-sm border px-3 py-2 text-sm ${
          isError ? "border-danger/40 bg-danger-soft" : "border-line bg-bg"
        }`}
      >
        {isError ? (
          <p className="whitespace-pre-wrap text-danger">{message.content}</p>
        ) : (
          <div className="markdown">
            <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
          </div>
        )}
        {warnings.length > 0 && (
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer text-warn">
              {warnings.length} ERC warning{warnings.length === 1 ? "" : "s"}
            </summary>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted">
              {warnings.map((w, i) => (
                <li key={i}>{w.message}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
      <div className="flex items-center gap-2 px-1 text-[11px] text-muted">
        {meta?.model && <span>via {meta.model}</span>}
        {version != null && (
          <button
            type="button"
            onClick={() => onOpenVersion(version)}
            className={`rounded px-1.5 py-0.5 font-medium focus-visible:outline-2 focus-visible:outline-accent ${
              version === selectedVersion ? "bg-accent-soft text-accent" : "bg-sunken text-ink hover:text-accent"
            }`}
            title={`Open version ${version}`}
          >
            v{version}
          </button>
        )}
        <time dateTime={message.created_at}>
          {new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </time>
      </div>
    </div>
  );
}
