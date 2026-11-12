/**
 * The Connections page as a catalogue: what each source is filed under, how a
 * search finds it, and how the page arranges whatever set it is handed.
 *
 * The page was three fixed sections (Connected, Worth adding next, More
 * sources) and a fourth for MCP servers, which held at fifteen tiles and does
 * not at two hundred. MCP presets come from a list that grows on the server,
 * and anyone can add a server by address, so how many sources there are, and
 * of which kind, is not known when the page is built. That makes this the same
 * job as the Home desk (lib/desk.js): the arrangement is a pure function of
 * the entries, bounded and tested over generated sets, and the components
 * only draw what it returns.
 *
 * An entry is plain data:
 *   { id, title, description, category, status, origin, publisher, keywords }
 * `title` and `description` arrive translated; everything else is a code.
 *
 * Search, filters and the arrangement are here; the words for a category are
 * `CATEGORY_LABELS`, the only copy in the module.
 */

import { msg } from "@lingui/core/macro";

/** Every filter's "no filter" value. */
export const ALL = "all";

/** What a source is for. Marketing first, because that is what Duct is. */
export const Category = Object.freeze({
  SEARCH: "search",
  ANALYTICS: "analytics",
  ADVERTISING: "advertising",
  PRODUCT: "product",
  REVENUE: "revenue",
  PRODUCTIVITY: "productivity",
  DESIGN: "design",
  DEVELOPER: "developer",
  OTHER: "other",
});

/** The order categories are offered and browsed in. */
export const CATEGORY_ORDER = [
  Category.SEARCH,
  Category.ANALYTICS,
  Category.ADVERTISING,
  Category.PRODUCT,
  Category.REVENUE,
  Category.PRODUCTIVITY,
  Category.DESIGN,
  Category.DEVELOPER,
  Category.OTHER,
];

export const CATEGORY_LABELS = {
  [Category.SEARCH]: msg`Search & SEO`,
  [Category.ANALYTICS]: msg`Analytics`,
  [Category.ADVERTISING]: msg`Advertising`,
  [Category.PRODUCT]: msg`Product`,
  [Category.REVENUE]: msg`Revenue`,
  [Category.PRODUCTIVITY]: msg`Productivity`,
  [Category.DESIGN]: msg`Design`,
  [Category.DEVELOPER]: msg`Developer`,
  [Category.OTHER]: msg`Other`,
};

/** Where a source stands for this account. Needs attention is connected, but
 *  missing a permission or a fresh sign-in, so it counts under Connected too. */
export const ConnectionStatus = Object.freeze({
  CONNECTED: "connected",
  ATTENTION: "attention",
  AVAILABLE: "available",
});

/**
 * Who stands behind a source. One facet rather than "native or MCP" beside
 * "Duct or vendor": today those two split the catalogue identically (every
 * native connector is Duct's, every MCP server is someone else's), so two
 * filters would always agree. The third value is a server added by address,
 * which no catalogue lists and only its owner can vouch for.
 */
export const Origin = Object.freeze({
  DUCT: "duct",
  VENDOR: "vendor",
  YOURS: "yours",
});

/** Filed for each native connector, by `connector_type`. */
export const NATIVE_CATEGORY = {
  gsc: Category.SEARCH,
  ga4: Category.ANALYTICS,
  gtm: Category.ANALYTICS,
  clarity: Category.ANALYTICS,
  google_ads: Category.ADVERTISING,
  meta_ads: Category.ADVERTISING,
  apple_ads: Category.ADVERTISING,
  openai_ads: Category.ADVERTISING,
  mixpanel: Category.PRODUCT,
  growthbook: Category.PRODUCT,
  stripe: Category.REVENUE,
  revenuecat: Category.REVENUE,
  github: Category.DEVELOPER,
  rss: Category.PRODUCT,
};

/**
 * Filed for each MCP preset, by its id. The server holds the preset's facts
 * (`service/mcp/presets.py`) and the app its copy; where it is filed is a
 * reading of what it is for, like its description. A preset missing here is
 * filed under Other until someone files it.
 */
export const MCP_CATEGORY = {
  openseo: Category.SEARCH,
  posthog: Category.PRODUCT,
  notion: Category.PRODUCTIVITY,
  linear: Category.PRODUCTIVITY,
  railway: Category.DEVELOPER,
  cloudflare: Category.DEVELOPER,
};

/**
 * Words a person types that the card does not say: the vendor behind a
 * product name, and the names people still use for it. Search only, so they
 * stay English; every card's own title and description are searched in the
 * reader's language as well.
 */
export const NATIVE_KEYWORDS = {
  gsc: ["google", "seo", "webmaster"],
  ga4: ["google", "ga", "web analytics"],
  gtm: ["google", "tags", "pixel"],
  clarity: ["microsoft", "heatmap", "session recording"],
  google_ads: ["google", "adwords", "ppc", "sem"],
  meta_ads: ["facebook", "instagram", "ppc"],
  apple_ads: ["apple", "app store", "asa"],
  openai_ads: ["chatgpt"],
  mixpanel: ["events", "funnels"],
  growthbook: ["experiments", "a/b test", "feature flags"],
  stripe: ["payments", "billing", "mrr"],
  revenuecat: ["subscriptions", "in-app purchases", "mrr"],
  github: ["git", "repositories", "changelog"],
};

/** Tiles a category shows while browsing before "Show all": two rows. */
export const CATEGORY_PREVIEW = 6;

/**
 * Below this many sources to browse, one grid; above it, one bounded section
 * per category. Nineteen tiles read fine as one grid and split into nine
 * sections of one or two; two hundred in one grid is a scroll with no
 * landmarks.
 */
export const GROUP_ABOVE = 24;

/** Lower case, accents off: "Analítica" is found by "analitica". */
export function normalize(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .trim();
}

function tokensOf(query) {
  return normalize(query).split(/\s+/).filter(Boolean);
}

// How well an entry answers a query, lower is better; null when it does not.
// Every word has to be found somewhere. A title that starts with the whole
// query ranks first, then a word of the title starting with each word typed,
// then the publisher and keywords, then the description.
function score(entry, tokens, categoryLabel) {
  const title = normalize(entry.title);
  const named = normalize([entry.publisher, categoryLabel, ...(entry.keywords || [])].join(" "));
  const described = normalize(entry.description);
  const titleWords = title.split(/[\s/&·-]+/);
  let total = title.startsWith(tokens.join(" ")) ? 0 : 1;
  for (const token of tokens) {
    if (titleWords.some((w) => w.startsWith(token))) continue;
    if (title.includes(token)) total += 1;
    else if (named.includes(token)) total += 2;
    else if (described.includes(token)) total += 3;
    else return null;
  }
  return total;
}

function byTitle(a, b) {
  return a.title.localeCompare(b.title);
}

const isOn = (entry) => entry.status !== ConnectionStatus.AVAILABLE;

/** True when `entry` passes the status filter; Connected takes attention too. */
export function matchesStatus(entry, status) {
  if (!status || status === ALL) return true;
  if (status === ConnectionStatus.CONNECTED) return isOn(entry);
  return entry.status === status;
}

function passes(entry, filters, skip = "") {
  if (skip !== "category" && filters.category && filters.category !== ALL && entry.category !== filters.category) {
    return false;
  }
  if (skip !== "status" && !matchesStatus(entry, filters.status)) return false;
  if (skip !== "origin" && filters.origin && filters.origin !== ALL && entry.origin !== filters.origin) return false;
  return true;
}

/**
 * True when nothing is typed or chosen beyond the status tab: the page
 * browses rather than answers. The tab is where the person stands, not a
 * question they asked, so it keeps the browsing layout.
 */
export function isBrowsing(filters = {}) {
  return !normalize(filters.query) && (filters.category || ALL) === ALL && (filters.origin || ALL) === ALL;
}

// What needs the person first, then what works, then what could: a source
// missing a permission is the one thing on the page that is broken.
const STATUS_RANK = {
  [ConnectionStatus.ATTENTION]: 0,
  [ConnectionStatus.CONNECTED]: 1,
  [ConnectionStatus.AVAILABLE]: 2,
};
const byStatus = (a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status];

/**
 * The entries a query and filters leave, best first. With a query, by how
 * well each answers it; without one, connected first, then by title.
 *
 * @param labelOf (category) => translated label, so "advertising" finds the
 *   ads and "Werbung" does in German.
 */
export function filterCatalog(entries, filters = {}, { labelOf = () => "" } = {}) {
  const tokens = tokensOf(filters.query);
  const kept = [];
  for (const entry of entries) {
    if (!passes(entry, filters)) continue;
    const s = tokens.length ? score(entry, tokens, labelOf(entry.category)) : 0;
    if (s === null) continue;
    kept.push({ entry, s });
  }
  kept.sort((a, b) => a.s - b.s || byStatus(a.entry, b.entry) || byTitle(a.entry, b.entry));
  return kept.map((k) => k.entry);
}

/**
 * How many entries each filter value would leave, with the query and the
 * other filters applied but not its own: the count beside "Advertising" is
 * what clicking it gives, whatever else is chosen.
 */
export function facetCounts(entries, filters = {}, { labelOf = () => "" } = {}) {
  const tokens = tokensOf(filters.query);
  const found = tokens.length ? entries.filter((e) => score(e, tokens, labelOf(e.category)) !== null) : entries;
  const category = { [ALL]: 0 };
  const status = { [ALL]: 0, [ConnectionStatus.CONNECTED]: 0, [ConnectionStatus.ATTENTION]: 0, [ConnectionStatus.AVAILABLE]: 0 };
  const origin = { [ALL]: 0 };
  for (const entry of found) {
    if (passes(entry, filters, "category")) {
      category[ALL] += 1;
      category[entry.category] = (category[entry.category] || 0) + 1;
    }
    if (passes(entry, filters, "status")) {
      status[ALL] += 1;
      status[entry.status] += 1;
      if (entry.status === ConnectionStatus.ATTENTION) status[ConnectionStatus.CONNECTED] += 1;
    }
    if (passes(entry, filters, "origin")) {
      origin[ALL] += 1;
      origin[entry.origin] = (origin[entry.origin] || 0) + 1;
    }
  }
  return { category, status, origin };
}

/**
 * The page, arranged, for the status tab chosen. Browsing (nothing typed,
 * no category, no publisher):
 *
 *   featured    the first sources worth connecting, while any is left and
 *               the tab can show one
 *   groups      the rest: one group when there are few, one bounded group
 *               per category when there are many (GROUP_ABOVE). Within each,
 *               what needs attention, then what is connected, then the rest.
 *
 * Anything typed or chosen: `results`, every match, best first.
 *
 * Each entry appears once: a featured source is not also in its category.
 *
 * @param featured ids to lift out while browsing, in their order
 */
export function arrangeCatalog(entries, filters = {}, { featured = [], labelOf = () => "" } = {}) {
  const counts = facetCounts(entries, filters, { labelOf });
  if (!isBrowsing(filters)) {
    return { mode: "results", results: filterCatalog(entries, filters, { labelOf }), counts, total: entries.length };
  }

  const shown = entries.filter((e) => matchesStatus(e, filters.status));
  const byId = new Map(shown.map((e) => [e.id, e]));
  const lifted = featured.map((id) => byId.get(id)).filter((e) => e && !isOn(e));
  const liftedIds = new Set(lifted.map((e) => e.id));
  const rest = shown.filter((e) => !liftedIds.has(e.id));

  const rank = (cat) => {
    const i = CATEGORY_ORDER.indexOf(cat);
    return i === -1 ? CATEGORY_ORDER.length : i;
  };
  let groups;
  if (rest.length <= GROUP_ABOVE) {
    const items = [...rest].sort((a, b) => byStatus(a, b) || rank(a.category) - rank(b.category) || byTitle(a, b));
    groups = items.length ? [{ category: ALL, items, more: 0 }] : [];
  } else {
    const buckets = new Map();
    for (const entry of rest) {
      const cat = CATEGORY_ORDER.includes(entry.category) ? entry.category : Category.OTHER;
      if (!buckets.has(cat)) buckets.set(cat, []);
      buckets.get(cat).push(entry);
    }
    groups = [...buckets.entries()]
      .sort(([a], [b]) => rank(a) - rank(b))
      .map(([category, items]) => {
        items.sort((a, b) => byStatus(a, b) || byTitle(a, b));
        return { category, items: items.slice(0, CATEGORY_PREVIEW), more: Math.max(0, items.length - CATEGORY_PREVIEW) };
      });
  }

  return { mode: "browse", featured: lifted, groups, counts, total: entries.length };
}

/**
 * Whether the status tabs are worth drawing: only when the account has both
 * something connected and something not. On the first day every tab would
 * say the same thing as All. Read from the whole catalogue, never the
 * search, so the tabs do not vanish while someone types.
 */
export function showStatusTabs(entries, status = ALL) {
  if (status && status !== ALL) return true;
  const on = entries.filter(isOn).length;
  return on > 0 && on < entries.length;
}
