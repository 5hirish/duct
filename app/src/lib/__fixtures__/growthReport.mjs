/**
 * One growth report, as the agent writes it and the backend stores it
 * (backend/agents/insights/report.py), for /preview and the component halves
 * the Analytics tab draws. Invented numbers for an invented product; the
 * shapes are the contract's.
 */

export const REPORT_SOURCES = [
  { id: "gsc", label: "Search Console", kind: "connector", gives: "organic clicks, impressions, queries, pages", status: "ready", detail: "sc-domain:solomoney.app" },
  { id: "ga4", label: "Google Analytics", kind: "connector", gives: "sessions, landing pages, conversion paths", status: "ready", detail: "Solo Money — web" },
  { id: "posthog", label: "PostHog", kind: "mcp", gives: "product analytics: signups, activation, retention", status: "ready", detail: "PostHog" },
  { id: "publishers", label: "Social posts", kind: "publishers", gives: "views, likes, comments and shares per post", status: "ready", detail: "Zernio" },
  { id: "openseo", label: "OpenSEO", kind: "mcp", gives: "rankings, keyword volumes, backlinks", status: "needs_attention", detail: "OpenSEO" },
  { id: "google_ads", label: "Google Ads", kind: "connector", gives: "spend, conversions, campaigns", status: "not_connected", detail: "" },
  { id: "mixpanel", label: "Mixpanel", kind: "connector", gives: "product events, activation", status: "needs_account", detail: "" },
];

export const REPORT_SOURCES_NONE = REPORT_SOURCES.map((s) => ({ ...s, status: "not_connected", detail: "" }));

export const REPORT_TEMPLATES = [
  { id: "growth_overview", label: "Growth overview", description: "Search, traffic, posts and signups on one page, with what moved and what to do.", sources: ["gsc", "ga4", "posthog", "publishers", "openseo", "google_ads", "mixpanel"] },
  { id: "seo", label: "Search", description: "Organic clicks, the queries and pages behind them, rankings and what to fix.", sources: ["gsc", "openseo", "ga4"] },
  { id: "social", label: "Social posts", description: "How the posts did, by platform and pillar, and what they sent to the site.", sources: ["publishers", "ga4", "posthog"] },
  { id: "product", label: "Product", description: "Signups, activation, retention and the friction in between.", sources: ["posthog", "mixpanel", "ga4", "clarity", "growthbook"] },
];

const DAYS = Array.from({ length: 30 }, (_, i) => `2026-10-${String(i + 1).padStart(2, "0")}`);
const CLICKS = [88, 94, 91, 102, 97, 70, 64, 110, 118, 121, 126, 171, 182, 177, 190, 188, 150, 141, 196, 203, 199, 210, 206, 171, 164, 215, 221, 218, 229, 224];

export const GROWTH_REPORT = {
  title: "Organic clicks up a third; signups flat",
  date_from: "2026-10-01",
  date_to: "2026-10-30",
  verdict: "Organic clicks rose 34% to 4,210 while signups held at 61. Fix the pricing page's form before buying more traffic.",
  summary: "Three guide posts started ranking on the 12th and now carry 45% of organic clicks. The new visitors land on pricing, where 38% leave without scrolling; the signup rate per pricing visit fell from 7.1% to 5.5%.",
  takeaway: "Traffic is not the constraint this month; the pricing form is.",
  sources: [
    { id: "gsc", label: "Search Console", status: "read", window: "1–30 Oct 2026" },
    { id: "ga4", label: "Google Analytics", status: "read", window: "1–30 Oct 2026" },
    { id: "publishers", label: "Social posts", status: "read", window: "1–30 Oct 2026" },
    { id: "posthog", label: "PostHog", status: "failed", note: "The server needs signing in again." },
  ],
  blocks: [
    {
      block_id: "headline", block_type: "kpi_strip", title: "Headline numbers",
      kpis: [
        { label: "Organic clicks", value: "4,210", delta: "+34% vs 1–30 Sep", tone: "good", source: "Search Console" },
        { label: "Sessions", value: "9,860", delta: "+18% vs 1–30 Sep", tone: "good", source: "Google Analytics" },
        { label: "Signups", value: "61", delta: "±0 vs 1–30 Sep", tone: "neutral", source: "Google Analytics" },
        { label: "Post views", value: "31,400", delta: "−12% vs 1–30 Sep", tone: "bad", source: "Zernio" },
      ],
      insight_note: "Clicks and sessions moved; signups did not. The gap is on the site, not in search.",
    },
    {
      block_id: "traffic", block_type: "time_series", title: "Organic clicks by day",
      source: "Search Console", window: "1–30 Oct 2026",
      rows: DAYS.map((date, i) => ({ date, clicks: CLICKS[i] })),
      x_field: "date", y_field: "clicks", y_unit: "clicks",
      insight_note: "A step up on 12 Oct, the day the agentic-workflow guide was indexed; the level held after it.",
    },
    {
      block_id: "channels", block_type: "bar_chart", title: "Where visitors came from",
      source: "Google Analytics", window: "1–30 Oct 2026",
      rows: [
        { channel: "Organic Search", sessions: 4320 }, { channel: "Direct", sessions: 2110 }, { channel: "Social", sessions: 1480 },
        { channel: "Referral", sessions: 960 }, { channel: "Email", sessions: 610 }, { channel: "Paid Search", sessions: 380 },
      ],
      x_field: "channel", y_field: "sessions", y_unit: "sessions",
      insight_note: "Organic is 44% of sessions and grew fastest; social fell with post views.",
    },
    {
      block_id: "queries", block_type: "table", title: "Queries that moved",
      source: "Search Console", window: "1–30 Oct 2026",
      rows: [
        { query: "agentic workflow", clicks: 612, impressions: 14800, ctr: "4.1%", position: 5.2 },
        { query: "ai agents for marketing", clicks: 498, impressions: 21300, ctr: "2.3%", position: 7.8 },
        { query: "ai agent vs agentic ai", clicks: 371, impressions: 9100, ctr: "4.1%", position: 4.9 },
        { query: "local ai agents", clicks: 260, impressions: 12200, ctr: "2.1%", position: 8.4 },
        { query: "solo money", clicks: 244, impressions: 2900, ctr: "8.4%", position: 1.2 },
      ],
      x_field: "query", y_field: "clicks",
      insight_note: "Four of the five are the guide cluster; the fifth is the brand.",
    },
    {
      block_id: "posts", block_type: "bar_chart", title: "Posts by views",
      source: "Zernio", window: "1–30 Oct 2026",
      rows: [
        { post: "3 invoicing mistakes (LinkedIn)", views: 9100 }, { post: "Agentic workflow, explained (LinkedIn)", views: 6400 },
        { post: "The 4-line checklist (X)", views: 4800 }, { post: "Deposit on jobs over $500 (LinkedIn)", views: 3900 },
        { post: "Chasing payment by text (X)", views: 2200 },
      ],
      x_field: "post", y_field: "views", y_unit: "views",
      insight_note: "Engagement rate 3.9% overall; the checklist post saved at twice the rate of the rest.",
    },
    {
      block_id: "platforms", block_type: "pie_chart", title: "Views by platform",
      source: "Zernio", window: "1–30 Oct 2026",
      rows: [{ platform: "LinkedIn", views: 21400 }, { platform: "X", views: 7600 }, { platform: "TikTok", views: 2400 }],
      x_field: "platform", y_field: "views",
      insight_note: "LinkedIn is two thirds of views on a third of the posts.",
    },
    {
      block_id: "signals", block_type: "signal_list", title: "What moved",
      signals: [
        { id: "s1", kind: "win", title: "The guide cluster ranks", impact: "Three posts, 1,900 clicks in October, 45% of organic.", action: "Publish the fourth guide this week.", source: "Search Console" },
        { id: "s2", kind: "risk", title: "Pricing page leaks the new traffic", impact: "38% of 1,100 pricing visits leave without scrolling; signups per visit fell from 7.1% to 5.5%.", action: "Drop the company field from the form.", source: "Google Analytics" },
        { id: "s3", kind: "watch", title: "Post views down 12%", impact: "Fewer posts (11 against 16), not weaker ones: views per post rose 9%.", action: "Hold the cadence at three a week.", source: "Zernio" },
      ],
    },
    {
      block_id: "actions", block_type: "action_list", title: "What to do next",
      actions: [
        { id: "a1", title: "Fix the pricing form", detail: "Drop the company field and move the plan picker above the fold.", size: "about 420 of 1,100 pricing visits", effort: "a form change, no backend", check: "signups per pricing visit back above 7% in two weeks", owner: "Shirish" },
        { id: "a2", title: "Publish the fourth guide", detail: "The cluster hub links to it already.", size: "~400 clicks a month at the cluster's rate", effort: "one post", check: "impressions on the hub within ten days", owner: "Duct" },
        { id: "a3", title: "Sign PostHog back in", detail: "Signups by source could not be read this month.", size: "closes the biggest gap below", effort: "a click in the Toolbox", check: "the next report shows the product block", owner: "Shirish" },
      ],
    },
  ],
  could_not_check: [
    "Signups by source: PostHog needs signing in again.",
    "Whether the social sessions converted: no key event is set in Google Analytics.",
  ],
  method_note: "1–30 Oct against 1–30 Sep. Brand queries (14% of clicks) excluded from the query table. 47 of 48 posts carried a posting date; one did not and is left out.",
};

/** The GET payload around that report, in the states the tab draws. */
export function reportPayload(state = "fresh", overrides = {}) {
  const base = {
    template: REPORT_TEMPLATES[0],
    templates: REPORT_TEMPLATES,
    sources: REPORT_SOURCES,
    report: null,
    generating: false,
    started_at: null,
    run_sources: [],
    error: null,
    ttl_hours: 24,
  };
  const stored = (hoursAgo) => ({
    artifact_id: "art_1", group_id: "grp_1", version: 3, title: GROWTH_REPORT.title,
    generated_at: new Date(Date.now() - hoursAgo * 3600 * 1000).toISOString(),
    stale: hoursAgo > 24,
    stale_after: new Date(Date.now() + (24 - hoursAgo) * 3600 * 1000).toISOString(),
    template: "growth_overview",
    report: GROWTH_REPORT,
  });
  const states = {
    no_sources: { sources: REPORT_SOURCES_NONE },
    empty: {},
    generating: { generating: true, started_at: new Date(Date.now() - 70 * 1000).toISOString(), run_sources: ["gsc", "ga4", "publishers"] },
    generating_with_old: { generating: true, started_at: new Date(Date.now() - 20 * 1000).toISOString(), run_sources: ["gsc", "ga4"], report: stored(40) },
    fresh: { report: stored(3) },
    stale: { report: stored(40) },
    failed: { error: { code: "report_invalid", retryable: true, error: "The agent could not write a report the tab can draw." } },
    failed_with_old: { report: stored(30), error: { code: "provider_unavailable", retryable: true, error: "The model provider is unavailable right now." } },
  };
  return { ...base, ...(states[state] || {}), ...overrides };
}
