/**
 * What a plan bets on, channel by channel, read from its own days and from
 * the facts its channel mix stored (`strategy.mix`, backend
 * agents/content/channel_mix.py `mix_snapshot`).
 *
 * The strategy's sentences are the agent's and name one channel at best, so
 * a three-channel plan used to say "Scaling Video" over a LinkedIn list made
 * of text. The rows here are code's: what each channel's days are, what its
 * own history says to lean on and to try, and how its share moved since the
 * last plan. Pure, so the board, the chat pane and the tests agree.
 */
import { dayPlatforms } from "@/lib/contentSchedule";

const STRATEGY_FIELDS = [
  "exploit", "exploit_evidence", "explore", "explore_evidence", "lesson", "best_times", "experiment", "review_notes",
];

/** A channel against the middle channel on the goal per post (channel_mix.py). */
export const Standing = Object.freeze({
  LEADS: "leads",
  HOLDS: "holds",
  TRAILS: "trails",
  UNTESTED: "untested",
});

/** What "earned" means for the brand (channel_mix.py GoalKind). */
export const GoalKind = Object.freeze({
  REACH: "reach",
  ENGAGEMENT: "engagement",
  INTENT: "intent",
});

/** True when a plan recorded any strategy. Plans made before #224 carry `{}`. */
export function hasStrategy(strategy) {
  return (
    STRATEGY_FIELDS.some((k) => typeof strategy?.[k] === "string" && strategy[k].trim()) ||
    mixFacts(strategy).length > 0
  );
}

function mixFacts(strategy) {
  const list = strategy?.mix?.channels;
  return Array.isArray(list) ? list.filter((c) => c && typeof c.channel === "string") : [];
}

/** How many of the given days are each type, most first: [{ type, count }]. */
export function typeMix(days) {
  const counts = new Map();
  for (const d of Array.isArray(days) ? days : []) {
    const type = d?.post_type || "";
    if (type) counts.set(type, (counts.get(type) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([type, count]) => ({ type, count }));
}

/**
 * One row per channel the plan's days are on, most posts first:
 *   { channel, posts, types, scaling, testing, standing, change }
 *
 * `posts` and `types` count every day on the channel, as the board's channel
 * chips do. `change` is the difference in days *made for* it (a day's first
 * platform) from the last plan, the unit the split moves in, and null when
 * there is nothing to compare. A type is only said to be leaned on or tried
 * where the plan actually makes it on that channel, and a channel with one
 * type has nothing to choose between, so it says neither.
 *
 * A plan made before the mix was stored gets the agent's one exploit and
 * explore on its busiest channel, which is the channel the prompt named.
 */
export function channelRows(strategy, days) {
  const on = new Map();
  const madeFor = new Map();
  for (const day of Array.isArray(days) ? days : []) {
    const platforms = dayPlatforms(day);
    if (!platforms.length) continue;
    madeFor.set(platforms[0], (madeFor.get(platforms[0]) || 0) + 1);
    for (const channel of new Set(platforms)) {
      if (!on.has(channel)) on.set(channel, []);
      on.get(channel).push(day);
    }
  }
  const facts = new Map(mixFacts(strategy).map((c) => [c.channel, c]));
  const order = [...facts.keys()];
  const rank = (channel) => (order.includes(channel) ? order.indexOf(channel) : order.length);

  const rows = [...on.entries()]
    .map(([channel, list]) => ({ channel, posts: list.length, types: typeMix(list) }))
    .sort((a, b) => b.posts - a.posts || rank(a.channel) - rank(b.channel));

  return rows.map((row, i) => {
    const fact = facts.get(row.channel);
    const legacy = !facts.size && i === 0 ? strategy || {} : null;
    const has = (type) => row.types.some((t) => t.type === type);
    const choice = row.types.length > 1;
    const scaling = choice ? (fact ? fact.scaling : legacy?.exploit) || "" : "";
    const tried = fact ? (Array.isArray(fact.testing) ? fact.testing : []) : legacy?.explore ? [legacy.explore] : [];
    const lastDays = Number.isFinite(fact?.last_days) ? fact.last_days : null;
    return {
      ...row,
      scaling: scaling && has(scaling) ? scaling : "",
      testing: choice ? tried.filter((type) => type !== scaling && has(type)) : [],
      standing: fact?.standing || null,
      change: lastDays === null ? null : (madeFor.get(row.channel) || 0) - lastDays,
    };
  });
}

/** The goal the plan was split on, or null for a plan made before #529. */
export function planGoal(strategy) {
  const goal = strategy?.mix?.goal;
  return Object.values(GoalKind).includes(goal) ? goal : null;
}

/**
 * The agent's sentence with its data names made readable: the history block
 * it reads names hooks as `question_open_loop`, and a sentence that copies
 * one reaches a person as code.
 */
export function plainWords(text) {
  return typeof text === "string" ? text.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (m) => m.replace(/_/g, " ")) : "";
}

/**
 * A plan's name without the date range it often carries in brackets:
 * "November 2026 plan (Nov 8 - Nov 30)". The line under the name already
 * says the dates, in the reader's format.
 */
export function planDisplayName(name) {
  const text = typeof name === "string" ? name.trim() : "";
  const bare = text.replace(/\s*\([^()]*\d[^()]*\)\s*$/, "").trim();
  return bare || text;
}
