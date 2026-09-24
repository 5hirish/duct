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
      { role: "user", text: "and this?", attachments: [{ name: "image", mediaType: "image/png", kind: "image", preview: "" }] },
    ]);
  });

  it("stamps each row with when it was written and keeps a compaction's summary", () => {
    const rows = mapEventsToMessages([
      { kind: "user", data: { content: "hi" }, created_at: "2026-09-20T10:00:00Z" },
      { kind: "compacted", data: { summary: "Sessions fell after the pricing change." } },
      { kind: "assistant", data: { text: "Hello." }, created_at: "2026-09-20T10:00:05Z" },
    ]);
    expect(rows[0].at).toBe(Date.parse("2026-09-20T10:00:00Z"));
    expect(rows[1]).toEqual({ role: "notice", kind: "compacted", before: null, after: null, summary: "Sessions fell after the pricing change." });
    expect(rows[2].at).toBe(Date.parse("2026-09-20T10:00:05Z"));
  });
});

describe("memory and context rows come back on a reopened thread", () => {
  it("rebuilds Recalled, Remembered (collapsed per turn) and the context notice", () => {
    const rows = mapEventsToMessages([
      { seq: 1, kind: "context", data: { model: "claude-sonnet-5", resume: false, blocks: { business_context: "Acme…", memory: "", data_sources: "ga4" } } },
      { seq: 2, kind: "memory_recalled", data: { memories: [{ id: "m1", title: "Pricing changed" }] } },
      { seq: 3, kind: "memory_written", data: { memory: { id: "m2", title: "Mobile is the channel" } } },
      { seq: 4, kind: "memory_written", data: { memory: { id: "m3", title: "Ads paused on the 4th" } } },
      { seq: 5, kind: "context", data: { model: "claude-sonnet-5", resume: true, blocks: { resume_primer: "…" } } },
    ]);
    expect(rows.map((r) => r.role)).toEqual(["activity", "memory_recall", "memory_note"]);
    expect(rows[0].activity).toMatchObject({ id: "context-1", tool: "ProjectContext", meta: { blocks: ["business_context", "data_sources"] } });
    expect(rows[2].memories.map((m) => m.id)).toEqual(["m2", "m3"]);
  });
});

describe("review cards come back on a reopened thread", () => {
  const card = (status) => ({ change_set_id: "cs-1", title: "Pause Display", status, changes: [] });

  it("rebuilds the card from the stored ProposeChanges result, one per set", () => {
    const rows = mapEventsToMessages([
      { kind: "tool_result", data: { name: "ProposeChanges", result: JSON.stringify({ ...card("proposed"), next_step: "wait" }) } },
      { kind: "assistant", data: { text: "Proposed a pause." } },
      { kind: "tool_result", data: { name: "RollbackChangeSet", result: card("rolled_back") } },
    ]);
    expect(rows.map((r) => r.role)).toEqual(["change_set_card", "assistant"]);
    expect(rows[0].changeSet).toMatchObject({ change_set_id: "cs-1", status: "rolled_back" });
  });

  it("draws nothing for a failed proposal", () => {
    const rows = mapEventsToMessages([
      { kind: "tool_result", data: { name: "ProposeChanges", is_error: true, result: '{"error": "unknown op"}' } },
    ]);
    expect(rows).toEqual([]);
  });
});
