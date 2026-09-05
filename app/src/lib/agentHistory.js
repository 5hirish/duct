"use client";

// Shared conversation-history rehydration: persisted agent_events rows →
// chat-bubble message objects. Used by ContentWorkspace and AuditWorkspace on
// resume. Tool events are deliberately dropped — they're forensics, not chat.

import { ErrorCode } from "./agentEvents";
import { Row, friendlyErrorMessage } from "./agentSession";

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
  let pendingThinking = "";
  const userText = (data) => {
    const c = data?.content;
    if (typeof c === "string") return c;
    if (Array.isArray(c))
      return c.filter((b) => b?.type === "text").map((b) => b.text).join(" ").trim() || "[image attached]";
    return "";
  };
  for (const e of events || []) {
    switch (e.kind) {
      case "user":
        out.push({ role: "user", text: userText(e.data) });
        break;
      case "thinking":
        pendingThinking = e.data?.text || "";
        break;
      case "assistant":
        out.push({ role: "assistant", text: e.data?.text || "", thinking: pendingThinking || undefined });
        pendingThinking = "";
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
