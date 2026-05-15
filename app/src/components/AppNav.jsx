"use client";

import { usePathname } from "next/navigation";
import { useMemo } from "react";

const ROUTE_LABELS = [
  ["/insights/organic-growth/generate", "Generate Insight"],
  ["/insights/organic-growth",          "Organic Growth"],
  ["/audit/seo",                        "SEO Audit"],
  ["/connections",                      "Connections"],
  ["/generate",                         "Generate Insight"],
  ["/projects",                         "Projects"],
  ["/onboarding",                       "Onboarding"],
];

function routeLabel(pathname) {
  if (!pathname) return "";
  for (const [prefix, label] of ROUTE_LABELS) {
    if (pathname.startsWith(prefix)) return label;
  }
  return "";
}

export default function AppNav() {
  const pathname = usePathname();
  const label = useMemo(() => routeLabel(pathname), [pathname]);

  return (
    <span className="text-sm font-medium text-foreground truncate">
      {label}
    </span>
  );
}
