import { describe, expect, it } from "vitest";
import {
  ALL,
  CATEGORY_PREVIEW,
  Category,
  ConnectionStatus,
  GROUP_ABOVE,
  Origin,
  arrangeCatalog,
  facetCounts,
  filterCatalog,
  isBrowsing,
  normalize,
  showStatusTabs,
} from "../connectorCatalog";
import { STARTERS, catalogScenario, randomCatalog } from "../__fixtures__/connectorCatalogs.mjs";

const LABELS = { advertising: "Advertising", search: "Search & SEO", product: "Product" };
const labelOf = (cat) => LABELS[cat] || "";

describe("search", () => {
  const today = catalogScenario("today");

  it("puts a title that starts with the query first", () => {
    const hits = filterCatalog(today, { query: "goo" }, { labelOf });
    expect(hits[0].title.startsWith("Google")).toBe(true);
    expect(hits.every((e) => /google/i.test(e.title))).toBe(true);
  });

  it("finds by the category's name, so 'advertising' lists the ads", () => {
    const hits = filterCatalog(today, { query: "advertising" }, { labelOf });
    expect(hits.map((e) => e.id).sort()).toEqual(["apple_ads", "google_ads", "meta_ads", "openai_ads"]);
  });

  it("needs every word, wherever each is", () => {
    expect(filterCatalog(today, { query: "stripe refunds" })).toHaveLength(1);
    expect(filterCatalog(today, { query: "stripe zebra" })).toHaveLength(0);
  });

  it("ignores case and accents", () => {
    expect(normalize("Analítica  ")).toBe("analitica");
    const foreign = catalogScenario("long-and-foreign");
    expect(filterCatalog(foreign, { query: "suchanfragen" }).map((e) => e.id)).toEqual(["gsc"]);
  });
});

describe("filters", () => {
  const today = catalogScenario("today");

  it("Connected takes the ones needing attention too", () => {
    const entries = [...today, { ...today[0], id: "x", status: ConnectionStatus.ATTENTION }];
    const hits = filterCatalog(entries, { status: ConnectionStatus.CONNECTED });
    expect(hits.map((e) => e.id).sort()).toEqual(["ga4", "gsc", "x"]);
  });

  it("counts each facet with the others applied but not its own", () => {
    const counts = facetCounts(today, { category: Category.ADVERTISING, origin: Origin.DUCT });
    // The category counts ignore the category chosen, so every chip says what it would give.
    expect(counts.category[Category.SEARCH]).toBe(1);
    expect(counts.category[ALL]).toBe(13);
    // The origin counts keep the category: four ads, all Duct's.
    expect(counts.origin[Origin.DUCT]).toBe(4);
    expect(counts.origin[Origin.VENDOR] || 0).toBe(0);
  });

  it("browses when nothing is typed or chosen; a status tab still browses", () => {
    expect(isBrowsing({})).toBe(true);
    expect(isBrowsing({ query: "  " })).toBe(true);
    expect(isBrowsing({ query: "a" })).toBe(false);
    expect(isBrowsing({ category: Category.REVENUE })).toBe(false);
    expect(isBrowsing({ status: ConnectionStatus.AVAILABLE })).toBe(true);
  });
});

describe("arrangement", () => {
  it("today is one grid, connected first, with the starters lifted out of it", () => {
    const out = arrangeCatalog(catalogScenario("today"), {}, { featured: STARTERS });
    expect(out.mode).toBe("browse");
    expect(out.featured.map((e) => e.id)).toEqual(["google_ads", "stripe"]);
    expect(out.groups).toHaveLength(1);
    expect(out.groups[0].items.slice(0, 2).map((e) => e.id)).toEqual(["gsc", "ga4"]);
    expect(out.groups[0].items.some((e) => e.id === "stripe")).toBe(false);
  });

  it("the Connected tab holds only what is connected, attention first, and no starters", () => {
    const entries = catalogScenario("hundreds");
    const out = arrangeCatalog(entries, { status: ConnectionStatus.CONNECTED }, { featured: STARTERS });
    const items = out.groups.flatMap((g) => g.items);
    expect(out.featured).toHaveLength(0);
    expect(items.every((e) => e.status !== ConnectionStatus.AVAILABLE)).toBe(true);
    expect(items[0].status).toBe(ConnectionStatus.ATTENTION);
  });

  it("draws the tabs only once there is both something connected and something not", () => {
    expect(showStatusTabs(catalogScenario("first-day"))).toBe(false);
    expect(showStatusTabs(catalogScenario("today"))).toBe(true);
    const all = catalogScenario("today").map((e) => ({ ...e, status: ConnectionStatus.CONNECTED }));
    expect(showStatusTabs(all)).toBe(false);
    // A tab someone is standing on never disappears under them.
    expect(showStatusTabs(catalogScenario("first-day"), ConnectionStatus.CONNECTED)).toBe(true);
  });

  it("two hundred become bounded sections, one per category, in order", () => {
    const out = arrangeCatalog(catalogScenario("hundreds"), {}, { featured: STARTERS });
    expect(out.groups.length).toBeGreaterThan(1);
    for (const g of out.groups) expect(g.items.length).toBeLessThanOrEqual(CATEGORY_PREVIEW);
    expect(out.groups.some((g) => g.more > 0)).toBe(true);
  });

  it("over any catalogue, shows every entry exactly once", () => {
    for (let seed = 1; seed <= 300; seed += 1) {
      const entries = randomCatalog(seed);
      for (const status of [ALL, ConnectionStatus.CONNECTED, ConnectionStatus.AVAILABLE]) {
        const out = arrangeCatalog(entries, { status }, { featured: STARTERS });
        const inTab = filterCatalog(entries, { status });
        const shown = [...out.featured, ...out.groups.flatMap((g) => g.items)].map((e) => e.id);
        const hidden = out.groups.reduce((n, g) => n + g.more, 0);
        expect(new Set(shown).size).toBe(shown.length);
        expect(shown.length + hidden).toBe(inTab.length);
        const browsable = inTab.length - out.featured.length;
        expect(out.groups.length > 1).toBe(browsable > GROUP_ABOVE);
        for (const g of out.groups) expect(g.items.length).toBeLessThanOrEqual(browsable > GROUP_ABOVE ? CATEGORY_PREVIEW : GROUP_ABOVE);
      }
    }
  });

  it("over any catalogue, the counts agree with what each choice would show", () => {
    for (let seed = 1; seed <= 100; seed += 1) {
      const entries = randomCatalog(seed);
      const counts = facetCounts(entries, {});
      for (const [cat, n] of Object.entries(counts.category)) {
        if (cat === ALL) continue;
        expect(filterCatalog(entries, { category: cat })).toHaveLength(n);
      }
      for (const status of Object.values(ConnectionStatus)) {
        expect(filterCatalog(entries, { status })).toHaveLength(counts.status[status]);
      }
    }
  });
});
