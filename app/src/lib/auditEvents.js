/**
 * SSE event names and step IDs for the SEO Audit Agent.
 * Mirror of backend agents/audit/events.py — keep in sync.
 */

export const AuditEvent = Object.freeze({
  PIPELINE_STARTED:    "pipeline_started",
  PIPELINE_FINISHED:   "pipeline_finished",
  PIPELINE_FAILED:     "pipeline_failed",

  STEP_STARTED:        "step_started",
  STEP_FINISHED:       "step_finished",

  QUESTIONS_REQUIRED:  "questions_required",
  REPORT_UPDATED:      "report_updated",
  TODO_UPDATE:         "todo_update",

  AGENT_MESSAGE_CHUNK: "agent_message_chunk",
  AGENT_MESSAGE:       "agent_message",
  MESSAGE_STOP:        "message_stop",

  SYNTHESIS_CHUNK:     "synthesis_chunk",   // legacy — no longer emitted

  THINKING_CHUNK:      "thinking_chunk",    // extended-thinking delta

  REPORT_CHUNK:        "report_chunk",      // streaming HTML token inside <duct_report>
});

export const AuditStep = Object.freeze({
  RESOLVE_URL:      "resolve_url",
  FETCH_SITEMAP:    "fetch_sitemap",
  CRAWL_PAGES:      "crawl_pages",
  SYNTHESIZE_AUDIT: "synthesize_audit",
});

export const STEP_LABELS = Object.freeze({
  [AuditStep.RESOLVE_URL]:      "Resolving website",
  [AuditStep.FETCH_SITEMAP]:    "Fetching sitemap",
  [AuditStep.CRAWL_PAGES]:      "Crawling pages",
  [AuditStep.SYNTHESIZE_AUDIT]: "AI synthesis",
});
