/**
 * The lifecycle every agent workspace moves through. Shared because it is the
 * agent protocol, not one agent's opinion: audit and content each had a private
 * byte-identical copy, so a new phase had to be added twice or the two drifted.
 *
 * Lives in lib/ (not components/) because the session reducer runs with no
 * React at all — that is what makes it testable against recorded streams.
 */
export const Phase = Object.freeze({
  STARTING:  "starting",   // session being created / stream attaching
  PIPELINE:  "pipeline",   // the opening run is working
  QUESTIONS: "questions",  // parked on a pause — a question, a connect offer, an account pick
  READY:     "ready",      // idle, input open
  CHATTING:  "chatting",   // a follow-up turn is in flight
  FAILED:    "failed",     // terminal — retry starts over
});
