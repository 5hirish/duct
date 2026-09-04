"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PlanViewport from "@/components/content/PlanViewport";
import { listPlans } from "@/lib/contentApi";
import { getActiveProjectId } from "@/lib/projects";

/**
 * Brand-new plan_month session.
 *
 * Clicking "Draft this post →" on a day card routes the user to
 * /content/posts/new?plan_id=<the latest plan>&day=<dayIndex> which
 * opens a draft_post workspace bound to that day.
 */
export default function NewPlanSessionPage() {
  const router = useRouter();
  const [projectId, setProjectId] = useState(null);
  const [latestPlanId, setLatestPlanId] = useState(null);

  useEffect(() => {
    const id = getActiveProjectId();
    if (!id) { router.replace("/content"); return; }
    setProjectId(id);
    // Resolve the latest plan id so onReviseDay can target it. We poll the
    // backend after PIPELINE_FINISHED is observed (handled in the workspace).
    listPlans(id).then((plans) => {
      if (Array.isArray(plans) && plans[0]?.id) setLatestPlanId(plans[0].id);
    }).catch(() => {});
  }, [router]);

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">Loading session…</p>
      </div>
    );
  }

  function reviseDay(index) {
    const params = new URLSearchParams();
    if (latestPlanId) params.set("plan_id", latestPlanId);
    if (index != null) params.set("day", String(index));
    router.push(`/content/posts/new?${params.toString()}`);
  }

  return (
    <div className="h-full">
      <ContentWorkspace
        mode="plan_month"
        context={{ projectId }}
        renderViewport={({ payload, steps, building }) => (
          <PlanSessionViewport
            payload={payload}
            steps={steps}
            building={building}
            onReviseDay={reviseDay}
            onPlanId={setLatestPlanId}
          />
        )}
      />
    </div>
  );
}

/** The plan viewport plus the one piece of state this page needs from it:
 * the id of the plan the agent produced, lifted in an effect rather than
 * during render (React warns, correctly, about setting a parent's state
 * while a child renders). */
function PlanSessionViewport({ payload, steps, building, onReviseDay, onPlanId }) {
  const planId = payload?.id;
  useEffect(() => {
    if (planId) onPlanId(planId);
  }, [planId, onPlanId]);
  return <PlanViewport payload={payload} steps={steps} building={building} onReviseDay={onReviseDay} />;
}
