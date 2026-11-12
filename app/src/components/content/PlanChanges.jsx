"use client";

import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { ArrowRight } from "lucide-react";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";
import { POST_TYPE_LABELS } from "@/lib/contentEnums";
import { planChanges } from "@/lib/contentSchedule";
import { formatDate, titleCase } from "@/lib/format";
import { plainWords } from "@/lib/planStrategy";
import SourceChips from "./SourceChips";

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

/**
 * A proposal that changes some days of a plan, shown as those days alone:
 * each one's date, channel and type, the new topic over the old one, and
 * any other field that moved as before → after. The rest of the plan is not
 * drawn, because Accept does not touch it, and thirty unchanged rows are
 * where a one-day change used to get lost.
 *
 * Props:
 *   - plan: the PLAN_GENERATED payload, with `changed_days` and `previous_days`
 */
export default function PlanChanges({ plan }) {
  const changes = planChanges(plan);
  const rest = Math.max((Array.isArray(plan?.days) ? plan.days.length : 0) - changes.length, 0);
  return (
    <div className="@container min-h-0 flex-1 overflow-y-auto px-4 pb-4">
      <ol className="divide-y divide-border/60">
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
  const when = date ? formatDate(date, { withYear: false, locale: i18n.locale }) : "";
  const was = before.topic || "";
  const value = (field, raw) => {
    if (field === "post_type") return POST_TYPE_LABELS[raw] ? i18n._(POST_TYPE_LABELS[raw]) : titleCase(raw);
    if (field === "platforms") return (Array.isArray(raw) ? raw : []).map((p) => platformMeta(p).label).join(", ");
    return plainWords(String(raw ?? ""));
  };
  const moved = fields.filter((f) => f !== "topic");
  return (
    <li className="flex flex-col gap-1 py-3">
      <p className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
        {channel && <PlatformGlyph platform={channel} className="size-3.5 shrink-0" />}
        <span className="tabular-nums">{when}</span>
        {after.post_type && <span aria-hidden="true">·</span>}
        {after.post_type && <span>{value("post_type", after.post_type)}</span>}
      </p>
      <p className="text-sm font-medium [overflow-wrap:anywhere]">{after.topic}</p>
      <SourceChips day={after} />
      {fields.includes("topic") && was && (
        <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
          <Trans>Was: {was}</Trans>
        </p>
      )}
      {moved.length > 0 && (
        // One column of labels, so the values line up and read down the change.
        <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
          {moved.map((field) => {
            const from = value(field, before[field]) || t`none`;
            const to = value(field, after[field]) || t`none`;
            return (
              <div key={field} className="contents">
                <dt className="text-muted-foreground">{i18n._(FIELD_LABELS[field])}</dt>
                <dd className="flex min-w-0 flex-wrap items-center gap-x-1.5">
                  <span className="text-muted-foreground">{from}</span>
                  <ArrowRight className="size-3 shrink-0 text-muted-foreground" aria-label={t`changes to`} />
                  <span className="font-medium">{to}</span>
                </dd>
              </div>
            );
          })}
        </dl>
      )}
    </li>
  );
}
