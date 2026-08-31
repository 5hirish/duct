/**
 * SSE event names for the autonomous insights agent.
 * Mirror of backend agents/core/events.py — keep in sync.
 *
 * The vocabulary is shared across agents by design (one enum backend-side), so
 * this file overlaps `auditEvents.js` almost entirely. The two names below are
 * the ones insights added, and they are the reason the wizard is going away:
 * the agent can now stop mid-run and ask for a connector or an account instead
 * of requiring the user to have decided both before it starts.
 */

export const InsightsEvent = Object.freeze({
  PIPELINE_STARTED:    "pipeline_started",
  PIPELINE_FINISHED:   "pipeline_finished",
  PIPELINE_FAILED:     "pipeline_failed",

  STEP_STARTED:        "step_started",
  // The insights runner emits one STEP_FINISHED per data pull, carrying
  // step_id "collect_source_data" and a label naming the entity and the window
  // it covers — which is what the right pane lists.
  STEP_FINISHED:       "step_finished",
  STEP_FAILED:         "step_failed",

  // Human-in-the-loop. All three park the run on the server until the user
  // responds through POST .../messages with type "answer"; they differ only in
  // the card the user sees and the shape of the answer they send back.
  QUESTIONS_REQUIRED:  "questions_required",
  CONNECTION_REQUIRED: "connection_required",
  ACCOUNT_SELECTION_REQUIRED: "account_selection_required",

  TODO_UPDATE:         "todo_update",

  AGENT_MESSAGE_CHUNK: "agent_message_chunk",
  MESSAGE_STOP:        "message_stop",
  THINKING_CHUNK:      "thinking_chunk",
  ARTIFACT_CHUNK:      "artifact_chunk",

  ARTIFACT_VERSION:    "artifact_version",
  ARTIFACT_UPDATED:    "artifact_updated",
  EXECUTION_PROPOSED:  "execution_proposed",

  MEMORY_WRITTEN:      "memory_written",
  MEMORY_RECALLED:     "memory_recalled",
});

/** Answer shapes, by the event that asked. The server resolves one Future for
 *  all three, so the client is what knows which shape belongs to which ask. */
/** step_id values the insights UI reacts to. Mirror of backend AgentStep. */
export const InsightsStep = Object.freeze({
  COLLECT_SOURCE_DATA: "collect_source_data",
});

export const ANSWER_SKIPPED = Object.freeze({ skipped: true });
