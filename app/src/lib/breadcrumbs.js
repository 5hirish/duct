/**
 * The top bar's trail on a full-bleed workspace: one crumb per path segment,
 * in the sidebar's words, each a link that goes somewhere. Pure, so the route
 * tree can be checked against it (lib/__tests__/breadcrumbs.test.js).
 */
import { msg } from "@lingui/core/macro";
import { titleCase } from "@/lib/format";

// Friendly labels for known path segments. Unknown segments (dynamic ids /
// slugs) fall back to prettifySegment(). Descriptors, resolved in buildTrail
// with the request's i18n, because a module-level `t` is fixed at first load.
const SEGMENT_LABELS = {
  content: msg`Content Studio`,
  plan: msg`Plan`,
  posts: msg`Posts`,
  sessions: msg`Sessions`,
  insights: msg`Home`,
  generate: msg`Generate Insight`,
  session: msg`Conversation`,
  seo: msg`SEO Audit`,
  execute: msg`Changes`,
  artifacts: msg`Documents`,
  connections: msg`Toolbox`,
  projects: msg`Projects`,
  project: msg`Project`,
  start: msg`Get started`,
  new: msg`New`,
  // The page is the only thing under /settings, and it owns both questions —
  // which model, and whose key. Title-casing the segment gave a breadcrumb
  // reading "Models" under a heading and a menu item that both say more.
  models: msg`Models & providers`,
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function prettifySegment(segment) {
  const decoded = (() => {
    try {
      return decodeURIComponent(segment);
    } catch {
      return segment;
    }
  })();
  // UUIDs / long opaque ids / pure numbers → short #id
  if (UUID_RE.test(decoded) || /^\d+$/.test(decoded) || decoded.length > 18) {
    return `#${decoded.slice(0, 6)}`;
  }
  // slug → Title Case
  return titleCase(decoded);
}

// Segments that are a route's plumbing, not a place: /insights is Home, and
// /insights/organic-growth is the same Home; /audit has no page of its own.
// The trail skips them, so the breadcrumb names where you are in the words
// the sidebar uses.
export const HIDDEN_SEGMENTS = new Set(["organic-growth", "audit"]);

// A folder with no page of its own still gets a crumb, and a crumb is a link,
// so it goes where the sidebar takes you for the same thing. Linked as itself
// it is a 404: "Posts" above a post was one until 2026-11-09, and so was
// "Sessions" above a plan session. lib/__tests__/breadcrumbs.test.js fails a folder
// without a page that is in neither list.
export const SEGMENT_HREFS = {
  "/insights": "/insights/organic-growth",
  "/content/posts": "/content?tab=posts",
  "/content/sessions": "/content?tab=plans",
  "/project": "/projects",
  "/settings": "/settings/profile",
};

// A crumb whose folder means something else to the person: a plan session is
// one of the plans, the way a post page is one of the posts.
const PATH_LABELS = { "/content/sessions": msg`Plans` };

/**
 * `lastLabel` is what the open workspace calls itself (lib/pageTitle.js
 * useTrailTitle): a post's hook rather than "#a9997d", a plan's name rather
 * than "New" when the session is revising one.
 */
export function buildTrail(pathname, i18n, lastLabel = "") {
  if (!pathname) return [];
  const segments = pathname.split("/").filter(Boolean);
  const crumbs = segments
    .map((segment, i) => {
      const path = "/" + segments.slice(0, i + 1).join("/");
      return {
        segment,
        label: PATH_LABELS[path]
          ? i18n._(PATH_LABELS[path])
          : SEGMENT_LABELS[segment]
            ? i18n._(SEGMENT_LABELS[segment])
            : prettifySegment(segment),
        href: SEGMENT_HREFS[path] || path,
      };
    })
    .filter((crumb) => !HIDDEN_SEGMENTS.has(crumb.segment));
  return crumbs.map((crumb, i) => {
    const isLast = i === crumbs.length - 1;
    return { ...crumb, label: isLast && lastLabel ? lastLabel : crumb.label, isLast };
  });
}
