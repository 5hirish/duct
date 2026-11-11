"use client";

import { useState } from "react";
import Link from "next/link";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { ChevronDown, Cloud, Laptop, Pause, Play, Trash2, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { formatDate, formatTime, relativeTime } from "@/lib/format";
import { Cadence, Outcome, ScheduleState, runConversationHref, runCost, scheduleState } from "@/lib/schedules";
import { cn } from "@/lib/utils";

const STATE = {
  [ScheduleState.RUNNING]: { label: msg`Running`, variant: "info" },
  [ScheduleState.NEEDS_YOU]: { label: msg`Needs you`, variant: "warning" },
  [ScheduleState.WAITING_ON_YOU]: { label: msg`Waiting on you`, variant: "info" },
  [ScheduleState.PAUSED]: { label: msg`Paused`, variant: "secondary" },
  [ScheduleState.ACTIVE]: { label: msg`Active`, variant: "success" },
};

const OUTCOMES = {
  [Outcome.PROPOSED]: msg`Proposed a plan`,
  [Outcome.NOTHING_NEW]: msg`Nothing new, no model call`,
  [Outcome.NO_PROPOSAL]: msg`Ran, proposed nothing`,
  [Outcome.FAILED]: msg`Failed`,
  [Outcome.SKIPPED]: msg`Skipped`,
  [Outcome.INTERRUPTED]: msg`Interrupted`,
};

// Mirror of backend service/schedules.Reason. A model failure's own code (a
// rate limit, a refused key) passes through and is worded as "Error".
const REASONS = {
  stale: msg`missed by more than a week`,
  monthly_cap: msg`this month's limit is reached`,
  not_member: msg`its creator left the project`,
  no_model_key: msg`no saved model key`,
  project_busy: msg`another run for this project was going`,
  timeout: msg`took longer than 15 minutes`,
  interrupted: msg`stopped by a restart`,
  error: msg`error`,
  unknown_job: msg`unknown job`,
};

// What to do about a "Needs you", and where.
const FIXES = {
  no_model_key: { text: msg`Save a model key so a run can start without you.`, href: "/settings/models", action: msg`Models & providers` },
  monthly_cap: { text: msg`It will run again next month, or raise the limit.`, href: null, action: null },
  not_member: { text: msg`Runs act as their creator. Recreate it from your account.`, href: null, action: null },
};

function useTrigger(s) {
  const { t, i18n } = useLingui();
  const time = s.at_time || "09:00";
  const zone = s.timezone || "UTC";
  // 2026-11-16 is a Monday, so +weekday names the day in the reader's language.
  const day = new Date(2026, 10, 16 + (Number(s.weekday) || 0)).toLocaleDateString(i18n.locale, { weekday: "long" });
  switch (s.cadence) {
    case Cadence.HOURLY: return t`Every hour`;
    case Cadence.DAILY: return t`Daily at ${time}, ${zone}`;
    case Cadence.WEEKDAYS: return t`Weekdays at ${time}, ${zone}`;
    case Cadence.WEEKLY: return t`Every ${day} at ${time}, ${zone}`;
    default: return t`Only when you run it`;
  }
}

/**
 * One schedule: what it runs and when, the state it is in, the last run with
 * its cost and a way into the conversation it left, and the history of every
 * run, skips included, each with its reason.
 *
 * Props: `schedule` (the route's shape), `onRunNow`, `onToggle(enabled)`,
 * `onDelete`, `loadHistory()` → rows, `busy` while an action is in flight.
 */
export default function ScheduleCard({ schedule: s, onRunNow, onToggle, onDelete, loadHistory, busy = false }) {
  const { t, i18n } = useLingui();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(null);
  const state = scheduleState(s);
  const meta = STATE[state];
  const trigger = useTrigger(s);
  const last = s.last;
  const lastHref = runConversationHref(last?.conversation_id);
  const fix = s.needs_reason ? FIXES[s.needs_reason] : null;
  const runs = s.runs_this_month || 0;
  const cap = s.monthly_cap || 0;
  const HostIcon = s.host === "local" ? Laptop : Cloud;
  const next = s.next_run_at ? new Date(s.next_run_at) : null;
  const nextDate = next ? formatDate(next, { withYear: false, locale: i18n.locale }) : "";
  const nextTime = next ? formatTime(next, { locale: i18n.locale }) : "";
  const nextText = next ? t`Next: ${nextDate}, ${nextTime}` : null;

  async function toggleHistory() {
    const opening = !open;
    setOpen(opening);
    if (opening && rows === null && loadHistory) {
      try {
        setRows(await loadHistory());
      } catch {
        setRows([]);
      }
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="truncate text-sm font-semibold">{s.name || t`Plan from your work`}</p>
          <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
            <span>{trigger}</span>
            <span aria-hidden>·</span>
            <span className="inline-flex items-center gap-1">
              <HostIcon className="size-3" aria-hidden />
              {s.host === "local" ? <Trans>This computer</Trans> : <Trans>Duct cloud</Trans>}
            </span>
            {nextText && s.enabled && <><span aria-hidden>·</span><span>{nextText}</span></>}
          </p>
        </div>
        <Badge variant={meta.variant} className="shrink-0">
          {state === ScheduleState.RUNNING && <Spinner className="size-3" />}
          {i18n._(meta.label)}
        </Badge>
      </div>

      {fix && (
        <p className="text-sm text-muted-foreground">
          {i18n._(fix.text)}{" "}
          {fix.href && <Link className="underline" href={fix.href}>{i18n._(fix.action)}</Link>}
        </p>
      )}

      {last && (
        <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
          <span>{relativeTime(last.at, { locale: i18n.locale })}</span>
          <span aria-hidden>·</span>
          <span className="text-foreground">{OUTCOMES[last.outcome] ? i18n._(OUTCOMES[last.outcome]) : last.outcome}</span>
          {last.reason && <span>({REASONS[last.reason] ? i18n._(REASONS[last.reason]) : i18n._(REASONS.error)})</span>}
          {runCost(last.cost_usd) && <><span aria-hidden>·</span><span className="tabular-nums">{runCost(last.cost_usd)}</span></>}
          {lastHref && (
            <>
              <span aria-hidden>·</span>
              <Link className="font-medium text-brand underline-offset-2 hover:underline" href={lastHref}>
                {last.outcome === Outcome.PROPOSED ? <Trans>Review the proposal</Trans> : <Trans>Open the run</Trans>}
              </Link>
            </>
          )}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground tabular-nums">
          <Trans>{runs} of {cap} runs this month</Trans>
        </span>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button size="sm" variant="outline" className="h-8" onClick={onRunNow} disabled={busy || s.running}>
            <Zap className="size-3.5" aria-hidden /> <Trans>Run now</Trans>
          </Button>
          <Button size="sm" variant="outline" className="h-8" onClick={() => onToggle?.(!s.enabled)} disabled={busy}>
            {s.enabled
              ? <><Pause className="size-3.5" aria-hidden /> <Trans>Pause</Trans></>
              : <><Play className="size-3.5" aria-hidden /> <Trans>Resume</Trans></>}
          </Button>
          {s.mine && (
            <Button size="sm" variant="ghost" className="h-8" onClick={onDelete} disabled={busy} aria-label={t`Delete schedule`}>
              <Trash2 className="size-3.5" aria-hidden />
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-2 border-t border-border/60 pt-2">
        <button
          type="button"
          onClick={toggleHistory}
          aria-expanded={open}
          className="inline-flex items-center gap-1 self-start text-xs text-muted-foreground hover:text-foreground"
        >
          <Trans>History</Trans>
          <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
        </button>
        {open && (
          rows === null ? (
            <Spinner className="size-4 text-muted-foreground" />
          ) : rows.length === 0 ? (
            <p className="text-xs text-muted-foreground"><Trans>No runs yet.</Trans></p>
          ) : (
            <ul className="flex flex-col gap-1 text-xs">
              {rows.map((r, i) => {
                const href = runConversationHref(r.conversation_id);
                const when = new Date(r.at);
                return (
                  <li key={`${r.at}-${i}`} className="flex flex-wrap items-center gap-x-1.5 text-muted-foreground">
                    <span className="tabular-nums">
                      {formatDate(when, { withYear: false, locale: i18n.locale })}, {formatTime(when, { locale: i18n.locale })}
                    </span>
                    <span className="text-foreground">{OUTCOMES[r.outcome] ? i18n._(OUTCOMES[r.outcome]) : r.outcome}</span>
                    {r.reason && <span>({REASONS[r.reason] ? i18n._(REASONS[r.reason]) : i18n._(REASONS.error)})</span>}
                    {r.will_retry && <span><Trans>retrying in 15 minutes</Trans></span>}
                    {runCost(r.cost_usd) && <span className="tabular-nums">{runCost(r.cost_usd)}</span>}
                    {href && <Link className="underline" href={href}><Trans>Open</Trans></Link>}
                  </li>
                );
              })}
            </ul>
          )
        )}
      </div>
    </Card>
  );
}
