import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { MessageRecord } from "../../api/types";
import { Button } from "../../ui/Button";
import { MessageItem, UserBubble } from "./MessageItem";
import { TurnProgress } from "./TurnProgress";
import { useDesignTurn } from "./useDesignTurn";

const MAX_LENGTH = 8000;

const EXAMPLES = [
  "A red LED powered from 9 V with a current-limiting resistor",
  "An RC low-pass filter with a 1 kHz cutoff, and show me its Bode plot",
  "A non-inverting op-amp amplifier with a gain of 11 on ±12 V rails",
];

interface Props {
  projectId: string;
  messages: MessageRecord[];
  loading: boolean;
  selectedVersion: number | null;
  onOpenVersion: (n: number) => void;
}

export function ChatPanel({ projectId, messages, loading, selectedVersion, onOpenVersion }: Props) {
  const [draft, setDraft] = useState("");
  const { state, send, abort, dismiss } = useDesignTurn(projectId, (saved) => {
    if (saved.version) onOpenVersion(saved.version.number);
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, state.steps.length, state.pendingContent]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const content = draft.trim();
    if (!content || state.running) return;
    setDraft("");
    void send(content);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  const empty = !loading && messages.length === 0 && !state.pendingContent;

  return (
    <>
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {loading && <p className="text-xs text-muted">Loading conversation…</p>}
        {empty && (
          <div className="mt-6 text-sm">
            <p className="font-medium">Describe a circuit to get started.</p>
            <ul className="mt-2 space-y-1.5">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => setDraft(example)}
                    className="w-full rounded-lg border border-line px-3 py-2 text-left text-xs text-muted hover:border-accent hover:text-ink"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {messages.map((message) => (
          <MessageItem key={message.id} message={message} selectedVersion={selectedVersion} onOpenVersion={onOpenVersion} />
        ))}
        {state.pendingContent && <UserBubble content={state.pendingContent} pending />}
        {(state.running || state.steps.length > 0) && <TurnProgress steps={state.steps} running={state.running} />}
        {state.error && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-3 py-2 text-xs text-danger">
            {state.error}{" "}
            <button type="button" className="underline" onClick={dismiss}>
              Dismiss
            </button>
          </div>
        )}
      </div>

      <form onSubmit={submit} className="border-t border-line p-3">
        <label htmlFor="chat-input" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-input"
          rows={3}
          value={draft}
          maxLength={MAX_LENGTH}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Describe a circuit or ask for a change… (Enter to send, Shift+Enter for a new line)"
          className="w-full resize-none rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <div className="mt-2 flex items-center justify-end gap-2">
          {state.running ? (
            <Button variant="danger" onClick={abort}>
              Stop
            </Button>
          ) : (
            <Button type="submit" variant="primary" disabled={!draft.trim()}>
              Send
            </Button>
          )}
        </div>
      </form>
    </>
  );
}
