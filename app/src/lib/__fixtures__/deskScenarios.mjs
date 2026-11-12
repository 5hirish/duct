// The desk, in every situation it has to survive.
//
// Everything on the desk is written at run time — by a model or by the person
// — so one good screenshot proves nothing about the next run. These are the
// situations the layout is held to (DESIGN.md, "Content awareness"), as
// `loadDesk`-shaped payloads: the /preview scenes render them, the unit tests
// assert the arrangement's invariants over them, and `randomDesk` throws
// seeded random mixes at the same invariants.
//
// Timestamps are relative to `now`, so a scene reads the same today as in a
// month. Nothing here is real: every name, title and number is invented.

const DAY = 86_400_000;

// Titles the way the agent and the person actually write them: short labels,
// full sentences, one that will not stop, restatements of one fact, the
// person's own typing, and two other languages.
export const TITLES = {
  short: ["Signups up", "Trial starts dipped", "Refunds steady"],
  sentence: [
    "Paid search clicks rose 14% after the bid change",
    "Organic sessions on the pricing page fell 9% week over week",
    "Two key events were renamed mid-week in GA4",
    "The comparison pages now carry most non-brand clicks",
    "Checkout abandonment is concentrated on mobile Safari",
  ],
  long:
    "North-star window: the next 90 days are about getting net new MRR positive and keeping it there — the measured 30-day position is €2,140 of new MRR against €2,960 lost to failed payments, plus €1,180 sitting past due, so the window is still net negative and the failed-payment recovery emails are the cheapest lever",
  restated: [
    "Inconsistent conversion definitions across landing pages invalidate comparisons",
    "Inconsistent conversion event definitions distort landing page performance",
    "Landing pages use inconsistent conversion definitions, so comparisons are invalid",
  ],
  numbersDiffer: ["Organic sessions fell 12% week over week", "Organic sessions fell 8% week over week"],
  typed: ["Analyse the webperformance pls.", "why did signups drop??", "check google ads", "Compare last month vs this month for paid"],
  german:
    "Die Conversion-Definitionen der Landingpages sind uneinheitlich, deshalb sind die Vergleiche zwischen Kampagnen und Zeiträumen derzeit nicht belastbar",
  japanese: "ランディングページごとにコンバージョンの定義が異なるため、期間比較の数値が信頼できません",
};

const iso = (now, days) => new Date(now - days * DAY).toISOString();
let seq = 0;
const id = (p) => `${p}-${(seq += 1)}`;

export function memory(now, over = {}) {
  const { daysAgo = 1, ...rest } = over;
  return {
    id: id("m"), kind: "conclusion", title: TITLES.sentence[0], body: "", status: "confirmed",
    confidence: "high", importance: 5, recorded_at: iso(now, daysAgo), valid_to: null,
    superseded_by: null, entity_key: "", attribute: "", period: "", value: {}, source_refs: [],
    ...rest,
  };
}

export function changeSet(now, over = {}) {
  const { daysAgo = 1, changes = 3, ...rest } = over;
  return {
    id: id("cs"), title: "Pause three ad groups with no conversions in 30 days", status: "proposed",
    changes: Array.from({ length: changes }, () => ({})), created_at: iso(now, daysAgo),
    updated_at: iso(now, daysAgo), ...rest,
  };
}

export function thread(now, over = {}) {
  const { daysAgo = 1, ...rest } = over;
  return {
    id: id("c"), status: "active", run_status: "idle", title: TITLES.typed[0], pinned: false,
    created_at: iso(now, daysAgo), last_active_at: iso(now, daysAgo), ...rest,
  };
}

const activity = (now, daysAgo) => [
  { id: id("a"), category: "check", action: "checked_ga4", summary: "", source: "auto", created_at: iso(now, daysAgo) },
];

const base = () => ({ memories: [], conversations: [], artifacts: [], activity: [], changeSets: [], sourceCount: 2 });

/**
 * The named situations. Each says what it holds the page to; the preview
 * scene shows that sentence beside it.
 */
export const DESK_SCENARIOS = [
  {
    id: "first-check",
    title: "First check running",
    expect: "Headline says Duct is looking; no lead, no rows; the working count sits in the header.",
    build: (now) => ({ ...base(), conversations: [thread(now, { daysAgo: 0, run_status: "running", title: "Check our Google Search performance" })] }),
  },
  {
    id: "one-thing",
    title: "One thing waits",
    expect: "One lead item, nothing under it; two notes below.",
    build: (now) => ({
      ...base(),
      activity: activity(now, 0.2),
      conversations: [thread(now, { daysAgo: 0.1, run_status: "paused", title: "Which campaigns should get next month's budget?" })],
      memories: [
        memory(now, { daysAgo: 0.5, title: TITLES.sentence[0], value: { value: 1840, unit: "clicks", delta: 0.14 }, source_refs: [{ connector: "google_ads" }] }),
        memory(now, { daysAgo: 2, kind: "goal", title: "40 paid signups a week by December" }),
      ],
    }),
  },
  {
    id: "busy",
    title: "Forty things at once",
    expect: "Exactly one lead and four rows, then a count of the rest; three notes; the page is no taller than with five.",
    build: (now) => {
      const d = { ...base(), activity: activity(now, 0.1) };
      for (let i = 0; i < 12; i += 1) d.memories.push(memory(now, { kind: "incident", title: `${TITLES.sentence[i % 5]} (${i + 1})`, importance: 3 + (i % 7), daysAgo: (i % 10) + 0.5 }));
      for (let i = 0; i < 8; i += 1) d.changeSets.push(changeSet(now, { daysAgo: i + 0.3, changes: (i % 4) + 1, title: `Exclude ${i + 2} low-intent search terms from Brand – Exact` }));
      for (let i = 0; i < 10; i += 1) d.conversations.push(thread(now, { run_status: i % 2 ? "failed" : "paused", title: `${TITLES.typed[i % 4]} #${i + 1}`, daysAgo: i * 0.7 }));
      for (let i = 0; i < 20; i += 1) d.memories.push(memory(now, { kind: ["metric", "conclusion", "goal", "watch"][i % 4], title: `${TITLES.sentence[i % 5]} — segment ${i + 1}`, daysAgo: i + 0.2 }));
      return d;
    },
  },
  {
    id: "all-clear",
    title: "All clear, with notes",
    expect: "Calm headline; no lead, no rows; the notes are the page.",
    build: (now) => ({
      ...base(),
      activity: activity(now, 0.1),
      memories: [
        memory(now, { kind: "metric", title: "Trial-to-paid held at 11.2%", value: { value: 0.112, unit: "%", delta: 0.004 }, source_refs: [{ connector: "stripe" }] }),
        memory(now, { kind: "outcome", title: "Meta title rewrite lifted organic clicks 18% in two weeks", daysAgo: 3, source_refs: [{ connector: "ga4" }] }),
        memory(now, { kind: "watch", title: "Watching the new pricing page for a week before judging it", daysAgo: 4, status: "proposed" }),
      ],
    }),
  },
  {
    id: "all-clear-empty",
    title: "All clear, nothing to say",
    expect: "The all-caught-up mosaic; nothing else.",
    build: (now) => ({ ...base(), activity: activity(now, 0.1), conversations: [thread(now, { daysAgo: 0.1, title: "What changed this week?" })] }),
  },
  {
    id: "stale",
    title: "Six weeks away (the 2026-11-03 screenshot)",
    expect: "Headline says how long since Duct looked; the fresh-look card leads; old items are filed and counted; the restated finding appears once.",
    build: (now) => ({
      ...base(),
      activity: activity(now, 42),
      conversations: [
        thread(now, { daysAgo: 41, run_status: "failed", title: TITLES.typed[0] }),
        thread(now, { daysAgo: 52, run_status: "cancelled", title: TITLES.typed[0] }),
      ],
      memories: [
        memory(now, { kind: "incident", title: TITLES.restated[0], daysAgo: 42, importance: 7 }),
        memory(now, { kind: "incident", title: "Duplicate page_view tags on core app routes inflate engagement", daysAgo: 42, importance: 8 }),
        ...[3, 4, 5, 6].map((n) => memory(now, { kind: "incident", title: `${TITLES.sentence[n % 5]}`, daysAgo: 40 + n })),
        memory(now, { kind: "conclusion", status: "proposed", title: "Paid ad spend optimisation is blocked by broken GA4 tracking", daysAgo: 42 }),
        memory(now, { kind: "conclusion", status: "proposed", title: TITLES.restated[1], daysAgo: 47 }),
        memory(now, { kind: "decision", status: "proposed", title: "Adopted a 30-day content plan spanning eight formats", daysAgo: 33 }),
      ],
    }),
  },
  {
    id: "long-and-foreign",
    title: "Run-on titles, German, Japanese",
    expect: "The lead clamps at two lines, every row at one; nothing pushes the age column off the row.",
    build: (now) => ({
      ...base(),
      activity: activity(now, 0.1),
      memories: [
        memory(now, { kind: "incident", title: TITLES.long, body: TITLES.long, importance: 9, daysAgo: 0.2 }),
        memory(now, { kind: "incident", title: TITLES.german, importance: 6, daysAgo: 0.4 }),
        memory(now, { kind: "incident", title: TITLES.japanese, importance: 6, daysAgo: 0.5 }),
        memory(now, { kind: "conclusion", title: TITLES.german, daysAgo: 1 }),
        memory(now, { kind: "conclusion", title: TITLES.japanese, daysAgo: 1 }),
        memory(now, { kind: "conclusion", title: TITLES.long, daysAgo: 1 }),
      ],
      conversations: [thread(now, { run_status: "paused", title: TITLES.long.slice(0, 120), daysAgo: 0.3 })],
    }),
  },
  {
    id: "repeats",
    title: "The same fact, said three ways",
    expect: "One row marked ×3; one thread marked ×2; the two session figures stay two notes because their numbers differ.",
    build: (now) => ({
      ...base(),
      activity: activity(now, 0.1),
      memories: [
        ...TITLES.restated.map((title, i) => memory(now, { kind: "incident", title, daysAgo: 1 + i })),
        ...TITLES.numbersDiffer.map((title, i) => memory(now, { kind: "metric", title, daysAgo: 1 + i })),
      ],
      conversations: [
        thread(now, { run_status: "failed", title: TITLES.typed[0], daysAgo: 0.5 }),
        thread(now, { run_status: "failed", title: "analyse the web-performance, pls", daysAgo: 2 }),
      ],
    }),
  },
  {
    id: "disconnected",
    title: "Sources disconnected, items still open",
    expect: "Connect leads; the open items are plain rows under it.",
    build: (now) => ({
      ...base(),
      sourceCount: 0,
      activity: activity(now, 1),
      memories: [memory(now, { kind: "incident", title: "Search Console stopped answering on Tuesday", daysAgo: 1 })],
      changeSets: [changeSet(now, { daysAgo: 2 })],
    }),
  },
];

export function deskScenario(scenarioId, { now = Date.now() } = {}) {
  const s = DESK_SCENARIOS.find((x) => x.id === scenarioId);
  if (!s) throw new Error(`no desk scenario "${scenarioId}"`);
  return s.build(now);
}

/** Mulberry32: small, seedable, and the same sequence on every machine. */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const ALL_TITLES = [
  ...TITLES.short, ...TITLES.sentence, TITLES.long, ...TITLES.restated, ...TITLES.numbersDiffer,
  ...TITLES.typed, TITLES.german, TITLES.japanese, "",
];

/**
 * A random desk across every axis at once: 0–300 items, any mix, any age up
 * to four months, any title (including none), with and without numbers and
 * sources, connected or not. Same seed, same desk.
 */
export function randomDesk(seed, { now = Date.now() } = {}) {
  const r = rng(seed);
  const pick = (xs) => xs[Math.floor(r() * xs.length)];
  const size = pick([0, 1, 2, 5, 12, 40, 300]);
  const age = () => pick([0, 0.1, 1, 3, 10, 20, 45, 120]) * (0.5 + r());
  const d = {
    memories: [], conversations: [], artifacts: [], changeSets: [],
    activity: r() < 0.8 ? activity(now, age()) : [],
    sourceCount: r() < 0.85 ? Math.ceil(r() * 6) : 0,
  };
  for (let i = 0; i < size; i += 1) {
    const roll = r();
    if (roll < 0.55) {
      d.memories.push(memory(now, {
        kind: pick(["incident", "conclusion", "metric", "goal", "decision", "watch", "outcome", "status", "entity"]),
        title: pick(ALL_TITLES),
        status: pick(["confirmed", "proposed", "archived"]),
        confidence: pick(["high", "medium", "low"]),
        importance: Math.ceil(r() * 10),
        daysAgo: age(),
        entity_key: r() < 0.3 ? pick(["ga4:sessions", "ads:cpa", "stripe:mrr"]) : "",
        value: r() < 0.3 ? { value: Math.round(r() * 1e6) / 100, unit: pick(["", "USD", "%"]), delta: r() - 0.5 } : {},
        source_refs: r() < 0.4 ? [{ connector: pick(["ga4", "gsc", "google_ads", "stripe", "not_a_connector"]) }] : [],
      }));
    } else if (roll < 0.75) {
      d.changeSets.push(changeSet(now, { status: pick(["proposed", "approved", "applying", "applied"]), daysAgo: age(), changes: Math.floor(r() * 9), title: pick(ALL_TITLES) }));
    } else {
      d.conversations.push(thread(now, {
        status: pick(["active", "active", "archived"]),
        run_status: pick(["paused", "failed", "running", "cancelled", "idle"]),
        title: pick(ALL_TITLES).slice(0, 120),
        pinned: r() < 0.1,
        daysAgo: age(),
      }));
    }
  }
  return d;
}
