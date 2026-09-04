import { describe, expect, it } from "vitest";
import { mapEventsToMessages } from "../agentHistory";

describe("mapEventsToMessages", () => {
  it("rebuilds the transcript shape the chat renders, dropping tool forensics", () => {
    const rows = mapEventsToMessages([
      { kind: "user", data: { content: "why did CPA jump?" } },
      { kind: "tool_use", data: { name: "FetchData" } },
      { kind: "thinking", data: { text: "check ads" } },
      { kind: "assistant", data: { text: "One campaign." } },
      { kind: "question", data: { questions: [{ question: "Which goal?" }] } },
      { kind: "answer", data: { answers: { "Which goal?": "Signups" } } },
      { kind: "user", data: { content: [{ type: "image" }, { type: "text", text: "and this?" }] } },
    ]);
    expect(rows).toEqual([
      { role: "user", text: "why did CPA jump?" },
      { role: "assistant", text: "One campaign.", thinking: "check ads" },
      { role: "assistant", text: "**Quick question:** Which goal?" },
      { role: "user", text: "Signups" },
      { role: "user", text: "and this?" },
    ]);
  });
});
