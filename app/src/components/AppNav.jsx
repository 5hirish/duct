"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useSyncExternalStore } from "react";
import { ChevronLeft } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { useAuditNav } from "../lib/auditNavContext";
import { pageTitleServerSnapshot, pageTitleSnapshot, subscribePageTitle } from "@/lib/pageTitle";
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
const HIDDEN_SEGMENTS = new Set(["organic-growth", "audit"]);
const SEGMENT_HREFS = { "/insights": "/insights/organic-growth" };

function buildTrail(pathname, i18n) {
  if (!pathname) return [];
  const segments = pathname.split("/").filter(Boolean);
  const crumbs = segments
    .map((segment, i) => {
      const path = "/" + segments.slice(0, i + 1).join("/");
      return {
        segment,
        label: SEGMENT_LABELS[segment] ? i18n._(SEGMENT_LABELS[segment]) : prettifySegment(segment),
        href: SEGMENT_HREFS[path] || path,
      };
    })
    .filter((crumb) => !HIDDEN_SEGMENTS.has(crumb.segment));
  return crumbs.map((crumb, i) => ({ ...crumb, isLast: i === crumbs.length - 1 }));
}

/**
 * The top bar's place-name.
 *
 * On a framed screen (one with a PageHeader) the page already says its name in
 * its own title, and the sidebar already says which section you are in, so the
 * bar says neither while that title is on screen: it holds only the way back
 * to a parent, when there is one, and takes the title over once it scrolls
 * under the bar. That is the large-title pattern from Apple's platforms, and
 * it ended every screen opening on its name twice (2026-11-03).
 *
 * A full-bleed workspace (a conversation, a running audit) has no page title,
 * so the bar is its only one and keeps the trail built from the path.
 */
export default function AppNav({ framed = false }) {
  const pathname = usePathname();
  const { i18n } = useLingui();
  const { isAuditRunning } = useAuditNav();
  const page = useSyncExternalStore(subscribePageTitle, pageTitleSnapshot, pageTitleServerSnapshot);

  const trail = useMemo(() => buildTrail(pathname, i18n), [pathname, i18n]);

  if (framed) return <FramedTrail page={page} />;
  if (trail.length === 0) return null;

  return (
    <>
      <Divider />
      <Breadcrumb className="min-w-0">
        <BreadcrumbList>
          {trail.map((crumb) => (
            <BreadcrumbSegment
              key={crumb.href}
              crumb={crumb}
              disabled={isAuditRunning}
            />
          ))}
        </BreadcrumbList>
      </Breadcrumb>
    </>
  );
}

function Divider() {
  return <div className="h-4 w-px shrink-0 bg-border" aria-hidden />;
}

function BreadcrumbSegment({ crumb, disabled }) {
  // The current page, or any ancestor while an audit is running, is not a link.
  const asPage = crumb.isLast || disabled;
  return (
    <>
      <BreadcrumbItem className="min-w-0">
        {asPage ? (
          <BreadcrumbPage className="truncate">{crumb.label}</BreadcrumbPage>
        ) : (
          <BreadcrumbLink asChild className="truncate">
            <Link href={crumb.href}>{crumb.label}</Link>
          </BreadcrumbLink>
        )}
      </BreadcrumbItem>
      {!crumb.isLast && <BreadcrumbSeparator />}
    </>
  );
}

/** The parent as the way back, and the title only once it has scrolled away. */
function FramedTrail({ page }) {
  const showTitle = page.present && !page.visible && Boolean(page.title);
  if (!page.back && !showTitle) return null;
  return (
    <>
      <Divider />
      <Breadcrumb className="min-w-0">
        <BreadcrumbList>
          {page.back && (
            <>
              <BreadcrumbItem className="min-w-0">
                <BreadcrumbLink asChild className="inline-flex min-w-0 items-center gap-1">
                  <Link href={page.back.href}>
                    {!showTitle && <ChevronLeft className="size-4 shrink-0" aria-hidden />}
                    <span className="truncate">{page.back.label}</span>
                  </Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              {showTitle && <BreadcrumbSeparator />}
            </>
          )}
          {showTitle && (
            <BreadcrumbItem className="min-w-0">
              <BreadcrumbPage className="truncate">{page.title}</BreadcrumbPage>
            </BreadcrumbItem>
          )}
        </BreadcrumbList>
      </Breadcrumb>
    </>
  );
}
