"""SSE event and step-ID enums for the Content Marketing Agent.

Both the runner (agents/content/v3/runner.py) and the route (routes/content.py)
import from here so event names are defined in exactly one place. The frontend
mirrors these values in app/src/lib/contentEvents.js.

Mirrors agents/audit/events.py but adds two payload events
(PLAN_GENERATED, POST_DRAFT_UPDATED) and a DISPATCH_SUBAGENT step.
"""

from __future__ import annotations

from enum import StrEnum


class ContentEvent(StrEnum):
    """SSE event.event values emitted over the content stream."""

    PIPELINE_STARTED  = "pipeline_started"
    PIPELINE_FINISHED = "pipeline_finished"
    PIPELINE_FAILED   = "pipeline_failed"

    STEP_STARTED  = "step_started"
    STEP_FINISHED = "step_finished"
    STEP_FAILED   = "step_failed"

    QUESTIONS_REQUIRED = "questions_required"
    TODO_UPDATE        = "todo_update"

    AGENT_MESSAGE_CHUNK = "agent_message_chunk"
    MESSAGE_STOP        = "message_stop"

    THINKING_CHUNK = "thinking_chunk"
    REPORT_CHUNK   = "report_chunk"

    PLAN_GENERATED     = "plan_generated"
    POST_DRAFT_UPDATED = "post_draft_updated"


class ContentStep(StrEnum):
    """step_id values used in STEP_STARTED / STEP_FINISHED events."""

    LOAD_PROJECT     = "load_project"
    LOAD_HISTORY     = "load_history"
    LOAD_LIBRARIES   = "load_libraries"
    ENRICHING        = "enriching"
    SYNTHESIZE_PLAN  = "synthesize_plan"

    LOAD_TOPIC = "load_topic"
    WRITE_COPY = "write_copy"
    BUILD_HTML = "build_html"
    WRITE_META = "write_meta"

    DISPATCH_SUBAGENT = "dispatch_subagent"


STEP_LABELS: dict[ContentStep, str] = {
    ContentStep.LOAD_PROJECT:      "Loading project",
    ContentStep.LOAD_HISTORY:      "Loading post history",
    ContentStep.LOAD_LIBRARIES:    "Loading format + avatar libraries",
    ContentStep.ENRICHING:         "Researching trends + history",
    ContentStep.SYNTHESIZE_PLAN:   "Synthesizing 30-day plan",
    ContentStep.LOAD_TOPIC:        "Loading topic + brand context",
    ContentStep.WRITE_COPY:        "Writing slide copy",
    ContentStep.BUILD_HTML:        "Building slide HTML",
    ContentStep.WRITE_META:        "Writing post metadata",
    ContentStep.DISPATCH_SUBAGENT: "Sub-agent",
}
