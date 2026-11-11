// Content plans, in every situation the board has to survive.
//
// A plan is written for dates, by the content agent, and read on whatever day
// the person opens it: ahead of time, halfway through, or a month after it
// ended with nothing drafted. These are those situations as the board's own
// data — `{ plans, plan, postsById }` — relative to `today`, so a scene reads
// the same next month. The /preview scenes render them through PlanBoardView
// and the unit tests hold lib/contentSchedule.js's agenda to them.
//
// Nothing here is real: every title, pillar and number is invented.

const DAY = 86_400_000;

const ymd = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const shift = (today, days) => new Date(today.getFullYear(), today.getMonth(), today.getDate() + days);
const at = (today, days, hour = 18) => {
  const d = shift(today, days);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
};

// A cover the preview can draw without a backend.
const COVER = (hue) =>
  `data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90"><rect width="160" height="90" fill="hsl(${hue} 45% 55%)"/><rect x="18" y="20" width="70" height="8" rx="4" fill="white" opacity=".8"/><rect x="18" y="36" width="110" height="8" rx="4" fill="white" opacity=".55"/></svg>`
  )}`;

const TOPICS = [
  "POV: an empty 45-day listing becomes an MLS-ready living room in 20 minutes",
  "Three staging mistakes buyers notice in the first photo",
  "Before and after: the same kitchen, two prices",
  "Why virtual staging sells faster than an empty room",
  "What a stager charges, and what the photo actually needs",
  "The one room every listing should stage first",
  "A day of listings in sixty seconds",
];
const LONG_TOPIC =
  "A complete walkthrough of how a three-bedroom listing that sat for ninety days went under contract in a week after the agent restaged every room, rewrote the description and reshot the exterior at golden hour, with the numbers from each step";
const GERMAN = "Vorher und nachher: wie ein leeres Wohnzimmer in zwanzig Minuten zur verkaufsfertigen Präsentation wird";
const JAPANESE = "空室のリビングが二十分で売れる部屋に変わるまでの全工程";
const PILLARS = ["before_after_staging", "listing_tips", "pricing_truths", "agent_life"];
const TYPES = ["slideshow", "video", "image", "slideshow", "video", "image", "text"];
const PLATFORMS = [["tiktok"], ["tiktok", "instagram"], ["instagram"], ["tiktok"], ["linkedin"]];

const NO_HISTORY = {
  exploit: "",
  exploit_evidence: "No published posts yet to establish an exploit leader; distributing evenly across visual formats",
  explore: "slideshow",
  explore_evidence: "No historical baseline; testing slideshows, videos, and single-image posts to gather baseline completion, saves, and shares",
  lesson: "Establish initial baseline performance across before/after carousels and calculator tool entry points",
  best_times: "Tue and Thu around 18:00 UTC (19:00 in Madrid / Europe/Madrid)",
};
const WITH_HISTORY = {
  exploit: "video",
  exploit_evidence: "Median completion 42% over 6 videos, against 18% over 5 slideshows",
  explore: "image",
  explore_evidence: "Two image posts so far, too few to judge",
  lesson: "Question hooks out-completed curiosity gaps 51% to 33%, so more of them",
  best_times: "Tue, Thu · 19:00",
  review_notes:
    "TikTok earned the most saves and shares per post, so it gets two more days; LinkedIn trails and gives one back, still a post a week.",
  experiment: "Image posts on TikTok, judged on saves against the video median",
  // What the plan stored from its channel mix (backend channel_mix.mix_snapshot).
  mix: {
    goal: "intent",
    channels: [
      { channel: "tiktok", last_days: 16, standing: "leads", scaling: "video", testing: ["image"] },
      { channel: "instagram", last_days: 6, standing: "untested", scaling: "", testing: [] },
      { channel: "linkedin", last_days: 7, standing: "trails", scaling: "text", testing: [] },
    ],
  },
};

function makePlan(id, name, start, count, { strategy = {}, topic = (i) => TOPICS[i % TOPICS.length] } = {}) {
  return {
    id,
    name,
    start_date: ymd(start),
    strategy,
    days: Array.from({ length: count }, (_, i) => ({
      topic: topic(i),
      pillar: PILLARS[i % PILLARS.length],
      post_type: TYPES[i % TYPES.length],
      platforms: PLATFORMS[i % PLATFORMS.length],
      format_slug: i % 3 === 0 ? "ugc-carousel" : "",
      status: "pending",
    })),
  };
}

/** Give day `i` a post in `status`, dated `offset` days from today. */
function withPost(plan, postsById, i, status, today, offset, { media = true } = {}) {
  const id = `${plan.id}-post-${i}`;
  const day = plan.days[i];
  day.post_id = id;
  day.status = status;
  postsById[id] = {
    id,
    status,
    post_type: day.post_type,
    platforms: day.platforms,
    pillar: day.pillar,
    hook_text: day.topic,
    thumbnail_url: media ? COVER((i * 47) % 360) : "",
    posted_at: status === "posted" ? at(today, offset) : null,
    scheduled_at: status === "draft" && offset >= 0 ? at(today, offset) : null,
    published_via: status === "posted" ? "duct" : "",
  };
}

/**
 * The scenarios also rendered as the Kanban, in /preview and in
 * check:layout: one full lane, every lane in use, and long foreign titles.
 */
export const KANBAN_SCENARIO_IDS = ["ended-nothing-posted", "mid-month", "long-and-foreign"];

export const PLAN_SCENARIOS = [
  {
    id: "ended-nothing-posted",
    title: "Ended a month ago, nothing drafted (the 2026-11-03 screenshot)",
    expect: "Says the plan ended and offers the next one; thirty posts are missed, five shown; no strategy row claims a win.",
    build(today) {
      const plan = makePlan("oct", "October 2026 Content Plan", shift(today, -33), 30, { strategy: NO_HISTORY });
      return { plans: [plan], plan, postsById: {} };
    },
  },
  {
    id: "mid-month",
    title: "Halfway through, with real results",
    expect: "Posted, drafted, missed and upcoming posts each where they belong; the strategy names what it scales and tests.",
    build(today) {
      const plan = makePlan("nov", "November plan", shift(today, -12), 30, { strategy: WITH_HISTORY });
      const postsById = {};
      for (let i = 0; i < 6; i += 1) withPost(plan, postsById, i, "posted", today, i - 12);
      withPost(plan, postsById, 6, "draft", today, -6);
      withPost(plan, postsById, 12, "draft", today, 0, { media: false });
      withPost(plan, postsById, 13, "draft", today, 1);
      return { plans: [plan], plan, postsById };
    },
  },
  {
    id: "fresh",
    title: "Starts today, no history",
    expect: "This week and the weeks after; the strategy is the mix it is trying, counted from the plan.",
    build(today) {
      const plan = makePlan("fresh", "Two-week plan", today, 14, { strategy: NO_HISTORY });
      return { plans: [plan], plan, postsById: {} };
    },
  },
  {
    id: "planned-ahead",
    title: "Planned ahead, starts in ten days",
    expect: "No missed, no this-week: the plan's weeks by their dates.",
    build(today) {
      const plan = makePlan("ahead", "December plan", shift(today, 10), 7, { strategy: WITH_HISTORY });
      return { plans: [plan], plan, postsById: {} };
    },
  },
  {
    id: "ended-done",
    title: "Ended, everything went out",
    expect: "Ended card counts every post as out; the posts are folded under Earlier.",
    build(today) {
      const plan = makePlan("sep", "September plan", shift(today, -40), 14, { strategy: WITH_HISTORY });
      const postsById = {};
      for (let i = 0; i < 14; i += 1) withPost(plan, postsById, i, "posted", today, i - 40);
      return { plans: [plan], plan, postsById };
    },
  },
  {
    id: "long-and-foreign",
    title: "Run-on titles, German, Japanese",
    expect: "Every title holds to its clamp; pillar chips truncate rather than wrap the row.",
    build(today) {
      const titles = [LONG_TOPIC, GERMAN, JAPANESE];
      const plan = makePlan("long", "A plan whose name is far longer than anyone would type into a field", shift(today, -3), 21, {
        strategy: NO_HISTORY,
        topic: (i) => titles[i % titles.length],
      });
      plan.days.forEach((d, i) => { d.pillar = i % 2 ? "before_and_after_staging_for_vacant_luxury_listings" : d.pillar; });
      return { plans: [plan], plan, postsById: {} };
    },
  },
  {
    id: "no-strategy",
    title: "An old plan with no strategy",
    expect: "No strategy row at all when the plan has one type; the agenda alone.",
    build(today) {
      const plan = makePlan("old", "Launch week", shift(today, -2), 5);
      plan.days.forEach((d) => { d.post_type = "video"; });
      return { plans: [plan], plan, postsById: {} };
    },
  },
];

// The plan picker's situations: a project's plans as the listing returns them,
// days included, built from the board's scenarios so the two agree.
const LONG_PLAN_NAME =
  "Novemberplan: Vorher-Nachher-Serie für leerstehende Wohnungen, Preisgespräche und Maklertage (8. Nov – 30. Nov)";

export const PLAN_PICKER_SCENARIOS = [
  {
    id: "several",
    title: "One running, one ahead, two ended",
    expect: "The menu opens on the running plan, checked; then the one ahead, then the ended ones newest first. Each row says its state, its dates, how far it got and its channels.",
    build: (today) => ["ended-nothing-posted", "planned-ahead", "mid-month", "ended-done"].map((id) => planScenario(id, today).plan),
  },
  {
    id: "one",
    title: "A first plan, running",
    expect: "One plan, so no menu: its name is a plain title.",
    build: (today) => [planScenario("mid-month", today).plan],
  },
  {
    id: "long-name",
    title: "A German-length name with its dates in brackets",
    expect: "The name truncates on one line, in the trigger and in its row, with the whole of it in the tooltip; the bracketed dates are dropped because the line under it says them.",
    build: (today) => {
      const running = planScenario("mid-month", today).plan;
      return [{ ...running, name: LONG_PLAN_NAME }, planScenario("planned-ahead", today).plan];
    },
  },
];

export function planPickerScenario(id, today) {
  const s = PLAN_PICKER_SCENARIOS.find((x) => x.id === id);
  if (!s) throw new Error(`no plan picker scenario "${id}"`);
  return s.build(today);
}

/**
 * A proposal that changes some days of the "fresh" plan, as revise_plan_days
 * sends it: the plan with those days changed, their indexes, and what each
 * said before. "one" is one day's topic and type; "week" is four days with
 * a hook moved, a channel moved, a series set and one topic long enough to
 * wrap.
 */
export function planChangeScenario(which, today) {
  const { plan } = planScenario("fresh", today);
  const edits = which === "week"
    ? {
        3: { topic: "Staging a rental in one afternoon, room by room", hook_type: "question_open_loop" },
        4: { topic: LONG_TOPIC, platforms: ["instagram"], post_type: "slideshow" },
        5: { series: "S2: Rentals that rent, 1/3", objective: "saves" },
        6: { topic: "What the photographer sees that the agent misses", hook_type: "contrarian_take", hook_emotion: "surprise" },
      }
    : { 2: { topic: "Five pieces that stage any living room", post_type: "image" } };
  const indexes = Object.keys(edits).map(Number);
  return {
    ...plan,
    days: plan.days.map((d, i) => (edits[i] ? { ...d, ...edits[i] } : d)),
    only_days: true,
    changed_days: indexes,
    previous_days: indexes.map((i) => plan.days[i]),
  };
}

export function planScenario(id, today) {
  const s = PLAN_SCENARIOS.find((x) => x.id === id);
  if (!s) throw new Error(`no plan scenario "${id}"`);
  return s.build(today);
}

/** Mulberry32, so a seed is the same plan on every machine. */
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

/**
 * A random plan: any start from two months back to a month ahead, 1 to 30
 * days, each day pending, drafted or posted at random, some posts undated.
 */
export function randomPlan(seed, today) {
  const r = rng(seed);
  const start = shift(today, Math.floor(r() * 90) - 60);
  const plan = makePlan(`r${seed}`, `Random ${seed}`, start, 1 + Math.floor(r() * 30), { strategy: r() < 0.5 ? NO_HISTORY : WITH_HISTORY });
  const postsById = {};
  plan.days.forEach((day, i) => {
    const roll = r();
    const offset = Math.round((start.getTime() - today.getTime()) / DAY) + i;
    if (roll < 0.3) withPost(plan, postsById, i, "posted", today, offset, { media: r() < 0.7 });
    else if (roll < 0.45) withPost(plan, postsById, i, "draft", today, offset, { media: r() < 0.5 });
    else if (roll < 0.5) withPost(plan, postsById, i, "discarded", today, offset);
  });
  return { plans: [plan], plan, postsById };
}
