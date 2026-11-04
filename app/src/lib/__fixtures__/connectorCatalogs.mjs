// The Connections catalogue at every size it has to survive.
//
// Today it is thirteen native connectors and six MCP presets. Presets grow on
// the server and anyone can add a server by address, so these are that list
// on day one, at two hundred, for someone with forty connected, and with
// names a translator or a vendor made long. Plain data in the shape
// lib/connectorCatalog.js arranges; the /preview scenes draw them as tiles and
// the unit tests hold the arrangement to them.
//
// Every vendor past the real ones is invented.

const NATIVE = [
  ["gsc", "Google Search Console", "Search queries, clicks, impressions and average position.", "search"],
  ["ga4", "Google Analytics", "Traffic, sessions, engagement and conversions.", "analytics"],
  ["gtm", "Google Tag Manager", "Tags, variables and container versions, staged, with rollback.", "analytics"],
  ["clarity", "Microsoft Clarity", "Rage clicks, dead clicks, quick-backs and script errors, per page.", "analytics"],
  ["google_ads", "Google Ads", "Spend, clicks, impressions, conversions and ROAS, per campaign.", "advertising"],
  ["meta_ads", "Meta Ads", "Facebook and Instagram spend, reach, conversions and CPA.", "advertising"],
  ["apple_ads", "Apple Search Ads", "Spend, taps and installs, by campaign and search term.", "advertising"],
  ["openai_ads", "OpenAI Ads", "Impressions, clicks and spend. Conversions stay in Ads Manager.", "advertising"],
  ["mixpanel", "Mixpanel", "Signups, logins and upgrades, one name across web and app.", "product"],
  ["growthbook", "GrowthBook", "Which tests are live, whether they still bucket, per-metric results.", "product"],
  ["stripe", "Stripe", "Settled revenue, subscriptions, refunds and payment outcomes.", "revenue"],
  ["revenuecat", "RevenueCat", "Trials, renewals, refunds and MRR across the App Store and Play.", "revenue"],
  ["github", "GitHub", "Merged pull requests, releases, closed issues and doc changes, by date.", "developer"],
];

const PRESETS = [
  ["openseo", "OpenSEO", "Keyword volume, difficulty and backlinks for the topics you ask about.", "search"],
  ["posthog", "PostHog", "Events, funnels and insights from your product analytics.", "product"],
  ["notion", "Notion", "Read and write pages in your Notion workspace.", "productivity"],
  ["linear", "Linear", "Look up issues and projects, or file a new issue.", "productivity"],
  ["railway", "Railway", "Your Railway projects: services, deployments, logs and variables.", "developer"],
  ["cloudflare", "Cloudflare", "Your Cloudflare account through its API: Workers, DNS, zones and analytics.", "developer"],
];

export const STARTERS = ["gsc", "ga4", "google_ads", "stripe"];

function native([id, title, description, category], status = "available") {
  return { id, title, description, category, status, origin: "duct", publisher: "Duct", keywords: [], logo: title };
}

function preset([id, title, description, category], status = "available") {
  return { id: `mcp:${id}`, title, description, category, status, origin: "vendor", publisher: title, keywords: [], logo: title };
}

function yours(i, status = "connected") {
  const host = `tools-${i}.example.com`;
  return { id: `mcp-url:${i}`, title: host, description: host, category: "other", status, origin: "yours", publisher: "", keywords: [], logo: host };
}

/** Mulberry32, so a seed is the same catalogue on every machine. */
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

const CATEGORIES = ["search", "analytics", "advertising", "product", "revenue", "productivity", "design", "developer", "other"];
const SYLLABLES = ["lu", "mi", "ra", "to", "ve", "zo", "ka", "ni", "pe", "sol", "tri", "vox", "quin", "dar", "bel"];
const NOUNS = ["Desk", "Hub", "Flow", "Board", "Pulse", "Lens", "Forge", "Base", "Grid", "Kit"];
const WHATS = {
  search: "Rankings, crawl errors and keyword gaps across your sites.",
  analytics: "Visits, sources and goals, by page and by day.",
  advertising: "Spend, clicks and conversions, per campaign and creative.",
  product: "Events, cohorts and retention from your product.",
  revenue: "Invoices, renewals and churn, reconciled daily.",
  productivity: "Docs, tasks and comments from your team's workspace.",
  design: "Frames, components and comments from your design files.",
  developer: "Deploys, logs and incidents from your infrastructure.",
  other: "Tools from a server your team runs.",
};

function vendor(r, i) {
  const name = `${SYLLABLES[Math.floor(r() * SYLLABLES.length)]}${SYLLABLES[Math.floor(r() * SYLLABLES.length)]}`;
  const title = `${name[0].toUpperCase()}${name.slice(1)} ${NOUNS[Math.floor(r() * NOUNS.length)]}`;
  const category = CATEGORIES[Math.floor(r() * CATEGORIES.length)];
  return { id: `mcp:gen-${i}`, title, description: WHATS[category], category, status: "available", origin: "vendor", publisher: title, keywords: [], logo: title };
}

/** Any catalogue: the real ones, `extra` generated vendors, some connected. */
export function randomCatalog(seed, { extra = 200 } = {}) {
  const r = rng(seed);
  const pick = () => {
    const roll = r();
    return roll < 0.08 ? "connected" : roll < 0.1 ? "attention" : "available";
  };
  const entries = [
    ...NATIVE.map((n) => native(n, pick())),
    ...PRESETS.map((p) => preset(p, pick())),
    ...Array.from({ length: Math.floor(r() * extra) }, (_, i) => ({ ...vendor(r, i), status: pick() })),
  ];
  const own = Math.floor(r() * 5);
  for (let i = 0; i < own; i += 1) entries.push(yours(i, r() < 0.8 ? "connected" : "attention"));
  return entries;
}

export const CATALOG_SCENARIOS = [
  {
    id: "today",
    title: "Today: two connected, nineteen to choose from",
    expect: "Tabs in the header; the starters, then one grid with the connected two first; chips list only the categories that have something.",
    build: () => [
      ...NATIVE.map((n) => native(n, n[0] === "gsc" || n[0] === "ga4" ? "connected" : "available")),
      ...PRESETS.map((p) => preset(p)),
    ],
  },
  {
    id: "first-day",
    title: "First day, nothing connected",
    expect: "No tabs yet, since every tab would say what All says; the four starters lead.",
    build: () => [...NATIVE.map((n) => native(n)), ...PRESETS.map((p) => preset(p))],
  },
  {
    id: "hundreds",
    title: "Two hundred MCP servers in the list",
    expect: "One section per category, six tiles each with Show all; the chips carry the counts.",
    build: () => {
      const r = rng(7);
      const entries = [
        ...NATIVE.map((n) => native(n, ["gsc", "ga4", "stripe"].includes(n[0]) ? "connected" : "available")),
        ...PRESETS.map((p) => preset(p, p[0] === "notion" ? "attention" : "available")),
        ...Array.from({ length: 200 }, (_, i) => vendor(r, i)),
        yours(1),
      ];
      return entries;
    },
  },
  {
    id: "power-user",
    title: "Forty connected",
    expect: "The Connected tab holds forty, past the 24 that fit one grid, so it splits by category with Show all.",
    build: () => {
      const r = rng(11);
      return [
        ...NATIVE.map((n) => native(n, "connected")),
        ...PRESETS.map((p) => preset(p, "connected")),
        ...Array.from({ length: 60 }, (_, i) => ({ ...vendor(r, i), status: i < 21 ? "connected" : "available" })),
      ];
    },
  },
  {
    id: "long-and-foreign",
    title: "Long vendor names, German and Japanese copy",
    expect: "Titles truncate on one line, descriptions clamp at two; chips wrap rather than scroll the page sideways.",
    build: () => [
      native(["gsc", "Google Search Console", "Suchanfragen, Klicks, Impressionen und durchschnittliche Position.", "search"], "connected"),
      native(["ga4", "Google Analytics", "トラフィック、セッション、エンゲージメント、コンバージョン。", "analytics"]),
      preset(["longname", "Enterprise Customer Data Orchestration Platform for Regulated Industries", "Bidirectional synchronisation of every customer attribute your compliance team has approved, with audit trails.", "other"]),
      preset(["notion", "Notion", "Seiten in deinem Notion-Arbeitsbereich lesen und schreiben.", "productivity"]),
      yours(3),
    ],
  },
];

export function catalogScenario(id) {
  const s = CATALOG_SCENARIOS.find((x) => x.id === id);
  if (!s) throw new Error(`no catalog scenario "${id}"`);
  return s.build();
}
