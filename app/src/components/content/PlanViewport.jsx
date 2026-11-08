"use client";

import { useEffect, useId, useState } from "react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import PlanList from "./PlanList";
import PlanStrategy from "./PlanStrategy";
import PipelineProgress from "../PipelineProgress";
import { acceptPlan, rejectPlan } from "../../lib/contentApi";
import { PlanStatus } from "../../lib/contentEnums";
import { ContentStep } from "../../lib/contentEvents";
import { planEndOf, planStartOf } from "../../lib/contentSchedule";
import { formatDateRange } from "../../lib/format";

// Loading ladder mirrors the audit report: the two fixed backend steps
// (LOAD_PROJECT, ENRICHING) plus a virtual synthesis stage the backend doesn't
// emit a step for (the long SDK turn that produces the plan). Labels are
// message descriptors (module-level), resolved with `i18n._` in the component.
const PLAN_STAGES = [
  { id: ContentStep.LOAD_PROJECT,    label: msg`Loading your brand & pillars` },
  { id: ContentStep.ENRICHING,       label: msg`Researching trends & history` },
  { id: ContentStep.SYNTHESIZE_PLAN, label: msg`Synthesizing your plan`, virtual: true },
];

const PLAN_LINES = [
  msg`Reviewing your content pillars…`,
  msg`Studying what's worked before…`,
  msg`Scanning trending sounds & hooks…`,
  msg`Mapping topics across your dates…`,
  msg`Balancing pillars and formats…`,
  msg`Casting your narrator…`,
  msg`Sequencing the posting cadence…`,
];

// What the chat is told after a decision, so the agent carries on in the
// right direction. Prompts to the model, not interface copy: the same
// register as PostViewport's review request, and English like it.
const ACCEPTED_MESSAGE = "I accepted the plan. Carry on.";
const REJECTED_MESSAGE = "I rejected this plan.";

/**
 * Right-pane viewport for plan_month sessions.
 * Re-renders on every PLAN_GENERATED event from the workspace.
 *
 * The plan reads as a list, not a status board: while a plan is being
 * written every post is pending, and a Kanban of that is one full lane and
 * three empty ones. The Plan tab keeps the board for when posts move.
 *
 * A plan the agent submits arrives as a proposal (`status: "proposed"`) and
 * is saved only when the person accepts it here; the decision bar under the
 * header is that choice. An event with no status predates proposals and is
 * a saved plan, so it draws no bar and no chip.
 *
 * Props:
 *   - payload: { type: "plan", id, name, days[], character, strategy, status?, proposal_id?, replaces_plan_id?, ... }
 *   - steps: live pipeline steps from the workspace (drives the loading ladder)
 *   - building: the plan is still being built (no payload yet, run not failed)
 *   - onReviseDay?(dayIndex)
 *   - onSendMessage?(text): a chat turn into the live session; absent on a read-only pane
 *   - sessionId?: the session the proposal was made in
 */
export default function PlanViewport({ payload, steps = [], building = false, onReviseDay, onSendMessage, sessionId }) {
  const { t, i18n } = useLingui();
  // Accept answers with the saved plan. It is shown at once rather than
  // waiting for the session's own PLAN_GENERATED echo, and dropped the
  // moment the next payload arrives, which is that echo or a new proposal.
  const [saved, setSaved] = useState(null);
  useEffect(() => { setSaved(null); }, [payload]);

  if (!payload || payload.type !== "plan") {
    return (
      <PipelineProgress
        stages={PLAN_STAGES.map((s) => ({ ...s, label: i18n._(s.label) }))}
        steps={steps}
        activeId={ContentStep.SYNTHESIZE_PLAN}
        synthesising={building}
        virtualWaitsForPrior
        lines={PLAN_LINES.map((m) => i18n._(m))}
        buildingLabel={t`Building your plan`}
        streamingSubtitle={t`Synthesizing your plan…`}
        idleSubtitle={t`Researching pillars and synthesizing the plan…`}
      />
    );
  }

  const plan = saved || payload;
  const narrator = plan.character?.name;
  const voice = plan.character?.voice;
  const dayCount = Array.isArray(plan.days) ? plan.days.length : 0;
  // The period this plan manages, so a revision reads as "this plan", not "a plan".
  const period = formatDateRange(planStartOf(plan), planEndOf(plan), { locale: i18n.locale });

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border/60 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{plan.name || <Trans>Content plan</Trans>}</p>
          {narrator && (
            <p className="text-xs text-muted-foreground truncate">
              {voice ? <Trans>Narrator: {narrator} · {voice}</Trans> : <Trans>Narrator: {narrator}</Trans>}
            </p>
          )}
        </div>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {period && <>{period} · </>}
          <Plural value={dayCount} one="# day" other="# days" />
        </span>
      </div>

      {/* Keyed by the proposal, so a re-submitted plan opens a fresh bar
          (textarea closed, no stale error) and a decision resets its state. */}
      <PlanDecision
        key={plan.proposal_id || plan.id || "plan"}
        plan={plan}
        sessionId={sessionId}
        onSendMessage={onSendMessage}
        onAccepted={(out) => setSaved({ type: "plan", ...out, status: PlanStatus.ACCEPTED })}
      />

      <PlanStrategy strategy={plan.strategy} days={plan.days} />
      <PlanList plan={plan} onReviseDay={onReviseDay} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// The decision bar
// ---------------------------------------------------------------------------

/**
 * One slot under the plan's header, with one of four things in it:
 *   proposed  → the consequence of Accept in a line, then Accept / Modify / Reject
 *   accepted  → "Saved as your plan"
 *   rejected  → the quiet note that the plan was discarded
 *   no status → nothing (a plan saved before proposals existed)
 *
 * Modify sends the person's words into the chat and leaves the plan proposed;
 * the agent answers with a new proposal, which remounts this bar.
 */
function PlanDecision({ plan, sessionId, onSendMessage, onAccepted }) {
  const { t } = useLingui();
  const noteId = useId();
  const [pending, setPending] = useState(null); // "accept" | "reject" while the call is in flight
  const [rejected, setRejected] = useState(false);
  const [modifying, setModifying] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  if (rejected || plan.status === PlanStatus.REJECTED) {
    return (
      <p role="status" className="shrink-0 border-b border-border/60 px-4 py-2.5 text-sm text-muted-foreground">
        <Trans>Plan discarded. Tell Duct what to plan instead, or close this tab.</Trans>
      </p>
    );
  }
  if (plan.status === PlanStatus.ACCEPTED) {
    return (
      <div className="shrink-0 border-b border-border/60 px-4 py-2">
        <Badge variant="success"><Check aria-hidden="true" /> <Trans>Saved as your plan</Trans></Badge>
      </div>
    );
  }
  if (plan.status !== PlanStatus.PROPOSED) return null;

  const busy = pending !== null;

  async function accept() {
    setError("");
    setPending("accept");
    try {
      const out = await acceptPlan(sessionId, plan.proposal_id);
      onAccepted(out);
      onSendMessage?.(ACCEPTED_MESSAGE);
    } catch {
      setError(t`Couldn't save the plan. Try again.`);
      setPending(null);
    }
  }

  async function reject() {
    setError("");
    setPending("reject");
    try {
      await rejectPlan(sessionId, plan.proposal_id);
      setRejected(true);
      onSendMessage?.(REJECTED_MESSAGE);
    } catch {
      setError(t`Couldn't discard the plan. Try again.`);
      setPending(null);
    }
  }

  function sendNote(e) {
    e.preventDefault();
    const text = note.trim();
    if (!text) return;
    onSendMessage?.(text);
    setNote("");
    setModifying(false);
  }

  return (
    <div className="shrink-0 border-b border-primary/20 bg-primary/5 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="min-w-0 text-sm">
          <span className="font-medium"><Trans>Duct proposes this plan.</Trans></span>{" "}
          <span className="text-muted-foreground">
            {plan.replaces_plan_id
              ? <Trans>Accept replaces your plan from today on; posts already drafted stay.</Trans>
              : <Trans>Accept saves this as your plan.</Trans>}
          </span>
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <Button type="button" onClick={accept} disabled={busy}>
            {pending === "accept" ? <Trans>Saving…</Trans> : <Trans>Accept</Trans>}
          </Button>
          <Button type="button" variant="outline" onClick={() => setModifying((v) => !v)} disabled={busy} aria-expanded={modifying}>
            <Trans>Modify</Trans>
          </Button>
          <Button type="button" variant="ghost" onClick={reject} disabled={busy}>
            {pending === "reject" ? <Trans>Discarding…</Trans> : <Trans>Reject</Trans>}
          </Button>
        </div>
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
      {modifying && (
        <form onSubmit={sendNote} className="mt-3 flex flex-col gap-2">
          <label htmlFor={noteId} className="text-xs font-medium text-muted-foreground"><Trans>What should change?</Trans></label>
          <Textarea
            id={noteId}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={t`Fewer videos in week two, and start with the before-and-after…`}
            className="min-h-16 bg-background"
            disabled={busy}
            autoFocus
          />
          <div className="flex items-center justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setModifying(false)} disabled={busy}><Trans>Cancel</Trans></Button>
            <Button type="submit" disabled={busy || !note.trim()}><Trans>Send</Trans></Button>
          </div>
        </form>
      )}
    </div>
  );
}
