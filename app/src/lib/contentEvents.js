/**
 * Step IDs and labels for the Content Studio agent — mirror of backend
 * agents/content/events.py. The event names are the shared vocabulary in
 * lib/agentEvents.js; `ContentEvent` is that object.
 */

import { AgentEvent } from "./agentEvents";

export const ContentEvent = AgentEvent;

export const ContentStep = Object.freeze({
  LOAD_PROJECT:      "load_project",
  LOAD_HISTORY:      "load_history",
  LOAD_LIBRARIES:    "load_libraries",
  ENRICHING:         "enriching",
  SYNTHESIZE_PLAN:   "synthesize_plan",

  LOAD_TOPIC:        "load_topic",
  WRITE_COPY:        "write_copy",
  BUILD_HTML:        "build_html",
  WRITE_META:        "write_meta",

  DISPATCH_SUBAGENT: "dispatch_subagent",
});

export const STEP_LABELS = Object.freeze({
  [ContentStep.LOAD_PROJECT]:      "Loading project",
  [ContentStep.LOAD_HISTORY]:      "Loading post history",
  [ContentStep.LOAD_LIBRARIES]:    "Loading format + avatar libraries",
  [ContentStep.ENRICHING]:         "Researching trends + history",
  [ContentStep.SYNTHESIZE_PLAN]:   "Synthesizing 30-day plan",
  [ContentStep.LOAD_TOPIC]:        "Loading topic + brand context",
  [ContentStep.WRITE_COPY]:        "Writing slide copy",
  [ContentStep.BUILD_HTML]:        "Building slide HTML",
  [ContentStep.WRITE_META]:        "Writing post metadata",
  [ContentStep.DISPATCH_SUBAGENT]: "Sub-agent",
});
