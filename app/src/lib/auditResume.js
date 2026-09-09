"use client";

// Launch a resumed audit chat: stash the AuditWorkspace params under the
// session key (same mechanism as a fresh audit) and navigate. The backend
// rehydrates the stored report for the conversation — no re-crawl.

import { DEFAULT_AUDIT_TEMPLATE_ID, ReportMode } from "./audit";
import { openAuditSession } from "./auditSession";
import { loadPreferences } from "./userPreferences";

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
  };
  // `kickoff` is client-only — a message the workspace sends on the user's
  // behalf once the resume is ready. It must never reach the request body,
  // where an unknown field is a 422.
  const sessionId = openAuditSession(params, { kickoff });
  router.push(`/audit/seo/${sessionId}`);
}
