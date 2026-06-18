"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PlannerTimeline from "@/components/content/PlannerTimeline";
import { listPlans } from "@/lib/contentApi";
import { getActiveProjectId } from "@/lib/projects";

/**
 * Content Planner session (mode=update_plan).
 *
 * Opens the strategist agent that owns the project's canonical rolling 7-day
 * plan. Left = chat, right = 7-day timeline. "Draft this post →" on a slot
 * routes to /content/posts/new?plan_id=<active>&day=<index> (the existing
 * draft_post flow).
 */
export default function ContentPlannerPage() {
  const router = useRouter();
  const [projectId, setProjectId] = useState(null);
  const [activePlanId, setActivePlanId] = useState(null);

  useEffect(() => {
    const id = getActiveProjectId();
    if (!id) { router.replace("/content"); return; }
    setProjectId(id);
    // Resolve the active plan id so "Draft this post →" can target it before the
    // first PLAN_GENERATED arrives (e.g. when refreshing an existing plan).
    listPlans(id).then((plans) => {
      if (!Array.isArray(plans)) return;
      const active = plans.find((p) => p.status === "active") || plans[0];
      if (active?.id) setActivePlanId(active.id);
    }).catch(() => {});
  }, [router]);

  if (!projectId) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading planner…</p>
      </div>
    );
  }

  // planId comes from the live plan payload (preferred) or the resolved active
  // plan id. Passed up from the timeline so we never setState during render.
  function reviseDay(index, planId) {
    const pid = planId || activePlanId;
    const params = new URLSearchParams();
    if (pid) params.set("plan_id", pid);
    if (index != null) params.set("day", String(index));
    router.push(`/content/posts/new?${params.toString()}`);
  }

  return (
    <div className="h-full">
      <ContentWorkspace
        mode="update_plan"
        context={{ projectId }}
        renderViewport={({ payload, steps, building, onSendMessage }) => (
          <PlannerTimeline
            payload={payload}
            steps={steps}
            building={building}
            projectId={projectId}
            onReviseDay={reviseDay}
            onRefreshPosts={() => onSendMessage?.("/refresh-posts")}
            onSendMessage={onSendMessage}
          />
        )}
      />
    </div>
  );
}
