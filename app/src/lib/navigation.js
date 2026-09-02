import {
  TrendingUp,
  BarChart3,
  Megaphone,
  Search,
  PenLine,
  ShieldCheck,
  FileText,
  History,
} from "lucide-react";

/**
 * Where you can go in the app — the single source of truth.
 *
 * The sidebar renders it, and the command palette turns every available item
 * into a "Go to …" command. It lives here rather than inside AppSidebar
 * because two surfaces now answer the same question, and a nav item that
 * exists in one but not the other is the kind of drift nobody notices until a
 * page becomes unreachable from search.
 *
 * `available: false` items are shown by the sidebar as coming-soon and are
 * skipped by the palette — there is nowhere to send you.
 */
export const NAV_SECTIONS = [
  {
    key: "growth",
    label: "Growth",
    items: [
      {
        key: "organic_growth",
        label: "Organic Growth",
        icon: TrendingUp,
        href: "/insights/organic-growth",
        available: true,
        matchPrefix: "/insights/organic-growth",
      },
      {
        key: "seo_audit",
        label: "SEO Audit",
        icon: Search,
        href: "/audit/seo",
        available: true,
        matchPrefix: "/audit/seo",
      },
      {
        key: "tiktok_studio",
        label: "Content Studio",
        icon: PenLine,
        href: "/content",
        available: true,
        matchPrefix: "/content",
      },
      {
        key: "paid_ads",
        label: "Paid Ads Intelligence",
        icon: Megaphone,
        href: null,
        available: false,
      },
    ],
  },
  {
    key: "product",
    label: "Product",
    items: [
      {
        key: "product_intelligence",
        label: "Product Intelligence",
        icon: BarChart3,
        href: null,
        available: false,
      },
    ],
  },
  {
    key: "execute",
    label: "Execute",
    items: [
      {
        key: "executions",
        label: "Executions",
        icon: ShieldCheck,
        href: "/execute",
        available: true,
        matchPrefix: "/execute",
      },
    ],
  },
  {
    key: "library",
    label: "Library",
    items: [
      {
        key: "artifacts",
        label: "Artifacts",
        icon: FileText,
        href: "/artifacts",
        available: true,
        matchPrefix: "/artifacts",
      },
      {
        key: "activity",
        label: "Activity",
        icon: History,
        href: "/activity",
        available: true,
        matchPrefix: "/activity",
      },
    ],
  },
];

/** Flat list of the reachable destinations, for search-style surfaces. */
export function navigableItems() {
  return NAV_SECTIONS.flatMap((section) =>
    section.items
      .filter((item) => item.available && item.href)
      .map((item) => ({ ...item, sectionLabel: section.label }))
  );
}
