"use client";

// When Duct may ask for a GitHub star (#539), on the rules iOS gives
// `SKStoreReviewController` for an App Store rating, made stricter: ask after
// the person has had a good experience, never on the first day, never in the
// middle of a task, and rarely. Stars are what put an open-source project in
// front of the next team, and the people best placed to give one are the ones
// Duct just helped; the same people are the ones a nag would cost us.
//
// THE TRIGGER is a run that made something and ended well, counted per run.
// Picked over "an applied change set" because it is the success the client can
// actually see for everyone: every agent makes artifacts (an audit report, a
// brief, a post, a plan), while change sets need a write connector, and in
// Auto posture the agent applies them on the server where no apply call ever
// crosses the client. The end of a run is a phase transition on the one
// reducer every workspace shares (lib/agentSession.js), so the moment lands
// after the run, never inside it. "Made something" uses the identity rule of
// the `artifact_generated` event (trackArtifact in hooks/useAgentSession.js),
// so the ask and the activation metric count the same thing; a run that
// writes a brief and three posts is still one good experience, not four.
//
// Per device, in localStorage, like lib/dailyReminder.js: the issue rules out
// server state for a nudge, and a second device asking once more is the cost
// of that, not a bug. Every access is guarded, and anything that cannot be
// read or written resolves to "never ask": the failure of a nudge should be
// silence. Words live in the component; this module decides only *whether*.

import { Phase } from "./agentPhase";

export const STAR_ASK_KEY = "duct_star_ask";

const DAY_MS = 24 * 60 * 60 * 1000;

/** Good runs before the first ask: once is luck, three is a habit forming. */
export const WINS_BEFORE_ASKING = 3;
/** Never on the first day of use, counted from the first time this device ran the app shell. */
export const FIRST_DAY_MS = DAY_MS;
/** After a showing, ignored or dismissed, the next one waits this long. */
export const COOLDOWN_MS = 60 * DAY_MS;
/** At most two showings, ever. */
export const MAX_SHOWINGS = 2;
/** The second "Not now" (or ✕) is final. */
export const MAX_DISMISSALS = 2;
/**
 * How long after a run ends before asking: enough to read the first lines of
 * what it made. Asking the instant a brief lands competes with the brief.
 */
export const SETTLE_MS = 8000;
/** How long the thank-you stays once the person is back in the window. */
export const THANKS_MS = 4000;
/**
 * The ask's footprint at the bottom-right corner, for the "never over the box
 * you type in" rule: the card's width cap (CornerNotice's 22rem), its inset,
 * and a height that holds its tallest state, German with the actions stacked
 * and grown to 44px for a finger (15.25rem measured).
 */
export const NOTICE_FOOTPRINT_REM = Object.freeze({ width: 22, height: 16, inset: 1 });

/** What a workspace says about its run, on `RUN_EVENT`. */
export const RunMoment = Object.freeze({
  STARTED: "started", // a run went live: anything pending waits for the next one
  WON: "won",         // a run made something and ended well
  ENDED: "ended",     // a run ended any other way
});
export const RUN_EVENT = "duct:agent-run";

/** Why the ask is not shown right now. `null` from `askBlocker` means it may be. */
export const AskBlock = Object.freeze({
  STORAGE: "storage",       // localStorage unreadable, unwritable or corrupt
  STARRED: "starred",       // they went to star it, from the notice or the menu
  DISMISSALS: "dismissals", // said no twice
  SHOWINGS: "showings",     // shown twice already
  WINS: "wins",             // not enough good runs yet
  FIRST_DAY: "first_day",
  COOLDOWN: "cooldown",
  LIVE: "live",             // a run is in progress, here or detached
  CORNER: "corner",         // another notice holds the corner, and outranks a request
  COMPOSER: "composer",     // the card would sit over the message box
});

// A question asked of the person (a pause) is the middle of a task too.
const LIVE_PHASES = new Set([Phase.PIPELINE, Phase.CHATTING, Phase.QUESTIONS]);

const EMPTY = Object.freeze({
  firstSeenAt: 0,
  wins: 0,
  shown: 0,
  shownAt: 0,
  dismissed: 0,
  dismissedAt: 0,
  starredAt: 0,
});
const UNAVAILABLE = Object.freeze({ ...EMPTY, unavailable: true });

function store() {
  try {
    return typeof window !== "undefined" ? window.localStorage ?? null : null;
  } catch {
    // Private mode / storage disabled: the accessor itself can throw.
    return null;
  }
}

/** The stored state, or one that blocks every ask when it cannot be trusted. */
export function readStarAsk() {
  const storage = store();
  if (!storage) return UNAVAILABLE;
  try {
    const raw = storage.getItem(STAR_ASK_KEY);
    if (raw == null) return EMPTY;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return UNAVAILABLE;
    const state = {};
    for (const key of Object.keys(EMPTY)) {
      const n = Number(parsed[key]);
      state[key] = Number.isFinite(n) && n > 0 ? n : 0;
    }
    return state;
  } catch {
    // A value no build of ours wrote. Starting over could ask someone who
    // already starred, so it blocks instead.
    return UNAVAILABLE;
  }
}

/** Write the whole state. False when it did not stick, so the caller can stay quiet. */
export function writeStarAsk(state) {
  const storage = store();
  if (!storage || state?.unavailable) return false;
  try {
    const next = {};
    for (const key of Object.keys(EMPTY)) next[key] = state[key] || 0;
    storage.setItem(STAR_ASK_KEY, JSON.stringify(next));
    return true;
  } catch {
    return false;
  }
}

// Transitions are pure, state in and state out, so every rule is testable
// without storage.

export function withFirstSeen(state, now) {
  return state.firstSeenAt ? state : { ...state, firstSeenAt: now };
}

export function withWin(state, now) {
  return { ...withFirstSeen(state, now), wins: state.wins + 1 };
}

export function withShown(state, now) {
  return { ...state, shown: state.shown + 1, shownAt: now };
}

export function withDismissed(state, now) {
  return { ...state, dismissed: state.dismissed + 1, dismissedAt: now };
}

export function withStarred(state, now) {
  return { ...state, starredAt: state.starredAt || now };
}

/**
 * Why Duct may not ask now, or null when it may. Rules first, in the order a
 * reader would check them, then the two that depend on the screen.
 */
export function askBlocker(state, { now, live = false, cornerTaken = false, coversComposer = false } = {}) {
  if (!state || state.unavailable) return AskBlock.STORAGE;
  if (state.starredAt) return AskBlock.STARRED;
  if (state.dismissed >= MAX_DISMISSALS) return AskBlock.DISMISSALS;
  if (state.shown >= MAX_SHOWINGS) return AskBlock.SHOWINGS;
  if (state.wins < WINS_BEFORE_ASKING) return AskBlock.WINS;
  if (!state.firstSeenAt || now - state.firstSeenAt < FIRST_DAY_MS) return AskBlock.FIRST_DAY;
  const last = Math.max(state.shownAt, state.dismissedAt);
  if (last && now - last < COOLDOWN_MS) return AskBlock.COOLDOWN;
  if (live) return AskBlock.LIVE;
  if (cornerTaken) return AskBlock.CORNER;
  if (coversComposer) return AskBlock.COMPOSER;
  return null;
}

/** A blocker that clears on its own while the app stays open, so a pending ask waits it out. */
export function isTransient(block) {
  return block === AskBlock.COMPOSER;
}

/** The moment a phase change marks, if any. `made`: the run produced an artifact. */
export function runMoment(previous, next, made) {
  const was = LIVE_PHASES.has(previous);
  const is = LIVE_PHASES.has(next);
  if (!was && is) return RunMoment.STARTED;
  if (was && !is) return next === Phase.READY && made ? RunMoment.WON : RunMoment.ENDED;
  return null;
}

/** Do two `{ left, top, right, bottom }` boxes share any area. */
export function boxesOverlap(a, b) {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

/** Where the ask would sit in a `{ width, height }` viewport, given the root font size in px. */
export function noticeBox(viewport, remPx = 16) {
  const { width, height, inset } = NOTICE_FOOTPRINT_REM;
  const w = Math.min(width * remPx, viewport.width - 2 * inset * remPx);
  const right = viewport.width - inset * remPx;
  const bottom = viewport.height - inset * remPx;
  return { left: right - w, top: bottom - height * remPx, right, bottom };
}

function update(change, now) {
  const state = readStarAsk();
  if (state.unavailable) return null;
  const next = change(state, now);
  return writeStarAsk(next) ? next : null;
}

/** First run of the app shell on this device; later calls keep the first date. */
export function noteFirstSeen(now = Date.now()) {
  return update(withFirstSeen, now);
}

/** True only when the showing was recorded: an ask that cannot be counted is not shown. */
export function noteShown(now = Date.now()) {
  return update(withShown, now) !== null;
}

export function noteDismissed(now = Date.now()) {
  return update(withDismissed, now);
}

export function noteStarred(now = Date.now()) {
  return update(withStarred, now);
}

/**
 * A workspace reports a moment of its run. A win is counted here, whoever is
 * listening, so the count does not depend on the notice being mounted.
 */
export function announceRun(moment, now = Date.now()) {
  if (!moment) return;
  if (moment === RunMoment.WON) update(withWin, now);
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
    window.dispatchEvent(new CustomEvent(RUN_EVENT, { detail: { moment } }));
  }
}
