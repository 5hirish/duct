"use client";

import { ArrowDown, ArrowUp, Clock, Compass, FlaskConical, TrendingUp } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { POST_TYPE_LABELS } from "@/lib/contentEnums";
import { TYPE_ICON } from "@/components/content/PostMiniCard";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";
import { Card } from "@/components/ui/card";
import { HelpTip } from "@/components/ui/page";
import { titleCase } from "@/lib/format";
import { GoalKind, Standing, channelRows, hasStrategy, planGoal, plainWords } from "@/lib/planStrategy";
import { cn } from "@/lib/utils";

export { hasStrategy, typeMix } from "@/lib/planStrategy";

const GOAL_WORDS = {
  [GoalKind.INTENT]: msg`Saves and shares per post, the closest sign of intent the posts report.`,
  [GoalKind.ENGAGEMENT]: msg`Comments, shares and saves per post.`,
  [GoalKind.REACH]: msg`People reached per post.`,
};

const STANDING_WORDS = {
  [Standing.LEADS]: msg`earns the most per post`,
  [Standing.TRAILS]: msg`earns less per post`,
  [Standing.UNTESTED]: msg`no results yet`,
};

/**
 * What the plan bets on, one row per channel, with the agent's reasons one
 * click away.
 *
 * It was one line for the whole plan, "Scaling Video · Testing Image", and
 * once a plan spread over TikTok, Instagram and LinkedIn that line was true
 * of one channel and said over all three, LinkedIn's text posts included.
 * Each channel is planned on its own history now (backend channel_mix.py),
 * so each gets its row: what it leans on and tries, counted from its days,
 * and how its share moved since the last plan and why, from the facts the
 * plan stored (`lib/planStrategy.js`). The agent's sentences, the split's
 * reasoning and the test it runs are behind the "?".
 *
 * Props:
 *   - strategy: ContentPlan.strategy (the agent's fields plus `mix`)
 *   - days: the plan's days
 *   - channel: the board's channel filter; one row when set
 *   - variant: "strip" in a pane (a ruled band), "card" on the board page
 *   - className: extra classes for the outer element
 */
export default function PlanStrategy({ strategy, days = [], channel = null, variant = "strip", className }) {
  const { t, i18n } = useLingui();
  const s = strategy || {};
  const all = channelRows(s, days);
  const rows = channel ? all.filter((row) => row.channel === channel) : all;
  const goal = planGoal(s);
  // A proven type is the one fact that needs history; without it, the
  // lesson field is whatever the model put there, never a lesson.
  const proven = Boolean(s.exploit);
  const leaned = typeLabel(i18n, s.exploit);
  const tried = typeLabel(i18n, s.explore);
  const why = [
    goal && { term: <Trans>Judged on</Trans>, text: i18n._(GOAL_WORDS[goal]) },
    s.review_notes && { term: <Trans>Why this split</Trans>, text: s.review_notes },
    s.experiment && { term: <Trans>What this plan tests</Trans>, text: s.experiment },
    proven && s.exploit_evidence && { term: <Trans>Why lean on {leaned}</Trans>, text: s.exploit_evidence },
    s.explore && s.explore_evidence && { term: <Trans>Why try {tried}</Trans>, text: s.explore_evidence },
    proven && s.lesson && { term: <Trans>Learned</Trans>, text: s.lesson },
  ].filter(Boolean);
  const telling = rows.some((row) => row.scaling || row.testing.length || row.types.length > 1);
  if (!hasStrategy(s) && !telling) return null;
  if (!rows.length && !why.length && !s.best_times) return null;

  const body = (
    <>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <h3 className="font-medium">
          <Trans>What the plan bets on</Trans>
        </h3>
        <div className="flex min-w-0 items-center gap-2">
          {s.best_times && (
            <span className="inline-flex min-w-0 items-center gap-1.5">
              <Clock className="size-3.5 shrink-0" aria-hidden />
              <span className="shrink-0 whitespace-nowrap">
                <Trans>Best times</Trans>
              </span>
              {/* The agent's words; one line here. */}
              <span className="min-w-0 max-w-56 truncate text-foreground" title={s.best_times}>{s.best_times}</span>
            </span>
          )}
          {why.length > 0 && (
            <HelpTip label={t`Why this plan`} className="-my-1.5 -mr-1.5">
              <dl className="grid gap-3 text-sm">
                {why.map((row, i) => (
                  <div key={i}>
                    <dt className="font-medium">{row.term}</dt>
                    <dd className="text-muted-foreground">{plainWords(row.text)}</dd>
                  </div>
                ))}
              </dl>
            </HelpTip>
          )}
        </div>
      </div>
      {rows.length > 0 && (
        <ul className="grid gap-3.5 @xl:gap-2.5">
          {rows.map((row) => (
            <ChannelRow key={row.channel} row={row} />
          ))}
        </ul>
      )}
    </>
  );

  return variant === "card" ? (
    <Card variant="quiet" size="sm" aria-label={t`Plan strategy`} className={cn("@container shrink-0", className)}>
      {body}
    </Card>
  ) : (
    <section
      aria-label={t`Plan strategy`}
      className={cn("@container flex shrink-0 flex-col gap-3 border-b border-border/60 px-4 py-3", className)}
    >
      {body}
    </section>
  );
}

/** One channel: its name and posts, then what it leans on and tries, then how its share moved. */
function ChannelRow({ row }) {
  const { i18n } = useLingui();
  const count = (type) => row.types.find((x) => x.type === type)?.count;
  const settled = row.scaling || row.testing.length > 0;
  const standing = STANDING_WORDS[row.standing];
  return (
    <li className="grid min-w-0 gap-x-4 gap-y-1 text-sm @xl:grid-cols-[11rem_minmax(0,1fr)] @xl:items-center">
      <span className="flex min-w-0 items-center gap-2">
        <PlatformGlyph platform={row.channel} className="size-4 shrink-0" />
        <span className="truncate font-medium">{platformMeta(row.channel).label}</span>
        <span className="shrink-0 tabular-nums text-muted-foreground">
          <Plural value={row.posts} one="# post" other="# posts" />
        </span>
      </span>
      <span className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
        {row.scaling && (
          <Bet icon={TrendingUp} tone="text-success" label={<Trans>Leans on</Trans>}>
            <TypeChip type={row.scaling} count={count(row.scaling)} />
          </Bet>
        )}
        {row.testing.length > 0 && (
          <Bet icon={FlaskConical} tone="text-info" label={<Trans>Tries</Trans>}>
            {row.testing.map((type) => (
              <TypeChip key={type} type={type} count={count(type)} />
            ))}
          </Bet>
        )}
        {!settled &&
          (row.types.length > 1 ? (
            <Bet icon={Compass} tone="text-info" label={<Trans>Finding what works</Trans>}>
              {row.types.map(({ type, count: n }) => (
                <TypeChip key={type} type={type} count={n} />
              ))}
            </Bet>
          ) : (
            row.types.map(({ type, count: n }) => <TypeChip key={type} type={type} count={n} />)
          ))}
        {(row.change || standing) && (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            {row.change > 0 && <ArrowUp className="size-3.5 text-success" aria-hidden />}
            {row.change < 0 && <ArrowDown className="size-3.5 text-warning" aria-hidden />}
            {row.change > 0 && <Plural value={row.change} one="# more than last plan" other="# more than last plan" />}
            {row.change < 0 && (
              <Plural value={-row.change} one="# fewer than last plan" other="# fewer than last plan" />
            )}
            {row.change ? standing && <span aria-hidden>·</span> : null}
            {standing && i18n._(standing)}
          </span>
        )}
      </span>
    </li>
  );
}

function Bet({ icon: Icon, tone, label, children }) {
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      <Icon className={cn("size-3.5 shrink-0", tone)} aria-hidden />
      <span className="text-muted-foreground">{label}</span>
      {children}
    </span>
  );
}

function typeLabel(i18n, type) {
  if (!type) return "";
  return POST_TYPE_LABELS[type] ? i18n._(POST_TYPE_LABELS[type]) : titleCase(type);
}

function TypeChip({ type, count }) {
  const { i18n } = useLingui();
  const Icon = TYPE_ICON[type];
  const label = typeLabel(i18n, type);
  return (
    <span className="inline-flex items-center gap-1 font-medium text-foreground">
      {Icon && <Icon className="size-3.5 shrink-0" aria-hidden />}
      {label}
      {count != null && <span className="font-normal tabular-nums text-muted-foreground">{count}</span>}
    </span>
  );
}
