// Whether a review the person asked for is still under way, read off the
// post's score and the agent's state, never off a timer alone.
//
// The Review tab said "Reviewing this post…" until the score's timestamp
// moved, and nothing else ended it, so a review that never arrived spun
// forever (2026-11-27): the API restarted under a live run, the turn died
// with no new score, and the tab waited on a score that was never coming.
// Now the wait ends one of four ways: the score lands, the turn ends
// without one, the run fails, or the turn never starts.

/** How long a sent request may sit before the agent starts on it. */
export const START_WINDOW_MS = 20_000;

export const ReviewStop = Object.freeze({
  NONE: "",
  ENDED: "ended",            // the turn finished and no new score came
  FAILED: "failed",          // the run failed
  NOT_STARTED: "not_started", // the message never reached a working agent
});

export const REVIEW_IDLE = Object.freeze({ askedAt: "", started: false, since: 0, stopped: ReviewStop.NONE });

/** The person asked for a review of a post scored at `scoredAt` ("" if never). */
export function reviewAsked(scoredAt, now) {
  return { askedAt: scoredAt || "none", started: false, since: now, stopped: ReviewStop.NONE };
}

/**
 * The next state, given what the agent and the post look like now:
 * `idle` (the agent is waiting on the person), `failed` (the run failed),
 * `scoredAt` (the post's current score time) and `now`.
 */
export function reviewTick(state, { idle, failed, scoredAt, now }) {
  if (!state.askedAt) return state;
  if ((scoredAt || "none") !== state.askedAt) return REVIEW_IDLE;
  const stop = (stopped) => ({ ...REVIEW_IDLE, stopped });
  if (failed) return stop(ReviewStop.FAILED);
  if (!idle) return state.started ? state : { ...state, started: true };
  if (state.started) return stop(ReviewStop.ENDED);
  if (now - state.since >= START_WINDOW_MS) return stop(ReviewStop.NOT_STARTED);
  return state;
}

export const isReviewing = (state) => Boolean(state.askedAt);
