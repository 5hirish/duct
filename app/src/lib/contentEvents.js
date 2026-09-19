/**
 * Step IDs and labels for the Content Studio agent — mirror of backend
 * agents/content/events.py. The event names are the shared vocabulary in
 * lib/agentEvents.js; `ContentEvent` is that object.
 */

import { msg } from "@lingui/core/macro";
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

// Message descriptors, not strings: this table is module-level, so it is
// rendered with `i18n._(STEP_LABELS[id])` in the component that shows it.
export const STEP_LABELS = Object.freeze({
  [ContentStep.LOAD_PROJECT]:      msg`Loading project`,
  [ContentStep.LOAD_HISTORY]:      msg`Loading post history`,
  [ContentStep.LOAD_LIBRARIES]:    msg`Loading format + avatar libraries`,
  [ContentStep.ENRICHING]:         msg`Researching trends + history`,
  [ContentStep.SYNTHESIZE_PLAN]:   msg`Synthesizing 30-day plan`,
  [ContentStep.LOAD_TOPIC]:        msg`Loading topic + brand context`,
  [ContentStep.WRITE_COPY]:        msg`Writing slide copy`,
  [ContentStep.BUILD_HTML]:        msg`Building slide HTML`,
  [ContentStep.WRITE_META]:        msg`Writing post metadata`,
  [ContentStep.DISPATCH_SUBAGENT]: msg`Sub-agent`,
});
