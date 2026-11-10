"use client";

import { CalendarSync, PencilLine } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { PlanAction, planActions, startOfDay } from "@/lib/contentSchedule";

/**
 * Chips over the plan session's composer: one click sends the request as the
 * person's own message, so the chat records what was asked. Shown only while
 * the session is idle on a saved plan; a proposal waiting on Accept, Modify
 * or Reject is the next step then, and a running turn has one already.
 *
 * Props:
 *   - plan: the saved plan the session manages (days included), or null
 *   - hidden: the session is busy, or a proposal is waiting
 *   - onSend(text)
 *   - today: a Date at the start of the day; defaults to now
 */
export default function PlanQuickActions({ plan, hidden = false, onSend, today }) {
  const { t } = useLingui();
  const actions = hidden ? [] : planActions(plan, today || startOfDay(new Date()));
  if (!actions.length) return null;

  const message = (action) =>
    action.id === PlanAction.REVISE
      ? t`Look at how this plan is doing so far and revise the days from today on. Keep the days I've already drafted.`
      : action.missed === 1
        ? t`One planned post was missed. Fit its topic into the days ahead if it is still worth making, without crowding any channel or moving the days I've drafted.`
        : t`${action.missed} planned posts were missed. Fit the best of their topics into the days ahead, without crowding any channel or moving the days I've drafted.`;

  return (
    <div className="px-3 pb-2">
      {/* On the right, the side the person's own messages sit on: these are
          things they might say, not the agent speaking. */}
      <div className="mx-auto flex max-w-3xl flex-wrap justify-end gap-2" role="group" aria-label={t`Suggested next steps`}>
        {actions.map((action) => (
          <Button
            key={action.id}
            type="button"
            variant="outline"
            size="sm"
            className="h-8 rounded-full px-3 text-xs"
            onClick={() => onSend?.(message(action))}
          >
            {action.id === PlanAction.REVISE ? (
              <>
                <PencilLine className="size-3.5" aria-hidden />
                <Trans>Revise the rest of the plan</Trans>
              </>
            ) : (
              <>
                <CalendarSync className="size-3.5" aria-hidden />
                <Plural value={action.missed} one="Catch up on # missed post" other="Catch up on # missed posts" />
              </>
            )}
          </Button>
        ))}
      </div>
    </div>
  );
}
