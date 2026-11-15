// Settings-side answers for the mock backend: members, schedules, usage,
// profile, models, project config, the consent page and the invite landing,
// plus the full project as the app keeps it in localStorage "duct_projects".
//
// Every shape follows the backend handler that answers the real route (file
// named beside each block). The story's clock is 2026-09-14 09:30 Madrid
// (07:30Z); every date below is on or before it.

const NOW_MS = Date.parse("2026-09-14T07:30:00Z");
// Python's aware isoformat, which is what every route here sends.
const iso = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "+00:00");
const DAY_MS = 86_400_000;

// --- People ------------------------------------------------------------------

const MAYA_ID = "3f6b2c1e-8a4d-4e7b-9c2f-5d1a0e7b4c91";
const PRIYA = { id: "a21c9e47-5b3f-4d08-8e6a-2f7c1b9d3e52", name: "Priya Raman", email: "priya@example.com" };
const JONAS = { email: "jonas@example.com" };
const INVITE_ID = "c7d40b19-6e2a-4f85-b3c1-9a8e5d2f0a63";
const INVITE_CREATED = "2026-09-11T15:20:00+00:00";
// invitation_ttl_days defaults to 7 (backend/config.py).
const INVITE_EXPIRES = "2026-09-18T15:20:00+00:00";

// --- Usage: one record of runs, summed per window ----------------------------
//
// service/usage.py summarise(): every breakdown and the total are SUMs over
// the same rows, so a window is built from runs and the four views agree.
// Prices are agents/models.py PRICING (input, output, cache read; USD per
// million tokens), so tokens x price is micro-dollars.
const PRICE = {
  "claude-opus-5-5": [4.0, 20.0, 0.2],
  "claude-sonnet-5-5": [2.0, 10.0, 0.2],
  "claude-haiku-5-5": [0.1, 0.5, 0.01],
  "gpt-6-luna": [0.1, 0.5, 0.01],
};
const PROVIDER_OF = {
  "claude-opus-5-5": "anthropic",
  "claude-sonnet-5-5": "anthropic",
  "claude-haiku-5-5": "anthropic",
  "gpt-6-luna": "openai",
};
// Light moved from Haiku to GPT-6 Luna on her ChatGPT plan on 14 Aug.
const LIGHT_SWITCH = Date.parse("2026-08-14T00:00:00Z");
const modelFor = (tier, at) =>
  tier === "heavy" ? "claude-opus-5-5" : tier === "standard" ? "claude-sonnet-5-5" : at < LIGHT_SWITCH ? "claude-haiku-5-5" : "gpt-6-luna";

// [calls, input tokens (cached included), cached, output] per tier for one run.
const TEMPLATES = {
  brief: { heavy: [3, 52000, 31000, 5600], standard: [28, 141000, 101000, 18200], light: [36, 64000, 28000, 5100] },
  session: { heavy: [1, 18000, 11000, 2100], standard: [22, 109000, 79000, 13400], light: [27, 47000, 21000, 3700] },
  plan: { standard: [18, 71000, 46000, 12100], light: [22, 43000, 16000, 4000] },
  // A release run that read a hotfix and proposed nothing.
  quiet: { standard: [6, 24000, 15000, 2100], light: [8, 14000, 5000, 1200] },
  draft: { standard: [9, 34000, 22000, 6300], light: [6, 11000, 4000, 1100] },
  audit: { heavy: [8, 167000, 66000, 18700], standard: [27, 124000, 77000, 14800], light: [42, 84000, 33000, 7900] },
};
// agent_type is what routes/agents.py passes to set_usage_context: the route's
// AgentType value (agents/registry.py), so the audit is "audit_seo".
const AGENT_OF = { brief: "insights", session: "insights", plan: "tiktok_studio", draft: "tiktok_studio", audit: "audit_seo" };

// [when, kind, scale]. Scheduled plan runs are absent on purpose: the
// schedule job (routes/schedule_jobs.py) never calls set_usage_context, so
// the real table has no row for them either.
const RUNS = [
  ["2026-08-02T09:12:00Z", "audit", 1.0],
  ["2026-08-03T05:30:00Z", "brief", 0.9],
  ["2026-08-05T10:20:00Z", "session", 0.8],
  ["2026-08-09T16:00:00Z", "plan", 1.1],
  ["2026-08-10T05:30:00Z", "brief", 0.95],
  ["2026-08-11T15:30:00Z", "draft", 0.9],
  ["2026-08-12T14:05:00Z", "session", 1.1],
  ["2026-08-12T16:10:00Z", "draft", 1.0],
  ["2026-08-17T05:30:00Z", "brief", 1.0],
  ["2026-08-18T15:45:00Z", "draft", 1.1],
  ["2026-08-19T08:50:00Z", "session", 0.9],
  ["2026-08-19T16:20:00Z", "draft", 0.8],
  ["2026-08-21T09:05:00Z", "session", 1.2],
  ["2026-08-23T17:10:00Z", "plan", 1.0],
  ["2026-08-24T05:30:00Z", "brief", 1.05],
  ["2026-08-25T15:10:00Z", "draft", 1.0],
  ["2026-08-26T14:30:00Z", "session", 1.0],
  ["2026-08-27T16:40:00Z", "draft", 0.9],
  ["2026-08-28T11:10:00Z", "session", 0.85],
  ["2026-08-31T05:30:00Z", "brief", 1.0],
  ["2026-09-01T15:25:00Z", "draft", 1.2],
  ["2026-09-03T08:00:00Z", "session", 1.3],
  ["2026-09-03T16:05:00Z", "draft", 1.0],
  ["2026-09-05T07:35:00Z", "session", 1.0],
  ["2026-09-07T05:30:00Z", "brief", 1.1],
  ["2026-09-08T16:00:00Z", "draft", 1.0],
  ["2026-09-09T10:15:00Z", "session", 0.9],
  ["2026-09-09T15:20:00Z", "draft", 1.1],
  ["2026-09-10T15:40:00Z", "session", 1.0],
  ["2026-09-10T16:45:00Z", "draft", 1.3],
  ["2026-09-11T09:20:00Z", "session", 0.8],
  ["2026-09-12T06:45:00Z", "session", 1.4],
  ["2026-09-12T13:30:00Z", "session", 1.0],
  ["2026-09-13T07:05:00Z", "session", 1.2],
  ["2026-09-13T11:40:00Z", "session", 1.1],
  ["2026-09-13T16:05:00Z", "audit", 1.1],
  ["2026-09-14T05:30:00Z", "brief", 1.15],
];

/** One run's rows: { model, calls, input_tokens, output_tokens, cached_tokens, cost_micros }. */
function runCells(kind, scale, at) {
  return Object.entries(TEMPLATES[kind]).map(([tier, [calls, input, cached, output]]) => {
    const model = modelFor(tier, at);
    const row = {
      model,
      calls: Math.max(1, Math.round(calls * scale)),
      input_tokens: Math.round(input * scale),
      cached_tokens: Math.round(cached * scale),
      output_tokens: Math.round(output * scale),
    };
    const [pin, pout, pcache] = PRICE[model];
    row.cost_micros = Math.round((row.input_tokens - row.cached_tokens) * pin + row.cached_tokens * pcache + row.output_tokens * pout);
    return row;
  });
}

/** What one run cost in dollars, as a schedule's history row carries it. */
const runCostUsd = (kind, scale, at) =>
  runCells(kind, scale, Date.parse(at)).reduce((sum, c) => sum + c.cost_micros, 0) / 1_000_000;

// UsageSlice.as_dict
function slice(key, rows) {
  const s = { key, calls: 0, input_tokens: 0, output_tokens: 0, cached_tokens: 0, micros: 0 };
  for (const r of rows) {
    s.calls += r.calls;
    s.input_tokens += r.input_tokens;
    s.output_tokens += r.output_tokens;
    s.cached_tokens += r.cached_tokens;
    s.micros += r.cost_micros;
  }
  return {
    key,
    calls: s.calls,
    input_tokens: s.input_tokens,
    output_tokens: s.output_tokens,
    cached_tokens: s.cached_tokens,
    total_tokens: s.input_tokens + s.output_tokens,
    cost_usd: s.micros / 1_000_000,
  };
}

function groupBy(rows, keyOf) {
  const groups = new Map();
  for (const r of rows) {
    const k = keyOf(r);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  return groups;
}

// UsageSummary.as_dict; breakdowns cost-first, as the SQL orders them.
function usage(windowDays) {
  const since = NOW_MS - windowDays * DAY_MS;
  const rows = RUNS.filter(([at]) => Date.parse(at) >= since).flatMap(([at, kind, scale]) =>
    runCells(kind, scale, Date.parse(at)).map((c) => ({
      ...c,
      agent: AGENT_OF[kind],
      provider: PROVIDER_OF[c.model],
      day: at.slice(0, 10),
    })),
  );
  const breakdown = (keyOf) =>
    [...groupBy(rows, keyOf)].map(([k, list]) => slice(k, list)).sort((a, b) => b.cost_usd - a.cost_usd);
  return {
    window_days: windowDays,
    since: iso(since),
    total: slice("total", rows),
    by_agent: breakdown((r) => r.agent),
    by_model: breakdown((r) => r.model),
    by_provider: breakdown((r) => r.provider),
    daily: [...groupBy(rows, (r) => r.day)]
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([day, list]) => {
        const s = slice(day, list);
        return { day, calls: s.calls, total_tokens: s.total_tokens, cost_usd: s.cost_usd };
      }),
  };
}

// --- Schedules ---------------------------------------------------------------

const WEEKLY_ID = "6d0c3a52-91f4-4c27-8e15-3f2b7a9e0c11";
const RELEASE_ID = "b8e47d10-2a6c-4f93-a5d2-7c19e04f6b22";

// service/schedules.history(): one dict per activity row, newest first.
const run = (at, outcome, extra = {}) => ({
  at,
  outcome,
  reason: "",
  conversation_id: null,
  cost_usd: null,
  duration_seconds: null,
  late_seconds: null,
  will_retry: false,
  feed_days: null,
  proposal_id: null,
  ...extra,
});

const WEEKLY_HISTORY = [
  run("2026-09-14T07:03:46+00:00", "proposed", {
    conversation_id: "e3a1f7c2-4b9d-4e61-8a07-1c5d9b2e6f14", cost_usd: runCostUsd("plan", 1.05, "2026-09-14T07:02:04Z"),
    duration_seconds: 102, late_seconds: 124, feed_days: 2, proposal_id: "prop_solo_w38",
  }),
  run("2026-09-07T07:02:58+00:00", "proposed", {
    conversation_id: "4f82c0d9-7a1e-4b35-9c6f-2e8d0a5b7c23", cost_usd: runCostUsd("plan", 0.95, "2026-09-07T07:01:21Z"),
    duration_seconds: 97, late_seconds: 81, feed_days: 2, proposal_id: "prop_solo_w37",
  }),
  // The gate found nothing worth a model call: no cost, but a conversation.
  run("2026-08-31T07:01:20+00:00", "nothing_new", {
    conversation_id: "9b5e2a74-0c3f-4d18-b6a9-7f1e4c8d2a35", cost_usd: 0, duration_seconds: 6, late_seconds: 74,
  }),
  // The release schedule was mid-run for Solo when this one came due.
  run("2026-08-24T07:00:41+00:00", "skipped", { reason: "project_busy", duration_seconds: 0, late_seconds: 41 }),
  run("2026-08-17T07:02:05+00:00", "proposed", {
    conversation_id: "1d7c4e93-8f2a-4b60-a5e1-3c9b7d0f2e46", cost_usd: runCostUsd("plan", 1.0, "2026-08-17T07:00:30Z"),
    duration_seconds: 95, late_seconds: 30, feed_days: 2, proposal_id: "prop_solo_w34",
  }),
];

const RELEASE_HISTORY = [
  // v4.2.1, a hotfix: the model read it and proposed nothing.
  run("2026-09-11T14:06:40+00:00", "no_proposal", {
    conversation_id: "7a3d9f15-2e6b-4c84-9d0a-5b1f8e3c7d57", cost_usd: runCostUsd("quiet", 1.0, "2026-09-11T14:05:00Z"),
    duration_seconds: 48, late_seconds: 360,
  }),
  // v4.2.0, the Android onboarding rebuild: day 5 of the 8–14 Sep plan.
  run("2026-09-02T16:08:55+00:00", "proposed", {
    conversation_id: "c5e8b2a6-3d7f-4e19-8b4c-6a0d2f9e1b68", cost_usd: runCostUsd("plan", 1.1, "2026-09-02T16:07:10Z"),
    duration_seconds: 105, late_seconds: 430, feed_days: 1, proposal_id: "prop_solo_rel420",
  }),
  run("2026-08-24T07:01:52+00:00", "proposed", {
    conversation_id: "2b6f0d38-9a4c-4f27-a1e5-8d3c7b9f0a79", cost_usd: runCostUsd("plan", 0.9, "2026-08-24T07:00:05Z"),
    duration_seconds: 107, late_seconds: 5, feed_days: 1, proposal_id: "prop_solo_rel413",
  }),
];

// The outcomes the monthly cap counts (service/schedules.SPENT), this UTC month.
const SPENT = new Set(["proposed", "no_proposal", "failed"]);
const spentThisMonth = (rows) => rows.filter((r) => SPENT.has(r.outcome) && r.at.startsWith("2026-09")).length;

// routes/schedules.py _out()
function scheduleOut(base, history, { waiting }) {
  const recent = history.slice(0, 8);
  return {
    ...base,
    last_run_at: recent[0]?.at ?? null,
    last_outcome: recent[0]?.outcome ?? "",
    needs_reason: "",
    running: false,
    runs_this_month: spentThisMonth(history),
    last: recent[0] ?? null,
    recent: recent.map((r) => ({ at: r.at, outcome: r.outcome, will_retry: r.will_retry })),
    waiting,
  };
}

// FeedOptions.model_dump(mode="json"): every field, defaults included.
const feed = (sources, disclosure) => ({ sources, look_back_days: null, max_days: 2, disclosure, notion_database: "" });

function schedules(projectId) {
  return [
    // Made from the plan board's From your work sheet, which sets no name.
    scheduleOut(
      {
        id: WEEKLY_ID, project_id: projectId, job: "content.plan_from_work", name: "",
        cadence: "weekly", at_time: "09:00", weekday: 0, timezone: "Europe/Madrid",
        enabled: true, host: "cloud", monthly_cap: 6,
        config: { feed: feed(["github", "duct"], "shipped"), horizon: 7 },
        // next_run_after adds the schedule's own jitter to Monday 09:00.
        next_run_at: "2026-09-21T07:02:00+00:00",
        mine: true,
      },
      WEEKLY_HISTORY,
      { waiting: true },
    ),
    // Priya made this one, so it is not Maya's to delete.
    scheduleOut(
      {
        id: RELEASE_ID, project_id: projectId, job: "content.plan_from_work", name: "",
        cadence: "on_release", at_time: "09:00", weekday: 0, timezone: "Europe/Madrid",
        enabled: true, host: "cloud", monthly_cap: 4,
        config: { feed: feed(["github"], "releases"), horizon: 7 },
        next_run_at: "2026-09-14T08:05:00+00:00",
        mine: false,
      },
      RELEASE_HISTORY,
      { waiting: false },
    ),
  ];
}

// --- Models ------------------------------------------------------------------

// routes/providers.py models_catalogue(), generated from the backend's own
// enums (ModelName, MODEL_LABELS, _MODEL_TIER_HINT, PROVIDER_TRIPLES, JOB_TIER,
// ImageModel, VideoModel). No Ollama models: the hosted instance offers none.
const M = (id, label, provider, tier_hint) => ({ id, label, provider, tier_hint, engines: ["v1"] });
const CATALOGUE = {
  models: [
    M("gpt-6-astra", "GPT-6 Astra", "openai", "heavy"),
    M("gpt-6.1-sol", "GPT-6.1 Sol", "openai", "heavy"),
    M("gpt-6-luna", "GPT-6 Luna", "openai", "light"),
    M("gpt-5-mini", "GPT-5 mini", "openai", "light"),
    M("gpt-4o", "GPT-4o", "openai", "standard"),
    M("gpt-4o-mini", "GPT-4o mini", "openai", "light"),
    M("gemini-3.1-pro-preview", "Gemini 3.1 Pro (preview)", "google_genai", "heavy"),
    M("gemini-3.8-flash", "Gemini 3.8 Flash", "google_genai", "standard"),
    M("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "google_genai", "light"),
    M("gemini-2.5-flash", "Gemini 2.5 Flash", "google_genai", "light"),
    M("claude-fable-5-1", "Claude Fable 5.1", "anthropic", "heavy"),
    M("claude-opus-5-5", "Claude Opus 5.5", "anthropic", "heavy"),
    M("claude-sonnet-5-5", "Claude Sonnet 5.5", "anthropic", "standard"),
    M("claude-haiku-5-5", "Claude Haiku 5.5", "anthropic", "light"),
    M("grok-4.7", "Grok 4.7", "xai", "heavy"),
    M("deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "openrouter", "standard"),
    M("deepseek/deepseek-v4-pro-0813", "DeepSeek V4 Pro", "openrouter", "standard"),
    M("qwen/qwen3.8-flash", "Qwen3.8 Flash", "openrouter", "standard"),
    M("moonshotai/kimi-k3", "Kimi K3", "openrouter", "standard"),
    M("z-ai/glm-5.3-flash", "GLM-5.3 Flash", "openrouter", "standard"),
    M("anthropic/claude-opus-5.5", "Claude Opus 5.5", "openrouter", "standard"),
    M("anthropic/claude-sonnet-5.5", "Claude Sonnet 5.5", "openrouter", "standard"),
    M("openai/gpt-6-luna", "GPT-6 Luna", "openrouter", "standard"),
  ],
  tiers: [
    { id: "heavy", default_model: "gemini-3.1-pro-preview", jobs: ["analysis", "audit"] },
    { id: "standard", default_model: "gemini-3.8-flash", jobs: ["verification", "synthesis", "drafting", "chat"] },
    { id: "light", default_model: "gemini-3.5-flash-lite", jobs: ["research", "memory", "recap"] },
  ],
  provider_triples: {
    google_genai: { heavy: "gemini-3.1-pro-preview", standard: "gemini-3.8-flash", light: "gemini-3.5-flash-lite" },
    anthropic: { heavy: "claude-opus-5-5", standard: "claude-sonnet-5-5", light: "claude-haiku-5-5" },
    openai: { heavy: "gpt-6.1-sol", standard: "gpt-6.1-sol", light: "gpt-6-luna" },
    openrouter: { heavy: "moonshotai/kimi-k3", standard: "deepseek/deepseek-v4-pro-0813", light: "deepseek/deepseek-v4.1-flash" },
    xai: { heavy: "grok-4.7", standard: "grok-4.7", light: "grok-4.7" },
  },
  jobs: [
    { id: "analysis", tier: "heavy" }, { id: "audit", tier: "heavy" },
    { id: "verification", tier: "standard" }, { id: "synthesis", tier: "standard" },
    { id: "drafting", tier: "standard" }, { id: "chat", tier: "standard" },
    { id: "research", tier: "light" }, { id: "memory", tier: "light" }, { id: "recap", tier: "light" },
  ],
  image_models: [
    { id: "gemini-3.1-flash-image", label: "Gemini 3.1 Flash Image", provider: "google_genai", default: true },
    { id: "gemini-3.1-flash-lite-image", label: "Gemini 3.1 Flash-Lite Image", provider: "google_genai", default: false },
    { id: "gemini-3-pro-image", label: "Gemini 3 Pro Image", provider: "google_genai", default: false },
    { id: "gpt-image-2.5-flare", label: "GPT Image 2.5 Flare", provider: "openai", default: true },
    { id: "gpt-image-2.5-sunburst", label: "GPT Image 2.5 Sunburst", provider: "openai", default: false },
    { id: "gpt-image-2", label: "GPT Image 2", provider: "openai", default: false },
    { id: "grok-imagine-image-2.0", label: "Grok Imagine 2.0", provider: "xai", default: true },
    { id: "google/gemini-3.1-flash-image", label: "Gemini 3.1 Flash Image", provider: "openrouter", default: true },
    { id: "bytedance-seed/seedream-5-0-pro", label: "Seedream 5 Pro", provider: "openrouter", default: false },
    { id: "black-forest-labs/flux.2-pro", label: "FLUX.2 Pro", provider: "openrouter", default: false },
    { id: "recraft/recraft-v4-styles-vector", label: "Recraft V4 Vector (SVG)", provider: "openrouter", default: false },
  ],
  image_provider_order: ["google_genai", "openai", "xai", "openrouter"],
  video_models: [
    { id: "veo-3.1-generate-preview", label: "Veo 3.1", provider: "google_genai", default: false },
    { id: "veo-3.1-fast-generate-preview", label: "Veo 3.1 Fast", provider: "google_genai", default: false },
    { id: "veo-3.1-lite-generate-preview", label: "Veo 3.1 Lite", provider: "google_genai", default: true },
    { id: "bytedance/seedance-2.5", label: "Seedance 2.5", provider: "openrouter", default: false },
    { id: "bytedance/seedance-2.0-mini", label: "Seedance 2.0 Mini", provider: "openrouter", default: true },
  ],
  video_provider_order: ["google_genai", "openrouter"],
};

// Heavy and Standard on her Anthropic key; Light on her ChatGPT plan.
const TIERS = { heavy: "claude-opus-5-5", standard: "claude-sonnet-5-5", light: "gpt-6-luna" };

// --- Project config ----------------------------------------------------------

// service/project_config.py get_project_config(): the north-star and growth
// stage lists narrow by industry and business model.
const opts = (values) => values.map((v) => ({ value: v, label: v }));
const INDUSTRY_OPTIONS = opts([
  "E-commerce & Retail", "Fashion & Beauty", "SaaS & Software", "Financial Services", "Healthcare", "Education",
  "Professional Services", "Marketing & Advertising", "Real Estate", "Travel & Hospitality", "Other",
]);
const BUSINESS_MODEL_OPTIONS = opts(["B2B", "B2C", "Marketplace", "PLG", "Agency", "Hybrid"]);
const GROWTH_STAGES = [
  { value: "0_pre_customer", label: "No customers or active users yet" },
  { value: "1_first_users", label: "First active users/customers (1-10)" },
  { value: "2_early_revenue", label: "Early repeat usage or revenue (10-100 customers)" },
  { value: "3_repeatable_growth", label: "Repeatable growth motion (100+ customers or steady MoM growth)" },
  { value: "4_scaling", label: "Scaling across channels or segments with predictable performance" },
];
const projectConfig = (northStar, stages) => ({
  industry_options: INDUSTRY_OPTIONS,
  business_model_options: BUSINESS_MODEL_OPTIONS,
  north_star_metric_options: opts(northStar),
  growth_stage_milestone_options: GROWTH_STAGES.filter((s) => stages.includes(s.value)),
});
const ALL_NORTH_STAR = ["Weekly active users", "Monthly active customers", "Qualified leads", "Pipeline created", "Net new revenue", "Retention rate", "Bookings", "Custom"];

const INDUSTRY = "Financial Services";
const BUSINESS_MODEL = "B2C";

// --- Routes ------------------------------------------------------------------

export function routes(story) {
  const { STORY } = story;
  const pid = STORY.project.id;
  const user = STORY.user;

  const memberList = {
    project_id: pid,
    project_name: STORY.project.name,
    viewer_role: "owner",
    members: [
      { user_id: MAYA_ID, email: user.email, full_name: user.name, avatar_url: "", role: "owner", joined_at: "2026-08-02T09:05:00+00:00", is_you: true },
      { user_id: PRIYA.id, email: PRIYA.email, full_name: PRIYA.name, avatar_url: "", role: "collaborator", joined_at: "2026-08-20T11:42:00+00:00", is_you: false },
    ],
    invitations: [
      {
        id: INVITE_ID, email: JONAS.email, role: "collaborator", status: "pending",
        expires_at: INVITE_EXPIRES, created_at: INVITE_CREATED, last_sent_at: INVITE_CREATED,
        invited_by_email: user.email, is_expired: false,
      },
    ],
    // Hosted Duct sends through Cloudflare; "console" would raise the
    // "email isn't configured" warning on the page.
    email_delivery: "cloudflare",
  };

  const rows = schedules(pid);
  const query = new URLSearchParams({ industry: INDUSTRY, business_model: BUSINESS_MODEL }).toString();

  return {
    // routes/project_members.py list_members -> MembersResponse
    [`GET /api/user/projects/${pid}/members`]: memberList,

    // routes/schedules.py list_schedules -> [_out(row)]
    [`GET /api/user/schedules?project_id=${pid}`]: rows,
    "GET /api/user/schedules": rows,
    // routes/schedules.py schedule_history -> service/schedules.history()
    [`GET /api/user/schedules/${WEEKLY_ID}/history`]: WEEKLY_HISTORY,
    [`GET /api/user/schedules/${RELEASE_ID}/history`]: RELEASE_HISTORY,

    // routes/usage.py get_usage -> UsageSummary.as_dict()
    "GET /api/user/usage?window_days=7": usage(7),
    "GET /api/user/usage?window_days=30": usage(30),
    "GET /api/user/usage?window_days=90": usage(90),

    // routes/profile.py read_profile -> _payload()
    "GET /api/user/profile": {
      display_name: user.name.split(" ")[0],
      // ROLE_OPTIONS is a fixed list (lib/userProfile.js); "Head of Growth" is not on it.
      role: "Growth Manager",
      writing_preset: "practitioner",
      communication_language: "English",
      timezone: "Europe/Madrid",
      // "" follows the browser. A set value writes the duct_lang cookie on
      // every app page ((app)/layout.js), which would pin captures to it.
      interface_language: "",
      notes: "Number first, then the why. Euros, and the week starts on Monday. Flag anything that touches the Android onboarding before you recommend spend.",
      communication_style: "practitioner",
      report_depth: "balanced",
      notes_max_chars: 1000,
      presets: ["executive", "practitioner", "technical"],
    },

    // routes/model_settings.py read_model_settings -> _payload()
    "GET /api/user/model-settings": { tiers: TIERS, auto_fallback: true, engine: "", image_model: "", video_model: "" },
    // routes/providers.py get_models_catalogue -> models_catalogue()
    "GET /api/models/catalogue": CATALOGUE,
    // routes/providers.py models_preview: what the saved map runs on. The
    // page asks on every load; without it the tier rows have no key chips.
    "POST /api/models/preview": {
      engine: "v1",
      tiers: Object.entries(TIERS).map(([id, model]) => ({
        id, model, provider: PROVIDER_OF[model], runnable: true, serves: null, reason: null,
      })),
    },

    // routes/projects.py get_projects_config: the page asks with the
    // project's industry and model (URLSearchParams spelling); bare is the
    // unfiltered list.
    [`GET /api/projects/config?${query}`]: projectConfig(
      ["Qualified leads", "Pipeline created", "Net new revenue", "Retention rate", "Bookings", "Custom"],
      ["1_first_users", "2_early_revenue", "3_repeatable_growth", "4_scaling"],
    ),
    "GET /api/projects/config": projectConfig(ALL_NORTH_STAR, GROWTH_STAGES.map((s) => s.value)),

    // routes/mcp_oauth.py describe_request -> ConsentRequestOut. Claude Code
    // registers as "<product> (<server name>)" and redirects to a loopback
    // port, which service/mcp_server/oauth.destination() calls "device".
    "GET /api/oauth/requests/r1": { client_name: "Claude Code (duct)", destination: "device", destination_name: "localhost" },

    // routes/project_members.py preview_invitation -> InvitePreviewOut
    "GET /api/invitations/tok1": {
      project_name: STORY.project.name,
      invited_email: JONAS.email,
      inviter_name: user.name,
      inviter_email: user.email,
      role: "collaborator",
      expires_at: INVITE_EXPIRES,
    },
  };
}

// --- The project, as lib/projects.js keeps it --------------------------------

/**
 * One entry of localStorage "duct_projects": the local shape withProjectDefaults
 * reads (company/targets/audience/competition/brand_channels at the top level,
 * provenance beside them), not the API row. `updatedAt` is set so a hydrate
 * against GET /api/user/projects keeps this copy (local wins when newer).
 */
export function projectProfile(story) {
  const { STORY } = story;
  return {
    id: STORY.project.id,
    name: STORY.project.name,
    createdAt: "2026-08-02T09:05:00.000Z",
    updatedAt: "2026-09-12T08:15:00.000Z",
    role: "owner",
    ownerEmail: STORY.user.email,
    autonomyLevel: "assisted",
    company: {
      name: STORY.company.name,
      pitch: "Budgeting for freelancers: every payment split into tax, bills and money that is safe to spend.",
      industry: INDUSTRY,
      business_model: BUSINESS_MODEL,
      website_url: `https://${STORY.company.site}`,
    },
    targets: {
      monthly_budget: "13000",
      target_cpa: String(STORY.targets.cpa),
      target_roas: "2.5",
      primary_kpi: "Weekly signups",
      north_star_metric: "Retention rate",
      north_star_goal_window: `${STORY.targets.weeklySignups} signups a week at a €${STORY.targets.cpa} CPA, with day-7 retention back above 50% on Android.`,
      north_star_constraints: "Android onboarding. Since the 2 Sep rebuild, people who deny the bank permission land on an empty screen and leave.",
      growth_stage_milestone: "3_repeatable_growth",
      growth_stage_context: `Team of six, two in growth. ${STORY.numbers.mrr} MRR; paid search and Performance Max bring most signups.`,
    },
    audience: {
      primary_segment: "Consumer",
      personas: [
        {
          name: "Freelancers with uneven income",
          description: "Designers, developers and writers in the EU who invoice several clients, get paid late and dread the quarterly tax bill. They open the app to see what is safe to spend today.",
          priority: "primary",
        },
        {
          name: "First-year freelancers",
          description: "Just left a salaried job. No idea how much to put aside for tax, and no system yet for late invoices.",
          priority: "secondary",
        },
      ],
    },
    competition: {
      compare_against: "Ledgerly, Tallyo",
      competitors: [
        { name: "Ledgerly", differentiator: "Full bookkeeping for freelancers. Heavier to set up, priced with accountants in mind." },
        { name: "Tallyo", differentiator: "Invoicing first, budgeting as an add-on. Outranks Solo on invoice-template searches." },
      ],
      positioning_statement: "For EU freelancers with uneven income, Solo is the budgeting app that puts tax money aside the day a payment lands, so what is left is safe to spend.",
    },
    brand_channels: {
      brand_voice: "Friendly",
      growth_motions: ["Paid", "Organic", "Product-led"],
      context_notes: "Reports in euros; the week starts on Monday. Leave “Solo · Brand · Legacy” paused until the rebrand ships. Brand search may run under the CPA target.",
      active_channels: ["tiktok", "instagram", "youtube"],
      seasonality_notes: "Quarterly tax deadlines in January, April, July and October. September is back-to-work and the busiest signup month.",
    },
    // Most fields are Maya's; four are still the audit's draft, so the
    // About and Competition steps show both chip kinds.
    provenance: {
      name: "user",
      company_name: "user",
      pitch: "crawl",
      website_url: "crawl",
      industry: "inferred",
      business_model: "user",
      personas: "user",
      compare_against: "inferred",
      competitors: "user",
      brand_voice: "user",
      active_channels: "user",
    },
  };
}
