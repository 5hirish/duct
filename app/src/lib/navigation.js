import { msg } from "@lingui/core/macro";
import { CalendarClock, FileText, History, House, PenLine, Plug, Search, ShieldCheck } from "lucide-react";

/**
 * Where you can go in the app — the single source of truth.
 *
 * The sidebar renders it, and the command palette turns every available item
 * into a "Go to …" command. It lives here rather than inside AppSidebar
 * because two surfaces now answer the same question, and a nav item that
 * exists in one but not the other is the kind of drift nobody notices until a
 * page becomes unreachable from search.
 *
 * `available: false` items are skipped by both. The sidebar used to show them
 * dimmed with a "Soon" pill, which put two dead entries in the primary nav;
 * a feature that does not exist yet is not a place you can go.
 *
 * `label` on a section and on an item is a Lingui descriptor, not a string:
 * render it with `i18n._(item.label)` from `useLingui()`. A `t` here would be
 * evaluated once at module load, in whichever language the first request had.
 */
export const NAV_SECTIONS = [
  {
    // Named for what you do, not for the modules behind it. Until 2026-11-02
    // the sidebar was the org chart: Growth / Product / Execute / Library,
    // two "Soon" items holding a section to themselves, and Connections, the
    // one thing a new user must do, parked in the footer beside "Light mode".
    key: "work",
    label: msg`Work`,
    items: [
      {
        key: "home",
        label: msg`Home`,
        icon: House,
        href: "/insights/organic-growth",
        available: true,
        // Conversations live under /insights too, and a run working there
        // pulses this entry.
        matchPrefix: "/insights",
      },
      {
        key: "seo_audit",
        label: msg`SEO Audit`,
        icon: Search,
        href: "/audit/seo",
        available: true,
        matchPrefix: "/audit/seo",
      },
      {
        key: "tiktok_studio",
        label: msg`Content Studio`,
        icon: PenLine,
        href: "/content",
        available: true,
        matchPrefix: "/content",
      },
      {
        key: "changes",
        label: msg`Changes`,
        icon: ShieldCheck,
        href: "/execute",
        available: true,
        matchPrefix: "/execute",
      },
      {
        // Runs nobody starts by hand (#562): what fires when, and what each left.
        key: "scheduled",
        label: msg`Scheduled`,
        icon: CalendarClock,
        href: "/scheduled",
        available: true,
        matchPrefix: "/scheduled",
      },
      {
        key: "connections",
        label: msg`Toolbox`,
        icon: Plug,
        href: "/connections",
        available: true,
        matchPrefix: "/connections",
        // The sidebar shows how many sources are live beside this one.
        badge: "connections",
      },
    ],
  },
  {
    key: "library",
    label: msg`Library`,
    items: [
      {
        key: "artifacts",
        label: msg`Documents`,
        icon: FileText,
        href: "/artifacts",
        available: true,
        matchPrefix: "/artifacts",
      },
      {
        key: "activity",
        label: msg`Activity`,
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
