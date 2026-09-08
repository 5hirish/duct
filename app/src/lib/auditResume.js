"use client";

// Launch a resumed audit chat: stash the AuditWorkspace params under the
// session key (same mechanism as a fresh audit) and navigate. The backend
// rehydrates the stored report for the conversation — no re-crawl.

import { DEFAULT_AUDIT_TEMPLATE_ID, ReportMode } from "./audit";
import { loadPreferences } from "./userPreferences";

// A message the workspace sends on the user's behalf once the resume is
// ready. Not part of the request — the backend forbids unknown fields — so
// the session page lifts it off before the params go on the wire, the same
// way it lifts `pending_provider`.
export const KICKOFF_KEY = "kickoff";

export function startAuditResume(
  router,
  { conversationId, projectId, url = "", reportMode = "", templateId = "", kickoff = "" },
) {
  const params = {
    url: url || "",
    project_id: projectId || null,
    resume: true,
    conversation_id: conversationId,
    report_mode: reportMode || ReportMode.TEMPLATE,
    template_id: templateId || DEFAULT_AUDIT_TEMPLATE_ID,
    user_preferences: loadPreferences(),
    ...(kickoff ? { [KICKOFF_KEY]: kickoff } : {}),
  };
  const sessionId = crypto.randomUUID();
  sessionStorage.setItem(`audit_session_${sessionId}`, JSON.stringify(params));
  router.push(`/audit/seo/${sessionId}`);
}
