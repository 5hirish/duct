"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Legacy 30-day plan_month session route. Plan generation moved to the Content
 * Planner agent — redirect any stale bookmarks/links to /content/planner.
 */
export default function LegacyPlanSessionRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/content/planner");
  }, [router]);

  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-sm text-muted-foreground">Opening the Content Planner…</p>
    </div>
  );
}
