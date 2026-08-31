/**
 * The lifecycle every agent workspace moves through. Shared because it is the
 * agent protocol, not one agent's opinion: audit and content each had a private
 * byte-identical copy, so a new phase had to be added twice or the two drifted.
 */
export const Phase = {
  STARTING:  "starting",
  PIPELINE:  "pipeline",
  QUESTIONS: "questions",
  READY:     "ready",
  CHATTING:  "chatting",
  FAILED:    "failed",
};
