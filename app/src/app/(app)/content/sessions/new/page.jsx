"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Trans, useLingui } from "@lingui/react/macro";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PlanViewport from "@/components/content/PlanViewport";
import PlanQuickActions from "@/components/content/PlanQuickActions";
import { getPlan, listPlans } from "@/lib/contentApi";
import { parseDate, planCovering } from "@/lib/contentSchedule";
import { PlanStatus } from "@/lib/contentEnums";
import { getActiveProjectId } from "@/lib/projects";
import { useLeaveOnProjectSwitch } from "@/hooks/useActiveProjectId";
import { AnalyticsEvent, trackEvent } from "@/lib/analytics";
import { feedFromParams, feedSessionHref } from "@/lib/contentFeed";
import { useTrailTitle } from "@/lib/pageTitle";
import { planDisplayName } from "@/lib/planStrategy";

/**
 * The plan manager: a plan_month session over one period's plan.
 *
 *   ?plan=<id>              — revise that plan. Its conversation is reopened
 *                             when it has one, and the pane shows the plan
 *                             straight away.
 *   ?start=<day>&days=<n>   — plan that period (the Plans tab's "New plan" and
 *                             "Plan ahead", once someone picked how far).
 *   neither                 — the plan covering today, or a new one for the
 *                             month in progress when none does.
 *   ?source=work&…          — a plan from shipped work (#561) over that period,
 *                             with the setup sheet's answers (lib/contentFeed.js).
 *                             Always a new run: it never resumes the covering
 *                             plan's conversation, which was about goals.
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
  const { t } = useLingui();
  // The trail says which plan: its name while revising one, "New" otherwise.
  const shortId = setup?.plan?.id?.slice(0, 8) || "";
  useTrailTitle(setup?.plan ? planDisplayName(setup.plan.name) || t`Plan ${shortId}` : "");

  useEffect(() => {
    const projectId = getActiveProjectId();
    if (!projectId) { router.replace("/content"); return; }
    const params = new URLSearchParams(window.location.search);
    const wanted = params.get("plan");
    const start = params.get("start");
    const days = Number(params.get("days")) || null;
    const feed = feedFromParams(params);
    let cancelled = false;
    (async () => {
      const plans = await listPlans(projectId).catch(() => []);
      const from = (start && parseDate(`${start}T00:00:00`)) || new Date();
      const meta = (wanted && plans.find((p) => p.id === wanted)) || planCovering(plans, from);
      // The full plan carries its conversation id; the listing does not.
      const plan = meta ? await getPlan(meta.id).catch(() => meta) : null;
      if (cancelled) return;
      if (feed) {
        // The pane shows the plan the feed will change; the run itself is
        // fresh, over the period the sheet picked.
        setSetup({ projectId, plan, start, days, feed });
        trackEvent(AnalyticsEvent.ContentPlanStarted, { source: "work" });
        return;
      }
      setSetup({ projectId, plan, start: plan ? null : start, days: plan ? null : days });
      if (!plan?.active_conversation_id) trackEvent(AnalyticsEvent.ContentPlanStarted, { source: "goals" });
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

  const { projectId, plan, start, days, feed } = setup;
  const context = feed
    ? { projectId, ...(start ? { startDate: start } : {}), ...(days ? { days } : {}), feed }
    : plan
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
        renderViewport={({ payload, steps, building, onSendMessage, sessionId, feed: read }) => (
          <PlanViewport
            // A plan from shipped work shows its read first: the plan it may
            // change appears with the proposal, not before the stories.
            payload={payload || (plan && !feed ? { type: "plan", ...plan } : null)}
            steps={steps}
            building={building}
            onSendMessage={onSendMessage}
            sessionId={sessionId}
            feed={read}
            // Full navigations: this page resolves its setup once, on mount,
            // so a push to the same route would keep the feed run on screen.
            onLookFurther={feed ? () => { window.location.assign(feedSessionHref({ ...feed, lookBack: 30 })); } : undefined}
            onPlanFromGoals={feed ? () => { window.location.assign("/content/sessions/new"); } : undefined}
          />
        )}
        renderFooter={({ payload, idle, onSendMessage }) => (
          // A proposal waiting on Accept, Modify or Reject is the next step on
          // its own; a rejected one leaves the plan the page opened on.
          <PlanQuickActions
            plan={payload && payload.status !== PlanStatus.REJECTED ? payload : plan}
            hidden={!idle || payload?.status === PlanStatus.PROPOSED}
            onSend={onSendMessage}
          />
        )}
      />
    </div>
  );
}
