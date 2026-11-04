// The desk's routing rule, pinned to the cases that decide it.
//
// The whole design rests on one property: an item lands in EXACTLY ONE card.
// The first case below is the load-bearing one — it asserts the partition
// holds across every source at once, which is the thing a topic-based layout
// (a "goals" card, a "problems" card) cannot promise.
//
// Run: node scripts/check-desk.mjs

import {
  NEEDS_YOU, FOUND, IN_PROGRESS,
  buildDesk, routeMemory, routeChangeSet, routeConversation,
  certainty, artifactLook, pinnedFirst, relativeTime,
  arrangeDesk, sameFinding, DESK_STATE, QUEUE_LIMIT, NOTES_LIMIT,
} from "../src/lib/desk.js";
import { DESK_SCENARIOS, deskScenario, randomDesk } from "../src/lib/__fixtures__/deskScenarios.mjs";

const NOW = Date.parse("2026-09-01T12:00:00Z");
const ago = (ms) => new Date(NOW - ms).toISOString();

const mem = (over = {}) => ({
  id: Math.random().toString(36).slice(2),
  kind: "conclusion", title: "t", status: "confirmed", confidence: "high",
  importance: 5, recorded_at: ago(3600e3), valid_to: null, superseded_by: null,
  ...over,
});

const cases = [];
const check = (name, got, want) => cases.push({ name, got, want });

// --- the partition ---------------------------------------------------------
{
  const desk = buildDesk({
    memories: [
      mem({ kind: "incident", title: "GA4 stale" }),
      mem({ kind: "goal", title: "40 signups/wk" }),
      mem({ kind: "metric", title: "13 real upgrades" }),
      mem({ kind: "entity", title: "a campaign" }),          // not a claim kind
      mem({ kind: "goal", title: "old goal", superseded_by: "abc" }),
      mem({ kind: "goal", title: "closed goal", valid_to: ago(0) }),
      mem({ kind: "goal", title: "dismissed", status: "archived" }),
    ],
    changeSets: [
      { id: "cs1", title: "Exclude 7 accounts", status: "proposed", changes: [{}, {}] },
      { id: "cs2", title: "Add negatives", status: "applied", changes: [{}] },
      { id: "cs3", title: "Pause ad group", status: "approved", changes: [{}] },
    ],
    conversations: [
      { id: "c1", title: "Funnel", status: "active", last_active_at: ago(2 * 864e5) },
      { id: "c2", title: "Old", status: "archived", last_active_at: ago(9 * 864e5) },
    ],
  });
  const all = [...desk.needsYou, ...desk.found, ...desk.inProgress];
  check("every item lands in exactly one card", all.length, new Set(all.map((i) => i.id)).size);
  check("unresolved incident + proposed change set need you", desk.needsYou.length, 2);
  check("goal and metric are findings", desk.found.length, 2);
  check("active thread + approved change set are in progress", desk.inProgress.length, 2);
  check("superseded, closed, archived and non-claim kinds are shown nowhere", all.length, 6);
  check("a change set outranks a memory in its card", desk.needsYou[0].type, "change_set");
}

// --- individual rules ------------------------------------------------------
check("an applied change set is history, not a card item", routeChangeSet({ status: "applied" }), null);
check("a rejected change set is not waiting on anyone", routeChangeSet({ status: "rejected" }), null);
check("an archived thread is not in progress", routeConversation({ status: "archived" }), null);
check("an open incident blocks on a person", routeMemory(mem({ kind: "incident" })), NEEDS_YOU);
check("a resolved incident is not on the desk", routeMemory(mem({ kind: "incident", valid_to: ago(0) })), null);
check("a watch is something I'm holding, not you", routeMemory(mem({ kind: "watch" })), FOUND);
check("an unconfirmed memory is a finding, not a chore", routeMemory(mem({ status: "proposed" })), FOUND);
check("...and it says so rather than showing a tick", certainty({ status: "proposed" }).code, "unconfirmed");
check("high confidence reads as checked", certainty({ status: "confirmed", confidence: "high" }).code, "checked");
check("a proposed change set counts its changes for the card",
  buildDesk({ changeSets: [{ id: "x", status: "proposed", changes: [{}, {}, {}] }] }).needsYou[0],
  { id: "change_set:x", type: "change_set", title: "", titleCode: "untitled_change_set",
    detailCode: "changes_to_approve", count: 3, tone: "alert", at: "", weight: 10, changeSetId: "x" });

// --- documents -------------------------------------------------------------
check("a brief is a brief", artifactLook({ kind: "brief" }).tone, "brief");
check("an audit report is a report", artifactLook({ kind: "report" }).tone, "report");
check("json is data", artifactLook({ kind: "other", content_type: "application/json" }).tone, "data");
check("an unknown kind is named by its kind", artifactLook({ kind: "slides" }), { code: "kind", kind: "slides", tone: "data" });
check("no kind at all is a document", artifactLook({}).code, "document");
{
  const rows = [
    { id: "a", pinned: false, created_at: ago(1e3) },
    { id: "b", pinned: true, created_at: ago(9 * 864e5) },
    { id: "c", pinned: false, created_at: ago(5e3) },
  ];
  check("pinned floats above newer unpinned", pinnedFirst(rows).map((r) => r.id).join(""), "bac");
}

// --- times -----------------------------------------------------------------
// Pinned to English here so the check does not depend on the machine's locale;
// the desk passes the interface language.
const at = (ms) => relativeTime(ago(ms), { now: NOW, locale: "en" });
check("minutes", at(18 * 60e3), "18 minutes ago");
check("one hour is singular", at(61 * 60e3), "1 hour ago");
check("yesterday is a word, not a date", at(30 * 3600e3), "yesterday");
check("days", at(3 * 864e5), "3 days ago");
check("a week on, a date", at(9 * 864e5), "Aug 23");
check("another language, no code change", relativeTime(ago(3 * 864e5), { now: NOW, locale: "es" }), "hace 3 días");
check("under a minute is the caller's word, not a number", at(20e3), "");
check("a clock skew never reads as the future", relativeTime(new Date(NOW + 5e3).toISOString(), { now: NOW, locale: "en" }), "");
check("no timestamp, no guess", relativeTime("", { now: NOW }), "");

// --- the arrangement --------------------------------------------------------
// The page's shape is fixed whatever the agent wrote: these hold it there.
const states = Object.fromEntries(
  DESK_SCENARIOS.map((sc) => [sc.id, arrangeDesk(deskScenario(sc.id, { now: NOW }), { now: NOW }).state])
);
check("each scenario lands in the state it was written for", states, {
  "first-check": DESK_STATE.WORKING, "one-thing": DESK_STATE.NEEDS_YOU, busy: DESK_STATE.NEEDS_YOU,
  "all-clear": DESK_STATE.CLEAR, "all-clear-empty": DESK_STATE.CLEAR, stale: DESK_STATE.STALE,
  "long-and-foreign": DESK_STATE.NEEDS_YOU, repeats: DESK_STATE.NEEDS_YOU, disconnected: DESK_STATE.CONNECT,
});
{
  const stale = arrangeDesk(deskScenario("stale", { now: NOW }), { now: NOW });
  check("six weeks away: nothing old is shown as news", [stale.lead, stale.rows.length, stale.notes.length], [null, 0, 0]);
  check("...and what was put away is counted", stale.filed.length, 7);
}
{
  const repeats = arrangeDesk(deskScenario("repeats", { now: NOW }), { now: NOW });
  const all = [repeats.lead, ...repeats.rows];
  check("one fact said three ways is one item", all.find((i) => i.type === "memory").copies, 3);
  check("one thread opened twice is one item", all.find((i) => i.type === "conversation").copies, 2);
  check("same words, different numbers stay two notes", repeats.notes.length, 2);
}
check("restatements merge", sameFinding(
  { title: "Inconsistent conversion definitions across landing pages invalidate comparisons" },
  { title: "Inconsistent conversion event definitions distort landing page performance" }), true);
check("different numbers veto a merge", sameFinding(
  { title: "Organic sessions fell 12% week over week" }, { title: "Organic sessions fell 8% week over week" }), false);
check("a stored subject decides over the words", sameFinding(
  { title: "a", subject: "metric|ga4:sessions||week", hasSubject: true },
  { title: "b", subject: "metric|ga4:sessions||week", hasSubject: true }), true);
{
  // 1,000 seeded random desks across every axis: the bounds never move.
  const broken = [];
  for (let seed = 1; seed <= 1000; seed += 1) {
    const a = arrangeDesk(randomDesk(seed, { now: NOW }), { now: NOW });
    const shown = [a.lead, ...a.rows, ...a.notes].filter(Boolean);
    const ids = shown.map((i) => i.id);
    if (a.rows.length > QUEUE_LIMIT || a.notes.length > NOTES_LIMIT) broken.push(`${seed}: over the limit`);
    if (new Set(ids).size !== ids.length) broken.push(`${seed}: an item shown twice`);
    if (a.lead && a.state !== DESK_STATE.NEEDS_YOU) broken.push(`${seed}: a lead item in state ${a.state}`);
    if (a.state === DESK_STATE.NEEDS_YOU && !a.lead) broken.push(`${seed}: needs you with nothing leading`);
    if (a.waiting !== (a.lead ? 1 : 0) + a.rows.length + a.more.length) broken.push(`${seed}: the headline count disagrees with the queue`);
    if (!Object.values(DESK_STATE).includes(a.state)) broken.push(`${seed}: unknown state ${a.state}`);
  }
  check("1,000 random desks keep the shape", broken.slice(0, 5), []);
}

let failed = 0;
for (const { name, got, want } of cases) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failed++;
  console.log(`${ok ? "✓" : "✗"} ${name}${ok ? "" : ` — expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`}`);
}
console.log(failed ? `\n${failed} case(s) failed` : `\nall ${cases.length} cases pass`);
process.exit(failed ? 1 : 0);
