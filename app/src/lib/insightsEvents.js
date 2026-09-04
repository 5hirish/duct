/**
 * Step IDs for the autonomous insights agent — mirror of backend
 * agents/core/events.py `AgentStep`. The event names are the shared
 * vocabulary in lib/agentEvents.js; `InsightsEvent` is that object.
 */

import { AgentEvent } from "./agentEvents";

export const InsightsEvent = AgentEvent;

/** Answer shapes, by the event that asked. The server resolves one Future for
 *  all three, so the client is what knows which shape belongs to which ask. */
/** step_id values the insights UI reacts to. Mirror of backend AgentStep. */
export const InsightsStep = Object.freeze({
  COLLECT_SOURCE_DATA: "collect_source_data",
});

export const ANSWER_SKIPPED = Object.freeze({ skipped: true });
