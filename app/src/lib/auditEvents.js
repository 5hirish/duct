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
  ARTIFACT_VERSION:    "artifact_version",   // new version of the primary artifact (full payload)
  ARTIFACT_UPDATED:    "artifact_updated",   // compact artifact card in the transcript
  EXECUTION_PROPOSED:  "execution_proposed",  // change-set card; upsert by change_set_id
  MEMORY_WRITTEN:      "memory_written",      // the quiet "Remembered: …" line
  MEMORY_RECALLED:     "memory_recalled",     // ids the turn was primed with
  TODO_UPDATE:         "todo_update",

  AGENT_MESSAGE_CHUNK: "agent_message_chunk",
  AGENT_MESSAGE:       "agent_message",
  MESSAGE_STOP:        "message_stop",

  SYNTHESIS_CHUNK:     "synthesis_chunk",   // legacy — no longer emitted

  THINKING_CHUNK:      "thinking_chunk",    // extended-thinking delta

  ARTIFACT_CHUNK:      "artifact_chunk",    // streaming HTML token inside <duct_artifact>

  // Legacy wire values. The backend no longer emits these; they stay here so an
  // app deployed ahead of the backend keeps rendering. Deploy order is app then
  // backend — see backend/agents/core/events.py. Remove once both are out.
  LEGACY_REPORT_UPDATED: "report_updated",
  LEGACY_REPORT_CHUNK:   "report_chunk",
});

export const AuditStep = Object.freeze({
  RESOLVE_URL:      "resolve_url",
  FETCH_SITEMAP:    "fetch_sitemap",
  CRAWL_PAGES:      "crawl_pages",
  ENRICHING:        "enriching",        // shared step — must match AgentStep.ENRICHING
  SYNTHESIZE_AUDIT: "synthesize_audit",
});

export const STEP_LABELS = Object.freeze({
  [AuditStep.RESOLVE_URL]:      "Resolving website",
  [AuditStep.FETCH_SITEMAP]:    "Fetching sitemap",
  [AuditStep.CRAWL_PAGES]:      "Crawling pages",
  [AuditStep.ENRICHING]:        "Researching competitors",
  [AuditStep.SYNTHESIZE_AUDIT]: "AI synthesis",
});
