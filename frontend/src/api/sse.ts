/**
 * A small, spec-compliant Server-Sent Events parser for use over `fetch` +
 * `ReadableStream` (EventSource cannot POST).
 *
 * Follows the WHATWG event-stream rules: lines end in CRLF, LF or CR (a CRLF
 * may be split across chunks), `:` starts a comment, a field without a colon
 * has an empty value, one leading space after the colon is stripped, multiple
 * `data:` lines are joined with "\n", and a blank line dispatches the event.
 */

export interface SseMessage {
  event: string;
  data: string;
  id: string | null;
}

export class SseParser {
  private buffer = "";
  private pendingCR = false;
  private eventType = "";
  private dataLines: string[] = [];
  private hasData = false;
  private lastId: string | null = null;

  constructor(private readonly onMessage: (message: SseMessage) => void) {}

  /** Feed a decoded text chunk; complete events are dispatched synchronously. */
  feed(chunk: string): void {
    let text = chunk;
    if (this.pendingCR) {
      // The previous chunk ended in CR; a leading LF belongs to that line ending.
      if (text.startsWith("\n")) text = text.slice(1);
      this.pendingCR = false;
    }
    this.buffer += text;

    let start = 0;
    for (let i = 0; i < this.buffer.length; i++) {
      const ch = this.buffer[i];
      if (ch !== "\n" && ch !== "\r") continue;
      this.processLine(this.buffer.slice(start, i));
      if (ch === "\r") {
        if (i + 1 < this.buffer.length) {
          if (this.buffer[i + 1] === "\n") i++;
        } else {
          this.pendingCR = true;
        }
      }
      start = i + 1;
    }
    this.buffer = this.buffer.slice(start);
  }

  /** Signal end of stream: a trailing event without its blank line is still delivered. */
  end(): void {
    if (this.buffer.length > 0) {
      this.processLine(this.buffer);
      this.buffer = "";
    }
    this.dispatch();
  }

  private processLine(line: string): void {
    if (line === "") {
      this.dispatch();
      return;
    }
    if (line.startsWith(":")) return; // comment / keep-alive

    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    switch (field) {
      case "event":
        this.eventType = value;
        break;
      case "data":
        this.dataLines.push(value);
        this.hasData = true;
        break;
      case "id":
        if (!value.includes("\0")) this.lastId = value;
        break;
      default:
        break; // "retry" and unknown fields are ignored
    }
  }

  private dispatch(): void {
    if (this.hasData) {
      this.onMessage({
        event: this.eventType || "message",
        data: this.dataLines.join("\n"),
        id: this.lastId,
      });
    }
    this.eventType = "";
    this.dataLines = [];
    this.hasData = false;
  }
}

/** Read an SSE byte stream to completion, yielding each message as it arrives. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  const queue: SseMessage[] = [];
  const parser = new SseParser((message) => queue.push(message));
  let finished = false;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        finished = true;
        parser.feed(decoder.decode());
        parser.end();
      } else {
        parser.feed(decoder.decode(value, { stream: true }));
      }
      while (queue.length > 0) yield queue.shift()!;
      if (done) return;
    }
  } finally {
    // If the consumer stopped early, cancel the underlying stream instead of leaking it.
    if (!finished) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
