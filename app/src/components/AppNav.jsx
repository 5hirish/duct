"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useSyncExternalStore } from "react";
import { ChevronLeft } from "lucide-react";
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
import { buildTrail } from "@/lib/breadcrumbs";


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

  const named = framed ? "" : page.title;
  const trail = useMemo(() => buildTrail(pathname, i18n, typeof named === "string" ? named : ""), [pathname, i18n, named]);

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
