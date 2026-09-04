"""Canonical SSE event + step vocabulary, shared by every agent type.

One enum so the frontend speaks a single language across audit, content,
insights, and any future agent. An agent simply never emits events/steps it
doesn't support — there is no per-agent enum. Per-agent modules
(agents/audit/events.py, agents/content/events.py) re-export these names for
backwards compatibility.

IMPORTANT: the string values are a contract with the frontend
(app/src/lib/auditEvents.js, app/src/lib/contentEvents.js). Never change an
existing value; only add new members.

The one deliberate exception: ``report_chunk`` → ``artifact_chunk`` and
``report_updated`` → ``artifact_version``. "Report" was audit-specific
vocabulary sitting on a mechanism every agent uses — content streams plans and
post drafts through the same tag, and the artifact store versions all of them
alike. The Python names are gone outright — nothing in the tree referenced them, and
a deprecated alias nobody uses is just a second name to keep true. Only the
*frontend* still accepts both strings, which is what makes the migration:

    deploy the app first, then the backend.

An older app meeting a newer backend is the only broken pairing, and that
ordering removes it. Drop the frontend's legacy branches once both are out.
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

    # Human-in-the-loop. All three park the run on the same asyncio.Future and
    # resume through the same messages endpoint; they differ only in what the
    # UI must render to collect the answer — a question, a connect button, or
    # an account picker.
    QUESTIONS_REQUIRED = "questions_required"
    # The agent needs a connector the project has not connected. Payload carries
    # connector_id, label, why, and an authorize_url for OAuth connectors.
    # Answering with {"skipped": true} is a first-class outcome: the run
    # continues and says what it could not see.
    CONNECTION_REQUIRED = "connection_required"
    # The connector is connected but the project has not chosen WHICH account,
    # property or site. Payload carries the candidates.
    ACCOUNT_SELECTION_REQUIRED = "account_selection_required"
    SLIDE_RENDER_REQUESTED = "slide_render_requested"  # agent asks the browser to rasterize a slide

    # Progress / todos
    TODO_UPDATE = "todo_update"

    # Streaming model output
    AGENT_MESSAGE_CHUNK = "agent_message_chunk"
    AGENT_MESSAGE = "agent_message"
    MESSAGE_STOP = "message_stop"
    THINKING_CHUNK = "thinking_chunk"        # model extended-thinking delta
    ARTIFACT_CHUNK = "artifact_chunk"        # streaming token inside <duct_artifact>
    SYNTHESIS_CHUNK = "synthesis_chunk"      # insights synthesis stream; legacy alias on audit

    # Terminal payloads
    #
    # Two artifact events, deliberately distinct:
    #   ARTIFACT_VERSION — a new *version* of the session's primary artifact,
    #     carrying the full payload + version_id + label. The artifact store
    #     intercepts it and persists the version (service/artifact_store.py).
    #   ARTIFACT_UPDATED — a compact *card* for the chat transcript, for any
    #     artifact. No payload, no version semantics.
    ARTIFACT_VERSION = "artifact_version"    # new version of the primary artifact
    PLAN_GENERATED = "plan_generated"        # content: 30-day plan
    POST_DRAFT_UPDATED = "post_draft_updated"  # content: a post draft
    ARTIFACT_UPDATED = "artifact_updated"    # generic artifact created/revised (card in chat)
    # Staged execution: a change-set card for the chat UI. Emitted when the
    # agent proposes a set AND when its state changes (auto-applied, rolled
    # back) — the UI upserts by change_set_id.
    EXECUTION_PROPOSED = "execution_proposed"

    # Memory (project_memories). MEMORY_WRITTEN carries the entries a turn
    # stored — the quiet "Remembered: …" line, with undo. MEMORY_RECALLED
    # carries the ids a turn was primed with, which the UI renders as chips
    # linking back to the source.
    MEMORY_WRITTEN = "memory_written"
    MEMORY_RECALLED = "memory_recalled"

    # The model call failed and is being retried — status, not an error. The
    # payload carries attempt / max_attempts / code so the UI can say
    # "Reconnecting to the model (2/4)" in the status row and go back to
    # "Working" when the next token arrives. A failure that has run out of
    # attempts arrives as STEP_FAILED / PIPELINE_FAILED with its ``code``
    # (agents/core/errors.py).
    MODEL_RETRYING = "model_retrying"

    # One model call's token bill, emitted as each call completes: input /
    # output / cached tokens plus the model's context window, so the UI can
    # show how full the context is and what a turn cost. The UI keeps the
    # running total; a resumed thread reads its last usage from the state route.
    TOKEN_USAGE = "token_usage"
    # The harness is summarising old history to make room, and then did. The
    # summariser's own tokens never reach the transcript — the first is what
    # the status row shows instead, the second leaves a quiet note behind.
    CONTEXT_COMPACTING = "context_compacting"
    CONTEXT_COMPACTED = "context_compacted"

    # A message the user sent while a turn was running has now been handed to
    # the model — steered in at a model-call boundary, or dequeued for the next
    # turn. Carries the client_message_id the client stamped on it, so the
    # "queued" mark on that row can come off.
    USER_INPUT_CONSUMED = "user_input_consumed"


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


# ---------------------------------------------------------------------------
# AG-UI alignment (agents/core/ports — the "events out" port)
# ---------------------------------------------------------------------------
#
# AG-UI (https://docs.ag-ui.com) is the emerging standard for agent→frontend
# event streams: ~30 typed events over SSE/WebSocket. Duct's vocabulary predates
# it and largely agrees with it — STEP_STARTED/STEP_FINISHED are already
# name-for-name identical.
#
# We map rather than rename, deliberately:
#
#   * Renaming `agent_message_chunk` → `text_message_content` would break every
#     consumer to buy nothing. The wire value is an internal contract; what has
#     to be portable is the *meaning*, and a mapping carries that exactly.
#   * Roughly half of Duct's events are domain events (artifacts, memory,
#     staged execution) that no protocol will ever cover. AG-UI's answer for
#     those is `Custom` — so "aligning" them would mean flattening real meaning
#     into a generic envelope. Contorting domain events to fit a standard is the
#     same mistake as contorting them to fit an SDK.
#
# This table is the whole adapter. A future AG-UI endpoint is a ~30-line
# translation over it, not a refactor. Keep it exhaustive: the boundary test in
# tests/test_harness_boundaries.py fails if an AgentEvent is missing here.

AG_UI_EVENT: dict[AgentEvent, str] = {
    # Lifecycle — exact matches
    AgentEvent.PIPELINE_STARTED:      "RunStarted",
    AgentEvent.PIPELINE_FINISHED:     "RunFinished",
    AgentEvent.PIPELINE_FAILED:       "RunError",
    AgentEvent.STEP_STARTED:          "StepStarted",
    AgentEvent.STEP_FINISHED:         "StepFinished",
    # AG-UI has no StepFailed; failure rides in the payload's `status` field
    # (StepStatus.ERROR), which is how AG-UI models step outcomes too.
    AgentEvent.STEP_FAILED:           "StepFinished",

    # Streaming text + reasoning
    AgentEvent.AGENT_MESSAGE_CHUNK:   "TextMessageContent",
    AgentEvent.AGENT_MESSAGE:         "TextMessageChunk",
    AgentEvent.MESSAGE_STOP:          "TextMessageEnd",
    AgentEvent.THINKING_CHUNK:        "ReasoningMessageContent",
    AgentEvent.SYNTHESIS_CHUNK:       "TextMessageContent",

    # Progress. Todos are an activity feed in AG-UI's model, and TodoWrite
    # always ships the full list, so the snapshot form is the right one.
    AgentEvent.TODO_UPDATE:           "ActivitySnapshot",

    # Domain events — Custom is AG-UI's escape hatch and the honest answer.
    AgentEvent.QUESTIONS_REQUIRED:    "Custom",
    AgentEvent.CONNECTION_REQUIRED:   "Custom",
    AgentEvent.ACCOUNT_SELECTION_REQUIRED: "Custom",
    AgentEvent.SLIDE_RENDER_REQUESTED: "Custom",
    AgentEvent.ARTIFACT_CHUNK:        "Custom",
    AgentEvent.ARTIFACT_VERSION:      "Custom",
    AgentEvent.ARTIFACT_UPDATED:      "Custom",
    AgentEvent.PLAN_GENERATED:        "Custom",
    AgentEvent.POST_DRAFT_UPDATED:    "Custom",
    AgentEvent.EXECUTION_PROPOSED:    "Custom",
    AgentEvent.MEMORY_WRITTEN:        "Custom",
    AgentEvent.MEMORY_RECALLED:       "Custom",
    AgentEvent.MODEL_RETRYING:        "Custom",
    AgentEvent.TOKEN_USAGE:           "Custom",
    AgentEvent.CONTEXT_COMPACTING:    "Custom",
    AgentEvent.CONTEXT_COMPACTED:     "Custom",
    AgentEvent.USER_INPUT_CONSUMED:   "Custom",
}

# Persisted conversation kinds → AG-UI. Only the tool kinds have real analogues;
# the rest are message roles AG-UI carries in MessagesSnapshot rather than as
# their own events.
AG_UI_EVENT_KIND: dict[EventKind, str] = {
    EventKind.USER:        "MessagesSnapshot",
    EventKind.ASSISTANT:   "MessagesSnapshot",
    EventKind.THINKING:    "ReasoningMessageContent",
    EventKind.QUESTION:    "Custom",
    EventKind.ANSWER:      "Custom",
    EventKind.TOOL_USE:    "ToolCallStart",
    EventKind.TOOL_RESULT: "ToolCallResult",
}
