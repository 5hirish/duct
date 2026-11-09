"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Trans } from "@lingui/react/macro";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PlanViewport from "@/components/content/PlanViewport";
import { getPlan, listPlans } from "@/lib/contentApi";
import { parseDate, planCovering } from "@/lib/contentSchedule";
import { getActiveProjectId } from "@/lib/projects";
import { useLeaveOnProjectSwitch } from "@/hooks/useActiveProjectId";

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
 * The pane is for reading the plan being made: a day has no "Draft post"
 * action here, because that route leaves the planning session for a drafting
 * one mid-plan (and, since proposals, before there is a plan to draft from).
 * Drafting from a day lives on the plan board (components/content/PlanBoard).
 */
export default function NewPlanSessionPage() {
  const router = useRouter();
  const [setup, setSetup] = useState(null); // { projectId, plan, start, days }
  // The plan is written into the project the page opened on.
  useLeaveOnProjectSwitch();

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

  return (
    <div className="h-full">
      <ContentWorkspace
        mode="plan_month"
        context={context}
        renderViewport={({ payload, steps, building, onSendMessage, sessionId }) => (
          <PlanViewport
            payload={payload || (plan ? { type: "plan", ...plan } : null)}
            steps={steps}
            building={building}
            onSendMessage={onSendMessage}
            sessionId={sessionId}
          />
        )}
      />
    </div>
  );
}
