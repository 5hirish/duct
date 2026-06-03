"use client";

import PlanKanban from "./PlanKanban";

/**
 * Right-pane viewport for plan_month sessions.
 * Re-renders on every PLAN_GENERATED event from the workspace.
 *
 * MVP: Kanban only. PlanCalendar lands in a follow-up phase.
 *
 * Props:
 *   - payload: { type: "plan", id, name, days[], character, ... }
 *   - onReviseDay?(dayIndex)
 */
export default function PlanViewport({ payload, onReviseDay }) {
  if (!payload || payload.type !== "plan") {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 gap-2">
        <div className="size-10 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
        <p className="text-sm text-muted-foreground">
          The agent is researching pillars and synthesizing the plan…
        </p>
        <p className="text-xs text-muted-foreground/70">
          Day cards will appear here as soon as the plan lands.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border/60 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{payload.name || "30-day plan"}</p>
          {payload.character?.name && (
            <p className="text-xs text-muted-foreground truncate">
              Narrator: {payload.character.name}
              {payload.character.voice ? ` · ${payload.character.voice}` : ""}
            </p>
          )}
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">
          {Array.isArray(payload.days) ? payload.days.length : 0} days
        </span>
      </div>

      <PlanKanban plan={payload} onReviseDay={onReviseDay} />
    </div>
  );
}
