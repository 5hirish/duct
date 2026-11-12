"use client";

import { useState } from "react";
import Link from "next/link";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import {
  ArrowRight, Check, ChevronDown, Cloud, Laptop, Minus, Pause, Play, RotateCcw, SkipForward, Tag, Trash2, X, Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDate, formatTime, relativeTime } from "@/lib/format";
import {
  Cadence, Outcome, ScheduleState, capPips, runConversationHref, runCost, runStrip, scheduleState,
} from "@/lib/schedules";
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

// A run's stone carries a glyph as well as a colour (WCAG 1.4.1): a tick
// for a plan proposed, a dash for a quiet week, a cross for a failure.
const OUTCOME_ICONS = {
  [Outcome.PROPOSED]: Check,
  [Outcome.NOTHING_NEW]: Minus,
  [Outcome.NO_PROPOSAL]: Minus,
  [Outcome.FAILED]: X,
  [Outcome.SKIPPED]: SkipForward,
  [Outcome.INTERRUPTED]: RotateCcw,
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
  no_repository: msg`no repository to watch`,
};

// What to do about a "Needs you", and where.
const FIXES = {
  no_model_key: { text: msg`Save a model key so a run can start without you.`, href: "/settings/models", action: msg`Models & providers` },
  monthly_cap: { text: msg`It will run again next month, or raise the limit.`, href: null, action: null },
  not_member: { text: msg`Runs act as their creator. Recreate it from your account.`, href: null, action: null },
  no_repository: { text: msg`Connect a GitHub repository so there are releases to watch.`, href: "/connections?connector=github", action: msg`Toolbox` },
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
    case Cadence.ON_RELEASE: return t`When a release is published on GitHub`;
    default: return t`Only when you run it`;
  }
}

/**
 * One schedule. It leads with a calendar leaf for the next run (the answer to
 * "when does this happen", readable before a word is), then what it runs,
 * then a strip of its last runs as stones, oldest first, with the next one
 * outlined at the end: a schedule that has been proposing every week looks
 * like a row of orange ticks, one that keeps finding nothing like a row of
 * dashes, and a broken one shows its crosses. The newest result and the one
 * thing to do about it come after, with the full history behind a fold.
 *
 * Props: `schedule` (the route's shape, `recent` newest first), `onRunNow`,
 * `onToggle(enabled)`, `onDelete`, `loadHistory()` → rows, `busy` while an
 * action is in flight.
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
  const waiting = state === ScheduleState.WAITING_ON_YOU && lastHref;
  const recent = Array.isArray(s.recent) ? s.recent : last ? [last] : [];

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
    <Card className={cn("@container flex flex-col gap-4", waiting && "border-primary/40")}>
      <div className="flex items-start gap-4">
        <NextRunLeaf schedule={s} state={state} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex items-start justify-between gap-3">
            <p className="min-w-0 text-sm font-semibold break-words">{s.name || t`Plan from your work`}</p>
            <Badge variant={meta.variant} className="shrink-0">
              {state === ScheduleState.RUNNING && <Spinner className="size-3" />}
              {i18n._(meta.label)}
            </Badge>
          </div>
          <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
            <span>{trigger}</span>
            <span aria-hidden>·</span>
            <span className="inline-flex items-center gap-1">
              <HostIcon className="size-3" aria-hidden />
              {s.host === "local" ? <Trans>This computer</Trans> : <Trans>Duct cloud</Trans>}
            </span>
          </p>
        </div>
      </div>

      {/* Under the words from @md, where the leaf's column leaves room for it;
          full width below that, so eight stones never wrap on a phone. */}
      <RunStrip recent={recent} enabled={s.enabled} running={s.running} className="-mt-2 @md:pl-18" />

      {fix ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-warning/10 px-3 py-2">
          <p className="text-sm">{i18n._(fix.text)}</p>
          {fix.href && (
            <Button asChild size="sm" variant="outline" className="h-8">
              <Link href={fix.href}>{i18n._(fix.action)}</Link>
            </Button>
          )}
        </div>
      ) : last && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{OUTCOMES[last.outcome] ? i18n._(OUTCOMES[last.outcome]) : last.outcome}</span>
            {last.reason && <span>({REASONS[last.reason] ? i18n._(REASONS[last.reason]) : i18n._(REASONS.error)})</span>}
            <span aria-hidden>·</span>
            <span>{relativeTime(last.at, { locale: i18n.locale })}</span>
            {runCost(last.cost_usd) && <><span aria-hidden>·</span><span className="tabular-nums">{runCost(last.cost_usd)}</span></>}
          </p>
          {lastHref && (waiting ? (
            <Button asChild size="sm" className="h-8">
              <Link href={lastHref}><Trans>Review the plan</Trans> <ArrowRight className="size-3.5" aria-hidden /></Link>
            </Button>
          ) : (
            <Link className="text-xs font-medium text-brand underline-offset-2 hover:underline" href={lastHref}>
              <Trans>Open the run</Trans>
            </Link>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-3">
        <div className="flex items-center gap-3">
          <CapMeter used={runs} cap={cap} />
          <button
            type="button"
            onClick={toggleHistory}
            aria-expanded={open}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <Trans>History</Trans>
            <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button size="sm" variant="ghost" className="h-8" onClick={onRunNow} disabled={busy || s.running}>
            <Zap className="size-3.5" aria-hidden /> <Trans>Run now</Trans>
          </Button>
          <Button size="sm" variant="ghost" className="h-8" onClick={() => onToggle?.(!s.enabled)} disabled={busy}>
            {s.enabled
              ? <><Pause className="size-3.5" aria-hidden /> <Trans>Pause</Trans></>
              : <><Play className="size-3.5" aria-hidden /> <Trans>Resume</Trans></>}
          </Button>
          {s.mine && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button size="sm" variant="ghost" className="h-8 text-muted-foreground" onClick={onDelete} disabled={busy} aria-label={t`Delete schedule`}>
                  <Trash2 className="size-3.5" aria-hidden />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t`Delete schedule`}</TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      {open && <History rows={rows} />}
    </Card>
  );
}

/**
 * The next run as a calendar leaf: the weekday on an orange band, the date
 * large, the time under it. Paused greys the band; needing the person rings
 * it amber; running shows the spinner where the date would be.
 */
function NextRunLeaf({ schedule: s, state }) {
  const { t, i18n } = useLingui();
  const paused = state === ScheduleState.PAUSED;
  const running = state === ScheduleState.RUNNING;
  if (s.cadence === Cadence.ON_RELEASE && !running) {
    // No date to show: it runs when a release lands, checked each hour.
    return (
      <div className="sched-leaf" data-state={state} role="img" aria-label={t`Runs on each GitHub release`}>
        <span className="sched-leaf-band text-2xs font-semibold">{paused ? t`Paused` : t`Release`}</span>
        <span className="sched-leaf-day flex h-8 items-center">
          {paused ? <Pause className="size-4" aria-hidden /> : <Tag className="size-5 text-brand" aria-hidden />}
        </span>
        <span className="pb-1.5 text-2xs text-muted-foreground">{t`hourly`}</span>
      </div>
    );
  }
  const next = s.next_run_at ? new Date(s.next_run_at) : null;
  const band = running ? t`Now` : next ? next.toLocaleDateString(i18n.locale, { weekday: "short" }) : paused ? t`Paused` : t`Manual`;
  const nextDate = next ? formatDate(next, { withYear: false, locale: i18n.locale }) : "";
  const nextTime = next ? formatTime(next, { locale: i18n.locale }) : "";
  const label = running ? t`Running now` : next ? t`Next run ${nextDate}, ${nextTime}` : band;
  return (
    <div className="sched-leaf" data-state={state} role="img" aria-label={label}>
      <span className="sched-leaf-band text-2xs font-semibold">{band}</span>
      <span className="sched-leaf-day flex h-8 items-center text-xl font-semibold tracking-tight">
        {running ? <Spinner className="size-4 text-brand" /> : next ? next.getDate() : paused ? <Pause className="size-4" aria-hidden /> : "–"}
      </span>
      <span className="pb-1.5 text-2xs text-muted-foreground">
        {next && !running ? formatTime(next, { locale: i18n.locale }) : " "}
      </span>
    </div>
  );
}

/** The last runs as stones, oldest first, then the next one outlined. */
function RunStrip({ recent, enabled, running, className }) {
  const { t, i18n } = useLingui();
  const stones = runStrip(recent, { enabled: enabled && !running });
  const ran = stones.filter((st) => st.at).length;
  return (
    <ol className={cn("flex flex-wrap items-center gap-1", className)} aria-label={t`Last ${ran} runs`}>
      {stones.map((st) => {
        if (st.outcome === "empty") return <li key={st.key} className="sched-run" data-outcome="empty" aria-hidden />;
        if (st.outcome === "next") {
          return (
            <li key={st.key} className="sched-run" data-outcome="next" aria-label={t`Next run`}>
              <ArrowRight className="size-3" aria-hidden />
            </li>
          );
        }
        const Icon = OUTCOME_ICONS[st.outcome] || Minus;
        const when = st.at ? new Date(st.at) : null;
        const whenText = when ? formatDate(when, { withYear: false, locale: i18n.locale }) : "";
        const what = OUTCOMES[st.outcome] ? i18n._(OUTCOMES[st.outcome]) : st.outcome;
        return (
          <li key={st.key}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="sched-run" data-outcome={st.outcome} tabIndex={0} aria-label={`${whenText}: ${what}`}>
                  <Icon className="size-3" strokeWidth={2.5} aria-hidden />
                </span>
              </TooltipTrigger>
              <TooltipContent>{whenText} · {what}</TooltipContent>
            </Tooltip>
          </li>
        );
      })}
    </ol>
  );
}

/** This month's runs against the cap, one pip a run. */
function CapMeter({ used, cap }) {
  const { t } = useLingui();
  if (!cap) return null;
  return (
    <span className="inline-flex items-center gap-2 text-xs text-muted-foreground" role="img" aria-label={t`${used} of ${cap} runs this month`}>
      <span className="inline-flex items-center gap-0.5" aria-hidden>
        {capPips(used, cap).map((on, i) => <span key={i} className="sched-pip" data-used={on ? "" : undefined} />)}
      </span>
      <span className="tabular-nums" aria-hidden><Trans>{used}/{cap} this month</Trans></span>
    </span>
  );
}

function History({ rows }) {
  const { i18n } = useLingui();
  if (rows === null) return <Spinner className="size-4 text-muted-foreground" />;
  if (rows.length === 0) return <p className="text-xs text-muted-foreground"><Trans>No runs yet.</Trans></p>;
  return (
    <ul className="-mt-1 flex flex-col text-xs">
      {rows.map((r, i) => {
        const href = runConversationHref(r.conversation_id);
        const when = new Date(r.at);
        const Icon = OUTCOME_ICONS[r.outcome] || Minus;
        return (
          <li key={`${r.at}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 border-b border-border/40 py-1.5 text-muted-foreground last:border-0">
            <span className="sched-run" data-outcome={r.outcome} aria-hidden>
              <Icon className="size-3" strokeWidth={2.5} />
            </span>
            <span className="w-28 shrink-0 tabular-nums">
              {formatDate(when, { withYear: false, locale: i18n.locale })}, {formatTime(when, { locale: i18n.locale })}
            </span>
            <span className="text-foreground">{OUTCOMES[r.outcome] ? i18n._(OUTCOMES[r.outcome]) : r.outcome}</span>
            {r.reason && <span>({REASONS[r.reason] ? i18n._(REASONS[r.reason]) : i18n._(REASONS.error)})</span>}
            {r.will_retry && <span><Trans>retrying in 15 minutes</Trans></span>}
            {runCost(r.cost_usd) && <span className="tabular-nums">{runCost(r.cost_usd)}</span>}
            {href && <Link className="ml-auto font-medium text-brand hover:underline" href={href}><Trans>Open</Trans></Link>}
          </li>
        );
      })}
    </ul>
  );
}
