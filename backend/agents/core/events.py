"""Canonical SSE event + step vocabulary, shared by every agent type.

One enum so the frontend speaks a single language across audit, content,
insights, and any future agent. An agent simply never emits events/steps it
doesn't support — there is no per-agent enum. Per-agent modules
(agents/audit/events.py, agents/content/events.py) re-export these names for
backwards compatibility.

IMPORTANT: the string values are a contract with the frontend
(app/src/lib/auditEvents.js, app/src/lib/contentEvents.js). Never change an
existing value; only add new members.
"""

from __future__ import annotations

from enum import StrEnum


class AgentEvent(StrEnum):
    """Every ``event`` value emitted over any agent's SSE stream."""

    # Pipeline lifecycle
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_FINISHED = "pipeline_finished"
    PIPELINE_FAILED = "pipeline_failed"

    # Step lifecycle
    STEP_STARTED = "step_started"
    STEP_FINISHED = "step_finished"
    STEP_FAILED = "step_failed"

    # Human-in-the-loop
    QUESTIONS_REQUIRED = "questions_required"
    SLIDE_RENDER_REQUESTED = "slide_render_requested"  # agent asks the browser to rasterize a slide

    # Progress / todos
    TODO_UPDATE = "todo_update"

    # Streaming model output
    AGENT_MESSAGE_CHUNK = "agent_message_chunk"
    AGENT_MESSAGE = "agent_message"
    MESSAGE_STOP = "message_stop"
    THINKING_CHUNK = "thinking_chunk"        # model extended-thinking delta
    REPORT_CHUNK = "report_chunk"            # streaming token inside <duct_report>
    SYNTHESIS_CHUNK = "synthesis_chunk"      # insights synthesis stream; legacy alias on audit

    # Terminal payloads
    REPORT_UPDATED = "report_updated"        # audit: a new versioned report
    PLAN_GENERATED = "plan_generated"        # content: 30-day plan
    POST_DRAFT_UPDATED = "post_draft_updated"  # content: a post draft
    PUBLISH_ASSESSMENT = "publish_assessment"  # content: pre-publish review (sanity + content score)


class EventKind(StrEnum):
    """Persisted conversation-event categories — the ``kind`` column on
    agent_events. Distinct from AgentEvent (the live SSE vocabulary): a small,
    stable set describing *what a stored turn is*, written by ConversationRecorder
    and replayed on resume.

    Kept a plain str enum — the DB column stays a free-text String, never a DB
    enum, so adding a kind needs no migration (see models/content/conversation.py).

    Contract with the frontend chat UI (served via routes/agents.py). Never
    change an existing value; only add members.
    """

    USER = "user"
    ASSISTANT = "assistant"
    THINKING = "thinking"
    QUESTION = "question"
    ANSWER = "answer"
    TOOL_USE = "tool_use"        # one per tool call: name + full input
    TOOL_RESULT = "tool_result"  # paired by tool_use_id: output + is_error


class StepStatus(StrEnum):
    """Lifecycle status carried on the ``status`` field of STEP_* events.

    Contract with the frontend (app/src/lib/agentSteps.js). Use ERROR for the
    failed state everywhere — audit historically used "error", content "failed";
    "error" is canonical.
    """

    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


class AgentStep(StrEnum):
    """Every ``step_id`` value used in STEP_STARTED / STEP_FINISHED events.

    Steps are agent-workflow stages; each agent uses the subset it needs.
    """

    # Audit
    RESOLVE_URL = "resolve_url"
    FETCH_SITEMAP = "fetch_sitemap"
    CRAWL_PAGES = "crawl_pages"
    SYNTHESIZE_AUDIT = "synthesize_audit"

    # Content
    LOAD_PROJECT = "load_project"
    LOAD_HISTORY = "load_history"
    LOAD_LIBRARIES = "load_libraries"
    SYNTHESIZE_PLAN = "synthesize_plan"
    LOAD_TOPIC = "load_topic"
    WRITE_COPY = "write_copy"
    BUILD_HTML = "build_html"
    WRITE_META = "write_meta"
    DISPATCH_SUBAGENT = "dispatch_subagent"

    # Insights
    COLLECT_SOURCE_DATA = "collect_source_data"
    NORMALIZE_CONNECTOR_OUTPUTS = "normalize_connector_outputs"
    SUPPLEMENTARY_FETCH = "supplementary_fetch"
    SYNTHESIZE_REPORT = "synthesize_report"
    ASSEMBLE_REPORT = "assemble_report"

    # Shared
    ENRICHING = "enriching"


STEP_LABELS: dict[AgentStep, str] = {
    # Audit
    AgentStep.RESOLVE_URL: "Resolving website",
    AgentStep.FETCH_SITEMAP: "Fetching sitemap",
    AgentStep.CRAWL_PAGES: "Crawling pages",
    AgentStep.SYNTHESIZE_AUDIT: "AI synthesis",
    # Content
    AgentStep.LOAD_PROJECT: "Loading project",
    AgentStep.LOAD_HISTORY: "Loading post history",
    AgentStep.LOAD_LIBRARIES: "Loading format + avatar libraries",
    AgentStep.SYNTHESIZE_PLAN: "Synthesizing 30-day plan",
    AgentStep.LOAD_TOPIC: "Loading topic + brand context",
    AgentStep.WRITE_COPY: "Writing slide copy",
    AgentStep.BUILD_HTML: "Building slide HTML",
    AgentStep.WRITE_META: "Writing post metadata",
    AgentStep.DISPATCH_SUBAGENT: "Sub-agent",
    # Insights
    AgentStep.COLLECT_SOURCE_DATA: "Collecting source data",
    AgentStep.NORMALIZE_CONNECTOR_OUTPUTS: "Normalizing connector outputs",
    AgentStep.SUPPLEMENTARY_FETCH: "Fetching supplementary data",
    AgentStep.SYNTHESIZE_REPORT: "Synthesizing report",
    AgentStep.ASSEMBLE_REPORT: "Assembling report",
    # Shared
    AgentStep.ENRICHING: "Researching competitors",
}
