"use client";

import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { ArrowRight, ChevronRight } from "lucide-react";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";
import { POST_TYPE_LABELS } from "@/lib/contentEnums";
import { planChanges } from "@/lib/contentSchedule";
import { formatDate, titleCase } from "@/lib/format";
import { plainWords } from "@/lib/planStrategy";
import { Card } from "@/components/ui/card";
import SourceChips from "./SourceChips";
import { dayIdea } from "@/lib/contentFeed";

// What each field is called on a changed day. Topic has no label: it is the
// day's headline, and its old wording sits under it.
const FIELD_LABELS = {
  post_type: msg`Type`,
  platforms: msg`Channel`,
  pillar: msg`Pillar`,
  hook_type: msg`Hook`,
  hook_emotion: msg`Emotion`,
  funnel_stage: msg`Funnel stage`,
  objective: msg`Objective`,
  series: msg`Series`,
  experiment: msg`Experiment`,
  format_slug: msg`Format`,
};

// What a person decides on, shown on the day itself. The rest are the
// planner's own tags (hook, emotion, funnel stage, objective, experiment,
// format): real, and worth a look, but listed in full they were twenty rows
// of before → after under five days, and the idea itself got lost.
const SHOWN_FIELDS = new Set(["topic", "post_type", "platforms", "pillar", "series"]);

/**
 * A proposal that changes some days of a plan, shown as those days alone.
 * Each day is a card: the date, the new idea over the one it replaces, the
 * type when it moved, and the new pillar and series as chips. The planner's
 * other tags fold under "More changes". The rest of the plan is not drawn,
 * because Accept does not touch it, and thirty unchanged rows are where a
 * one-day change used to get lost.
 *
 * Props:
 *   - plan: the PLAN_GENERATED payload, with `changed_days` and `previous_days`
 */
export default function PlanChanges({ plan }) {
  const changes = planChanges(plan);
  const rest = Math.max((Array.isArray(plan?.days) ? plan.days.length : 0) - changes.length, 0);
  return (
    <div className="@container min-h-0 flex-1 overflow-y-auto px-4 py-3">
      <ol className="flex flex-col gap-2">
        {changes.map((change) => (
          <ChangedDay key={change.index} change={change} />
        ))}
      </ol>
      {rest > 0 && (
        <p className="pt-3 text-xs text-muted-foreground">
          <Plural value={rest} one="The other # day stays as it is." other="The other # days stay as they are." />
        </p>
      )}
    </div>
  );
}

function ChangedDay({ change }) {
  const { t, i18n } = useLingui();
  const { date, before, after, fields } = change;
  const channel = Array.isArray(after.platforms) ? after.platforms[0] : null;
  const value = (field, raw) => {
    if (field === "post_type") return POST_TYPE_LABELS[raw] ? i18n._(POST_TYPE_LABELS[raw]) : titleCase(raw);
    if (field === "platforms") return (Array.isArray(raw) ? raw : []).map((p) => platformMeta(p).label).join(", ");
    return plainWords(String(raw ?? ""));
  };
  const was = fields.includes("topic") ? before.topic || "" : "";
  const typeMoved = fields.includes("post_type") && before.post_type;
  const chips = ["pillar", "series"].filter((f) => fields.includes(f) && after[f]);
  const more = fields.filter((f) => !SHOWN_FIELDS.has(f));
  const day = date ? new Date(date) : null;
  return (
    <li>
    <Card size="sm" className="grid grid-cols-[2.75rem_minmax(0,1fr)] gap-3 p-3">
      {/* The date as a calendar leaf: the one thing every card has, read
          down the column before any title. */}
      <div className="flex flex-col items-center self-start rounded-lg bg-muted/60 py-1.5 text-center leading-none" aria-hidden="true">
        {day && (
          <>
            <span className="text-2xs font-medium uppercase text-muted-foreground">
              {day.toLocaleDateString(i18n.locale, { month: "short" })}
            </span>
            <span className="mt-1 text-lg font-semibold tabular-nums">{day.getDate()}</span>
            <span className="mt-1 text-2xs text-muted-foreground">
              {day.toLocaleDateString(i18n.locale, { weekday: "short" })}
            </span>
          </>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        {day && (
          <span className="sr-only">{formatDate(date, { withYear: false, locale: i18n.locale })}</span>
        )}
        <p className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          {channel && <PlatformGlyph platform={channel} className="size-3.5 shrink-0" />}
          {typeMoved ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-1.5 py-0.5 font-medium text-foreground">
              <span className="text-muted-foreground line-through">{value("post_type", before.post_type)}</span>
              <ArrowRight className="size-3 shrink-0" aria-label={t`changes to`} />
              {value("post_type", after.post_type)}
            </span>
          ) : (
            after.post_type && <span>{value("post_type", after.post_type)}</span>
          )}
        </p>
        <p className="text-sm font-medium leading-snug [overflow-wrap:anywhere]">{after.topic}</p>
        {was && (
          <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
            <span className="sr-only"><Trans>Replaces:</Trans> </span>
            <span className="line-through decoration-muted-foreground/60">{was}</span>
          </p>
        )}
        {dayIdea(after) && (
          <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{dayIdea(after)}</p>
        )}
        <SourceChips day={after} />
        {chips.length > 0 && (
          <ul className="flex min-w-0 flex-wrap gap-1">
            {chips.map((field) => (
              <li
                key={field}
                className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full border border-border/70 px-2 py-0.5 text-xs"
              >
                <span className="shrink-0 text-muted-foreground">{i18n._(FIELD_LABELS[field])}</span>
                <span className="truncate font-medium">{value(field, after[field])}</span>
              </li>
            ))}
          </ul>
        )}
        {more.length > 0 && <MoreChanges fields={more} before={before} after={after} value={value} />}
      </div>
    </Card>
    </li>
  );
}

/** The planner's own tags that moved, folded: one line until opened. */
function MoreChanges({ fields, before, after, value }) {
  const { t, i18n } = useLingui();
  const names = fields.map((f) => i18n._(FIELD_LABELS[f]).toLowerCase()).join(", ");
  return (
    <details className="group text-xs">
      <summary className="flex min-h-6 cursor-pointer list-none items-center gap-1 text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
        <span className="truncate">
          <Plural value={fields.length} one="# more change" other="# more changes" />
          <span aria-hidden="true"> · </span>
          {names}
        </span>
      </summary>
      <dl className="mt-1.5 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 pl-4.5">
        {fields.map((field) => {
          const from = value(field, before[field]);
          const to = value(field, after[field]);
          return (
            <div key={field} className="contents">
              <dt className="text-muted-foreground">{i18n._(FIELD_LABELS[field])}</dt>
              <dd className="min-w-0 [overflow-wrap:anywhere]">
                {to ? (
                  <>
                    <span className="font-medium">{to}</span>
                    {from && <span className="text-muted-foreground"> <Trans>(was {from})</Trans></span>}
                  </>
                ) : (
                  <span className="text-muted-foreground">
                    <Trans>removed</Trans>
                    {from && <> · <span className="line-through">{from}</span></>}
                  </span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </details>
  );
}
