"use client";

// Shared conversation-history rehydration: persisted agent_events rows →
// chat-bubble message objects. Used by ContentWorkspace and AuditWorkspace on
// resume.
//
// Tool traffic used to be dropped wholesale here ("forensics, not chat"),
// which was right while nothing rendered it and wrong the moment the
// transcript grew activity cards: a reopened thread lost every source the
// agent had read, so the record in the database was better than the record on
// screen. The allowlisted calls (lib/toolActivity.js) come back as the same
// rows they were live; everything else is still dropped, still forensics.

import { ErrorCode } from "./agentEvents";
import { Notice, Row, friendlyErrorMessage } from "./agentSession";
import { describeContent } from "./attachments";
import { activityCallIndex, activityFromStored, contextActivity } from "./toolActivity";

/** A stored failure becomes the row the live client showed: the turn-failed
 *  bubble with its code (so the action under it is the right one), or, for a
 *  stop, the quiet line the transcript ends on. */
function failureRow(data) {
  const code = data?.code || "";
  if (code === ErrorCode.CANCELLED) {
    return { role: Row.NOTICE, text: "Stopped here — the turn was interrupted." };
  }
  return {
    role: Row.SEND_ERROR,
    text: friendlyErrorMessage(data?.error || "That turn failed.", code),
    content: null,
    code,
    retryable: data?.retryable ?? true,
  };
}

export function mapEventsToMessages(events) {
  const out = [];
  const calls = activityCallIndex(events);
  let pendingThinking = "";
  // The model each run started on, from the CONTEXT row the runner writes
  // before its first call. A later run on a different model gets the same
  // divider the live transcript draws.
  let lastModel = "";
  // The row's clock is when it was written, so a reopened thread shows the
  // same "2 days ago" on hover that the live one would have.
  const stamp = (e) => (e.created_at ? { at: Date.parse(e.created_at) || undefined } : {});
  for (const e of events || []) {
    switch (e.kind) {
      case "user": {
        const { text, attachments } = describeContent(e.data?.content);
        out.push({ role: "user", text, ...(attachments.length ? { attachments } : {}), ...stamp(e) });
        break;
      }
      case "thinking":
        pendingThinking = e.data?.text || "";
        break;
      case "assistant":
        out.push({ role: "assistant", text: e.data?.text || "", thinking: pendingThinking || undefined, ...stamp(e) });
        pendingThinking = "";
        break;
      case "compacted":
        // The sizes are gone with the run; the divider says it happened and
        // keeps the summary, which is the part a reader can still use.
        if (pendingThinking) { out.push({ role: "assistant", text: "", thinking: pendingThinking }); pendingThinking = ""; }
        out.push({ role: Row.NOTICE, kind: Notice.COMPACTED, before: null, after: null, summary: e.data?.summary || "" });
        break;
      case "question": {
        const qs = (e.data?.questions || []).map((q) => q?.question).filter(Boolean).join(" · ");
        if (pendingThinking) { out.push({ role: "assistant", text: "", thinking: pendingThinking }); pendingThinking = ""; }
        if (qs) out.push({ role: "assistant", text: `**Quick question:** ${qs}` });
        break;
      }
      case "answer": {
        const ans = Object.values(e.data?.answers || {}).filter(Boolean).join(", ");
        if (ans) out.push({ role: "user", text: ans });
        break;
      }
      case "context": {
        const model = e.data?.model || "";
        if (model && lastModel && model !== lastModel) {
          out.push({ role: Row.NOTICE, kind: Notice.MODEL, label: e.data?.model_label || model, model });
        }
        if (model) lastModel = model;
        // The same "Read project context" row the run drew live, from the
        // row it recorded at the same moment.
        const activity = contextActivity(e.data, e.seq != null ? `context-${e.seq}` : "");
        if (activity) out.push({ role: Row.ACTIVITY, activity });
        break;
      }
      case "memory_recalled":
        if (e.data?.memories?.length) out.push({ role: Row.MEMORY_RECALL, memories: e.data.memories });
        break;
      case "memory_written": {
        // Several writes in one turn collapse into one line, as they do live.
        const last = out[out.length - 1];
        if (!e.data?.memory) break;
        if (last?.role === Row.MEMORY_NOTE) last.memories = [...last.memories, e.data.memory];
        else out.push({ role: Row.MEMORY_NOTE, memories: [e.data.memory] });
        break;
      }
      case "tool_result": {
        const activity = activityFromStored(e, calls);
        if (activity) out.push({ role: Row.ACTIVITY, activity });
        break;
      }
      case "failure":
        if (pendingThinking) { out.push({ role: "assistant", text: "", thinking: pendingThinking }); pendingThinking = ""; }
        out.push(failureRow(e.data));
        break;
      default:
        break;
    }
  }
  if (pendingThinking) out.push({ role: "assistant", text: "", thinking: pendingThinking });
  return out;
}
