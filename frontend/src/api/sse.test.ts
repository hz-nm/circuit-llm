import { describe, expect, it } from "vitest";
import { parseStreamEvent } from "./designTurn";
import { readSse, SseParser, type SseMessage } from "./sse";

function parseAll(chunks: string[]): SseMessage[] {
  const out: SseMessage[] = [];
  const parser = new SseParser((m) => out.push(m));
  for (const chunk of chunks) parser.feed(chunk);
  parser.end();
  return out;
}

function streamOf(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(c);
      controller.close();
    },
  });
}

describe("SseParser", () => {
  it("parses events with types, joins multi-line data and skips comments", () => {
    const messages = parseAll([": keep-alive\n\nevent: attempt_started\ndata: {\"a\":1}\n\ndata: line1\ndata: line2\n\n"]);
    expect(messages).toEqual([
      { event: "attempt_started", data: '{"a":1}', id: null },
      { event: "message", data: "line1\nline2", id: null },
    ]);
  });

  it("handles events split at arbitrary chunk boundaries", () => {
    const text = "event: saved\ndata: {\"type\":\"saved\"}\n\nevent: failed\ndata: x\n\n";
    for (let size = 1; size <= 7; size++) {
      const chunks: string[] = [];
      for (let i = 0; i < text.length; i += size) chunks.push(text.slice(i, i + size));
      expect(parseAll(chunks).map((m) => m.event)).toEqual(["saved", "failed"]);
    }
  });

  it("accepts CRLF and CR line endings, including a CRLF split across chunks", () => {
    expect(parseAll(["data: a\r", "\n\r", "\ndata: b\r\r"]).map((m) => m.data)).toEqual(["a", "b"]);
  });

  it("strips exactly one space after the colon and handles fields without a value", () => {
    expect(parseAll(["data:  two spaces\n\ndata\n\n"]).map((m) => m.data)).toEqual([" two spaces", ""]);
  });

  it("delivers a final event that lacks its trailing blank line", () => {
    expect(parseAll(["event: completed\ndata: done"])).toEqual([{ event: "completed", data: "done", id: null }]);
  });

  it("ignores events without data", () => {
    expect(parseAll(["event: ping\n\n"])).toEqual([]);
  });
});

describe("readSse", () => {
  it("decodes UTF-8 sequences split across byte chunks", async () => {
    const bytes = new TextEncoder().encode('data: {"reply":"4.7 kΩ ±5 %"}\n\n');
    const split = bytes.indexOf(0xce) + 1; // in the middle of "Ω"
    const messages: SseMessage[] = [];
    for await (const m of readSse(streamOf([bytes.slice(0, split), bytes.slice(split)]))) messages.push(m);
    expect(messages.map((m) => m.data)).toEqual(['{"reply":"4.7 kΩ ±5 %"}']);
  });
});

describe("parseStreamEvent", () => {
  it("accepts known event types and rejects anything else", () => {
    expect(parseStreamEvent('{"type":"failed","error":"boom"}')).toEqual({ type: "failed", error: "boom" });
    expect(parseStreamEvent('{"type":"unknown"}')).toBeNull();
    expect(parseStreamEvent("not json")).toBeNull();
  });
});
