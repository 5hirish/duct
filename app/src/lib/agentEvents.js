/**
 * The SSE vocabulary every agent speaks — mirror of backend
 * agents/core/events.py `AgentEvent`. One enum backend-side, so one here: the
 * per-agent files (auditEvents, contentEvents, insightsEvents) re-export this
 * and add only their own step ids and labels.
 *
 * Never change an existing value; only add members. The legacy names at the
 * bottom are wire values the backend no longer emits, kept so an app deployed
 * ahead of the backend keeps rendering (deploy order is app, then backend).
 */
export const AgentEvent = Object.freeze({
  PIPELINE_STARTED:    "pipeline_started",
  PIPELINE_FINISHED:   "pipeline_finished",
  PIPELINE_FAILED:     "pipeline_failed",

  STEP_STARTED:        "step_started",
  STEP_FINISHED:       "step_finished",
  STEP_FAILED:         "step_failed",

  // Pauses. All three park the run until the user answers through the same
  // endpoint; they differ only in the card the UI renders.
  QUESTIONS_REQUIRED:         "questions_required",
  CONNECTION_REQUIRED:        "connection_required",
  ACCOUNT_SELECTION_REQUIRED: "account_selection_required",
  SLIDE_RENDER_REQUESTED:     "slide_render_requested",

  TODO_UPDATE:         "todo_update",

  AGENT_MESSAGE_CHUNK: "agent_message_chunk",
  AGENT_MESSAGE:       "agent_message",
  MESSAGE_STOP:        "message_stop",
  THINKING_CHUNK:      "thinking_chunk",
  ARTIFACT_CHUNK:      "artifact_chunk",
  SYNTHESIS_CHUNK:     "synthesis_chunk",

  ARTIFACT_VERSION:    "artifact_version",
  PLAN_GENERATED:      "plan_generated",
  POST_DRAFT_UPDATED:  "post_draft_updated",
  ARTIFACT_UPDATED:    "artifact_updated",
  EXECUTION_PROPOSED:  "execution_proposed",

  MEMORY_WRITTEN:      "memory_written",
  MEMORY_RECALLED:     "memory_recalled",

  LEGACY_REPORT_UPDATED: "report_updated",
  LEGACY_REPORT_CHUNK:   "report_chunk",
});

/** The events that park a run. `pending` in the session state is one of these. */
export const PAUSE_EVENTS = Object.freeze([
  AgentEvent.QUESTIONS_REQUIRED,
  AgentEvent.CONNECTION_REQUIRED,
  AgentEvent.ACCOUNT_SELECTION_REQUIRED,
]);
