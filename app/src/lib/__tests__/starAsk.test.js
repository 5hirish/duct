import { beforeEach, describe, expect, it } from "vitest";
import { Phase } from "../agentPhase.js";
import {
  AskBlock,
  COOLDOWN_MS,
  FIRST_DAY_MS,
  MAX_SHOWINGS,
  RUN_EVENT,
  RunMoment,
  STAR_ASK_KEY,
  WINS_BEFORE_ASKING,
  announceRun,
  askBlocker,
  boxesOverlap,
  isTransient,
  noteDismissed,
  noteFirstSeen,
  noteShown,
  noteStarred,
  noticeBox,
  readStarAsk,
  runMoment,
  withDismissed,
  withShown,
  withStarred,
  withWin,
  writeStarAsk,
} from "../starAsk.js";

const DAY = 24 * 60 * 60 * 1000;
const T0 = Date.UTC(2026, 10, 1, 9, 0);

/** Someone a week in with three good runs and no ask yet: the one who may be asked. */
function ready(overrides = {}) {
  return {
    firstSeenAt: T0,
    wins: WINS_BEFORE_ASKING,
    shown: 0,
    shownAt: 0,
    dismissed: 0,
    dismissedAt: 0,
    starredAt: 0,
    ...overrides,
  };
}
const LATER = T0 + 7 * DAY;

function memoryStorage() {
  const data = new Map();
  return {
    data,
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
  };
}

describe("when Duct may ask for a star", () => {
  it("asks a week-old user after three good runs", () => {
    expect(askBlocker(ready(), { now: LATER })).toBeNull();
  });

  it("waits for three good runs", () => {
    expect(askBlocker(ready({ wins: WINS_BEFORE_ASKING - 1 }), { now: LATER })).toBe(AskBlock.WINS);
  });

  it("never asks on the first day of use", () => {
    const state = ready();
    expect(askBlocker(state, { now: T0 + FIRST_DAY_MS - 1 })).toBe(AskBlock.FIRST_DAY);
    expect(askBlocker(state, { now: T0 + FIRST_DAY_MS })).toBeNull();
    // No first-seen date at all reads as day one, not as long ago.
    expect(askBlocker(ready({ firstSeenAt: 0 }), { now: LATER })).toBe(AskBlock.FIRST_DAY);
  });

  it("never asks while a run is live", () => {
    expect(askBlocker(ready(), { now: LATER, live: true })).toBe(AskBlock.LIVE);
  });

  it("never asks again after Star, even with every other rule passing", () => {
    const starred = withStarred(ready(), LATER);
    expect(askBlocker(starred, { now: LATER + 365 * DAY })).toBe(AskBlock.STARRED);
  });

  it("waits 60 days after a dismissal", () => {
    const once = withDismissed(withShown(ready(), LATER), LATER);
    expect(askBlocker(once, { now: LATER + COOLDOWN_MS - 1 })).toBe(AskBlock.COOLDOWN);
    expect(askBlocker(once, { now: LATER + COOLDOWN_MS })).toBeNull();
  });

  it("waits 60 days after a showing nobody answered, too", () => {
    const ignored = withShown(ready(), LATER);
    expect(askBlocker(ignored, { now: LATER + COOLDOWN_MS - 1 })).toBe(AskBlock.COOLDOWN);
  });

  it("never asks after the second dismissal", () => {
    // Two dismissals without two recorded showings (an older state, a lost
    // write) still settle it.
    const twice = withDismissed(withDismissed(ready({ shown: 1 }), LATER), LATER);
    expect(askBlocker(twice, { now: LATER + 10 * COOLDOWN_MS })).toBe(AskBlock.DISMISSALS);
  });

  it("shows at most twice, ever", () => {
    let state = ready();
    for (let i = 0; i < MAX_SHOWINGS; i += 1) state = withShown(state, LATER);
    expect(askBlocker(state, { now: LATER + 10 * COOLDOWN_MS })).toBe(AskBlock.SHOWINGS);
  });

  it("yields the corner to any other notice", () => {
    expect(askBlocker(ready(), { now: LATER, cornerTaken: true })).toBe(AskBlock.CORNER);
  });

  it("never sits over the message box, and waits that out rather than giving up", () => {
    const block = askBlocker(ready(), { now: LATER, coversComposer: true });
    expect(block).toBe(AskBlock.COMPOSER);
    expect(isTransient(block)).toBe(true);
    expect(isTransient(AskBlock.FIRST_DAY)).toBe(false);
    expect(isTransient(AskBlock.LIVE)).toBe(false);
  });

  it("counts a win and keeps the first date it saw", () => {
    const first = withWin(ready({ firstSeenAt: 0, wins: 0 }), T0);
    expect(first).toMatchObject({ wins: 1, firstSeenAt: T0 });
    expect(withWin(first, LATER)).toMatchObject({ wins: 2, firstSeenAt: T0 });
  });
});

describe("what counts as a moment", () => {
  it("marks a run going live", () => {
    expect(runMoment(Phase.READY, Phase.CHATTING, false)).toBe(RunMoment.STARTED);
    expect(runMoment(Phase.STARTING, Phase.PIPELINE, false)).toBe(RunMoment.STARTED);
  });

  it("is a win only when the run made something and ended ready", () => {
    expect(runMoment(Phase.PIPELINE, Phase.READY, true)).toBe(RunMoment.WON);
    expect(runMoment(Phase.CHATTING, Phase.READY, true)).toBe(RunMoment.WON);
    expect(runMoment(Phase.CHATTING, Phase.READY, false)).toBe(RunMoment.ENDED);
    expect(runMoment(Phase.PIPELINE, Phase.FAILED, true)).toBe(RunMoment.ENDED);
  });

  it("treats a question to the person as the middle of the task", () => {
    expect(runMoment(Phase.PIPELINE, Phase.QUESTIONS, true)).toBeNull();
    expect(runMoment(Phase.QUESTIONS, Phase.CHATTING, true)).toBeNull();
    expect(runMoment(Phase.QUESTIONS, Phase.READY, true)).toBe(RunMoment.WON);
  });

  it("does not count a stored thread opening as a run", () => {
    expect(runMoment(Phase.STARTING, Phase.READY, true)).toBeNull();
    expect(runMoment(Phase.READY, Phase.READY, true)).toBeNull();
  });
});

describe("the message-box rule", () => {
  const phone = { width: 390, height: 844 };

  it("sees the ask over a composer that spans the bottom of a phone", () => {
    const composer = { left: 0, top: 724, right: 390, bottom: 844 };
    expect(boxesOverlap(noticeBox(phone), composer)).toBe(true);
  });

  it("leaves a composer in the left pane of a split workspace alone", () => {
    const wide = { width: 1440, height: 900 };
    const leftPane = { left: 256, top: 780, right: 840, bottom: 900 };
    expect(boxesOverlap(noticeBox(wide), leftPane)).toBe(false);
  });

  it("keeps the card inside a narrow window", () => {
    // 22rem is wider than a 360px window less its two 1rem insets.
    const box = noticeBox({ width: 360, height: 640 });
    expect(box.left).toBe(16);
    expect(box.right).toBe(344);
  });
});

describe("the stored state", () => {
  let storage;
  beforeEach(() => {
    storage = memoryStorage();
    const events = [];
    globalThis.window = {
      localStorage: storage,
      events,
      dispatchEvent: (e) => events.push(e),
    };
  });

  it("starts empty and records each step", () => {
    expect(readStarAsk()).toMatchObject({ wins: 0, shown: 0, starredAt: 0 });
    noteFirstSeen(T0);
    noteFirstSeen(LATER);
    expect(readStarAsk().firstSeenAt).toBe(T0);
    expect(noteShown(LATER)).toBe(true);
    noteDismissed(LATER);
    noteStarred(LATER + 1);
    expect(readStarAsk()).toMatchObject({ shown: 1, shownAt: LATER, dismissed: 1, starredAt: LATER + 1 });
  });

  it("counts a win when a workspace announces one, and tells the listener", () => {
    announceRun(RunMoment.WON, T0);
    announceRun(RunMoment.ENDED, T0);
    announceRun(RunMoment.WON, T0);
    expect(readStarAsk().wins).toBe(2);
    expect(window.events.map((e) => [e.type, e.detail.moment])).toEqual([
      [RUN_EVENT, RunMoment.WON],
      [RUN_EVENT, RunMoment.ENDED],
      [RUN_EVENT, RunMoment.WON],
    ]);
  });

  it("blocks every ask when the value cannot be trusted, and never writes over it", () => {
    storage.setItem(STAR_ASK_KEY, "{not json");
    expect(askBlocker(readStarAsk(), { now: LATER })).toBe(AskBlock.STORAGE);
    expect(noteShown(LATER)).toBe(false);
    expect(storage.getItem(STAR_ASK_KEY)).toBe("{not json");
  });

  it("drops a field that is not a number rather than trusting it", () => {
    storage.setItem(STAR_ASK_KEY, JSON.stringify({ ...ready(), wins: "lots", starredAt: -5 }));
    expect(readStarAsk()).toMatchObject({ wins: 0, starredAt: 0, firstSeenAt: T0 });
  });

  it("never asks when storage throws on read", () => {
    globalThis.window = {
      get localStorage() {
        throw new Error("SecurityError");
      },
    };
    expect(askBlocker(readStarAsk(), { now: LATER })).toBe(AskBlock.STORAGE);
    expect(noteShown(LATER)).toBe(false);
  });

  it("does not show an ask it could not count", () => {
    writeStarAsk(ready());
    storage.setItem = () => {
      throw new Error("QuotaExceededError");
    };
    expect(noteShown(LATER)).toBe(false);
  });

  it("has nothing to say outside a browser", () => {
    delete globalThis.window;
    expect(askBlocker(readStarAsk(), { now: LATER })).toBe(AskBlock.STORAGE);
    expect(() => announceRun(RunMoment.WON)).not.toThrow();
  });
});
