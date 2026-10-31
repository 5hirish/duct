"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Trans } from "@lingui/react/macro";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PlanViewport from "@/components/content/PlanViewport";
import { getPlan, listPlans } from "@/lib/contentApi";
import { parseDate, planCovering } from "@/lib/contentSchedule";
import { getActiveProjectId } from "@/lib/projects";

/**
 * The plan manager: a plan_month session over one period's plan.
 *
 *   ?plan=<id>              — revise that plan. Its conversation is reopened
 *                             when it has one, and the pane shows the plan
 *                             straight away.
 *   ?start=<day>&days=<n>   — plan that period (the Plan tab's "New plan" and
 *                             "Plan ahead", once someone picked how far).
 *   neither                 — the plan covering today, or a new one for the
 *                             month in progress when none does.
 *
 * Which plan a session manages is resolved here before the session opens,
 * the same way the backend resolves it (runner._resolve_plan_period), so the
 * pane always shows the plan the agent is changing.
 *
 * Clicking "Draft this post →" on a day routes to
 * /content/posts/new?plan_id=<the plan>&day=<dayIndex>.
 */
export default function NewPlanSessionPage() {
  const router = useRouter();
  const [setup, setSetup] = useState(null); // { projectId, plan, start, days }
  const [planId, setPlanId] = useState(null);

  useEffect(() => {
    const projectId = getActiveProjectId();
    if (!projectId) { router.replace("/content"); return; }
    const params = new URLSearchParams(window.location.search);
    const wanted = params.get("plan");
    const start = params.get("start");
    const days = Number(params.get("days")) || null;
    let cancelled = false;
    (async () => {
      const plans = await listPlans(projectId).catch(() => []);
      const from = (start && parseDate(`${start}T00:00:00`)) || new Date();
      const meta = (wanted && plans.find((p) => p.id === wanted)) || planCovering(plans, from);
      // The full plan carries its conversation id; the listing does not.
      const plan = meta ? await getPlan(meta.id).catch(() => meta) : null;
      if (cancelled) return;
      setSetup({ projectId, plan, start: plan ? null : start, days: plan ? null : days });
      if (plan) setPlanId(plan.id);
    })();
    return () => { cancelled = true; };
  }, [router]);

  if (!setup) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground"><Trans>Loading session…</Trans></p>
      </div>
    );
  }

  const { projectId, plan, start, days } = setup;
  const context = plan
    ? {
        projectId,
        planId: plan.id,
        artifactType: "plan",
        artifactId: plan.id,
        ...(plan.active_conversation_id
          ? { conversationId: plan.active_conversation_id, resume: true }
          : {}),
      }
    : { projectId, ...(start ? { startDate: start } : {}), ...(days ? { days } : {}) };

  function reviseDay(index) {
    const params = new URLSearchParams();
    if (planId) params.set("plan_id", planId);
    if (index != null) params.set("day", String(index));
    router.push(`/content/posts/new?${params.toString()}`);
  }

  return (
    <div className="h-full">
      <ContentWorkspace
        mode="plan_month"
        context={context}
        renderViewport={({ payload, steps, building }) => (
          <PlanSessionViewport
            payload={payload || (plan ? { type: "plan", ...plan } : null)}
            steps={steps}
            building={building}
            onReviseDay={reviseDay}
            onPlanId={setPlanId}
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
