"use client";

import { usePathname, useRouter } from "next/navigation";
import { useMemo } from "react";
import { useAuditNav } from "../lib/auditNavContext";

const ROUTE_LABELS = [
  ["/insights/organic-growth/generate", "Generate Insight"],
  ["/insights/organic-growth",          "Organic Growth"],
  ["/audit/seo",                        "SEO Audit"],
  ["/connections",                      "Connections"],
  ["/generate",                         "Generate Insight"],
  ["/projects",                         "Projects"],
  ["/onboarding",                       "Onboarding"],
];

// Routes that show a back button, and where they go back to
const BACK_ROUTES = [
  ["/audit/seo/", "/audit/seo"],
];

function routeLabel(pathname) {
  if (!pathname) return "";
  for (const [prefix, label] of ROUTE_LABELS) {
    if (pathname.startsWith(prefix)) return label;
  }
  return "";
}

function backDest(pathname) {
  if (!pathname) return null;
  for (const [prefix, dest] of BACK_ROUTES) {
    if (pathname.startsWith(prefix)) return dest;
  }
  return null;
}

export default function AppNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuditRunning } = useAuditNav();

  const label = useMemo(() => routeLabel(pathname), [pathname]);
  const dest  = useMemo(() => backDest(pathname),   [pathname]);

  return (
    <div className="flex items-center gap-2 min-w-0">
      {dest && (
        <div className="relative group">
          <button
            onClick={() => !isAuditRunning && router.push(dest)}
            disabled={isAuditRunning}
            aria-label="Go back"
            className={`flex items-center justify-center rounded-md p-1 transition-colors ${
              isAuditRunning
                ? "cursor-not-allowed text-muted-foreground/40"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M6.85355 3.14645C7.04882 3.34171 7.04882 3.65829 6.85355 3.85355L3.70711 7H12.5C12.7761 7 13 7.22386 13 7.5C13 7.77614 12.7761 8 12.5 8H3.70711L6.85355 11.1464C7.04882 11.3417 7.04882 11.6583 6.85355 11.8536C6.65829 12.0488 6.34171 12.0488 6.14645 11.8536L2.14645 7.85355C1.95118 7.65829 1.95118 7.34171 2.14645 7.14645L6.14645 3.14645C6.34171 2.95118 6.65829 2.95118 6.85355 3.14645Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd" />
            </svg>
          </button>

          {/* Tooltip — only shown when disabled */}
          {isAuditRunning && (
            <div className="absolute left-1/2 top-full mt-2 -translate-x-1/2 z-50 pointer-events-none">
              <div className="whitespace-nowrap rounded-md bg-popover border border-border px-2.5 py-1.5 text-xs text-popover-foreground shadow-md">
                Audit in progress — wait for it to finish
                <div className="absolute -top-1 left-1/2 -translate-x-1/2 size-2 rotate-45 border-l border-t border-border bg-popover" />
              </div>
            </div>
          )}
        </div>
      )}

      <span className="text-sm font-medium text-foreground truncate">{label}</span>
    </div>
  );
}
