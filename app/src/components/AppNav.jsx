"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo } from "react";
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
// slugs) fall back to prettifySegment().
const SEGMENT_LABELS = {
  content: "Content Studio",
  plan: "Plan",
  posts: "Posts",
  sessions: "Sessions",
  insights: "Insights",
  "organic-growth": "Organic Growth",
  generate: "Generate Insight",
  audit: "Audit",
  seo: "SEO Audit",
  connections: "Connections",
  projects: "Projects",
  project: "Project",
  onboarding: "Onboarding",
  new: "New",
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

function buildTrail(pathname) {
  if (!pathname) return [];
  const segments = pathname.split("/").filter(Boolean);
  return segments.map((segment, i) => ({
    label: SEGMENT_LABELS[segment] || prettifySegment(segment),
    href: "/" + segments.slice(0, i + 1).join("/"),
    isLast: i === segments.length - 1,
  }));
}

export default function AppNav() {
  const pathname = usePathname();
  const { isAuditRunning } = useAuditNav();

  const trail = useMemo(() => buildTrail(pathname), [pathname]);

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
