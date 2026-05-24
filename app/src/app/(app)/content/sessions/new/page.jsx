"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PlanViewport from "@/components/content/PlanViewport";
import { getActiveProjectId } from "@/lib/projects";

/**
 * Brand-new plan_month session.
 * Triggers an SSE stream on mount. The session id is held in the workspace's
 * sessionIdRef; we don't persist it cross-route in MVP.
 */
export default function NewPlanSessionPage() {
  const router = useRouter();

  useEffect(() => {
    if (!getActiveProjectId()) router.replace("/content");
  }, [router]);

  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">Loading session…</p>
      </div>
    );
  }

  return (
    <div className="h-full">
      <ContentWorkspace
        mode="plan_month"
        context={{ projectId }}
        renderViewport={({ payload }) => (
          <PlanViewport
            payload={payload}
            onReviseDay={(dayIndex) => {
              // For MVP: jump back to the landing and let the user start a
              // draft_post session from the day card. A direct "draft from
              // Day N" flow comes in Phase 6.
              router.push(`/content?day=${dayIndex}`);
            }}
          />
        )}
      />
    </div>
  );
}
