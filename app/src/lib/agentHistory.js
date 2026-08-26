"use client";

// Shared conversation-history rehydration: persisted agent_events rows →
// chat-bubble message objects. Used by ContentWorkspace and AuditWorkspace on
// resume. Tool events are deliberately dropped — they're forensics, not chat.

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
      default:
        break;
    }
  }
  if (pendingThinking) out.push({ role: "assistant", text: "", thinking: pendingThinking });
  return out;
}
