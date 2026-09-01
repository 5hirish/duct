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
  certainty, artifactLook, pinnedFirst, relativeTime, headline,
} from "../src/lib/desk.js";

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
check("...and it says so rather than showing a tick", certainty({ status: "proposed" }).label, "Not confirmed");
check("high confidence reads as checked", certainty({ status: "confirmed", confidence: "high" }).label, "Checked");

// --- documents -------------------------------------------------------------
check("a brief is a brief", artifactLook({ kind: "brief" }).tone, "brief");
check("an audit report is a report", artifactLook({ kind: "report" }).tone, "report");
check("json is data", artifactLook({ kind: "other", content_type: "application/json" }).tone, "data");
{
  const rows = [
    { id: "a", pinned: false, created_at: ago(1e3) },
    { id: "b", pinned: true, created_at: ago(9 * 864e5) },
    { id: "c", pinned: false, created_at: ago(5e3) },
  ];
  check("pinned floats above newer unpinned", pinnedFirst(rows).map((r) => r.id).join(""), "bac");
}

// --- words -----------------------------------------------------------------
check("minutes", relativeTime(ago(18 * 60e3), NOW), "18 minutes ago");
check("one hour is singular", relativeTime(ago(61 * 60e3), NOW), "1 hour ago");
check("yesterday is a word, not a date", relativeTime(ago(30 * 3600e3), NOW), "Yesterday");
check("days", relativeTime(ago(3 * 864e5), NOW), "3 days ago");
check("a clock skew never reads as the future", relativeTime(new Date(NOW + 5e3).toISOString(), NOW), "just now");
check("no timestamp, no guess", relativeTime("", NOW), "");

check("one thing needing you is singular",
  headline({ needsYou: 1, lastRunAt: ago(60e3), sourceCount: 3, now: NOW }).title,
  "1 thing needs you.");
check("a clear desk says so",
  headline({ needsYou: 0, found: 4, lastRunAt: ago(60e3), sourceCount: 3, now: NOW }).title,
  "Nothing needs you right now.");
check("a zero is never reported as a result",
  headline({ needsYou: 0, found: 0, sourceCount: 0, now: NOW }).sub,
  "Nothing has run yet. 0 sources connected.");

let failed = 0;
for (const { name, got, want } of cases) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failed++;
  console.log(`${ok ? "✓" : "✗"} ${name}${ok ? "" : ` — expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`}`);
}
console.log(failed ? `\n${failed} case(s) failed` : `\nall ${cases.length} cases pass`);
process.exit(failed ? 1 : 0);
