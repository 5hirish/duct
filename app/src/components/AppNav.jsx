"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo } from "react";
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
import { titleCase } from "@/lib/format";

// Friendly labels for known path segments. Unknown segments (dynamic ids /
// slugs) fall back to prettifySegment(). Descriptors, resolved in buildTrail
// with the request's i18n, because a module-level `t` is fixed at first load.
const SEGMENT_LABELS = {
  content: msg`Content Studio`,
  plan: msg`Plan`,
  posts: msg`Posts`,
  sessions: msg`Sessions`,
  insights: msg`Insights`,
  "organic-growth": msg`Organic Growth`,
  generate: msg`Generate Insight`,
  session: msg`Session`,
  audit: msg`Audit`,
  seo: msg`SEO Audit`,
  connections: msg`Connections`,
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

function buildTrail(pathname, i18n) {
  if (!pathname) return [];
  const segments = pathname.split("/").filter(Boolean);
  return segments.map((segment, i) => ({
    label: SEGMENT_LABELS[segment] ? i18n._(SEGMENT_LABELS[segment]) : prettifySegment(segment),
    href: "/" + segments.slice(0, i + 1).join("/"),
    isLast: i === segments.length - 1,
  }));
}

export default function AppNav() {
  const pathname = usePathname();
  const { i18n } = useLingui();
  const { isAuditRunning } = useAuditNav();

  const trail = useMemo(() => buildTrail(pathname, i18n), [pathname, i18n]);

  if (trail.length === 0) return null;

  return (
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
  );
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
