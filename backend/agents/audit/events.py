"""SSE event and step-ID enums for the SEO Audit Agent.

Both the runner (agents/audit/v3/runner.py) and the route (routes/audit.py)
import from here so event names are defined in exactly one place.
The frontend mirrors these values in app/src/lib/auditEvents.js.
"""

from __future__ import annotations

from enum import StrEnum


class AuditEvent(StrEnum):
    """SSE event.event values emitted over the audit stream."""

    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_FINISHED = "pipeline_finished"
    PIPELINE_FAILED = "pipeline_failed"

    STEP_STARTED = "step_started"
    STEP_FINISHED = "step_finished"

    QUESTIONS_REQUIRED = "questions_required"
    REPORT_UPDATED = "report_updated"
    TODO_UPDATE = "todo_update"

    AGENT_MESSAGE_CHUNK = "agent_message_chunk"
    AGENT_MESSAGE = "agent_message"
    MESSAGE_STOP = "message_stop"

    SYNTHESIS_CHUNK = "synthesis_chunk"   # kept for backwards compat; no longer emitted

    THINKING_CHUNK = "thinking_chunk"     # model extended-thinking delta

    REPORT_CHUNK = "report_chunk"         # streaming HTML token inside <duct_report>


class AuditStep(StrEnum):
    """step_id values used in STEP_STARTED / STEP_FINISHED events."""

    RESOLVE_URL = "resolve_url"
    FETCH_SITEMAP = "fetch_sitemap"
    CRAWL_PAGES = "crawl_pages"
    SYNTHESIZE_AUDIT = "synthesize_audit"


STEP_LABELS: dict[AuditStep, str] = {
    AuditStep.RESOLVE_URL:     "Resolving website",
    AuditStep.FETCH_SITEMAP:   "Fetching sitemap",
    AuditStep.CRAWL_PAGES:     "Crawling pages",
    AuditStep.SYNTHESIZE_AUDIT: "AI synthesis",
}
