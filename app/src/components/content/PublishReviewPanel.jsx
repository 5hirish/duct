"use client";

import { useId } from "react";
import { CheckCircle2, CircleX, RefreshCw, TriangleAlert } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  BAND_META,
  HOOK_LABELS,
  MARKER_LABELS,
  PANEL_METRIC_LABELS,
  PERSONA_ACTIONS,
  PanelFit,
  SanityCheckId,
  VERDICT_META,
  failedChecks,
  hookVotes,
  isScored,
  panelEchoesBaseline,
  panelTrusted,
  replyNumber,
  slideNumber,
  weakestMarkers,
} from "@/lib/contentReview";
import { relativeTime } from "@/lib/format";

// How many fixes the publish dialog shows: the dialog is a last look before
// posting, not the place to read all six.
const COMPACT_FIXES = 2;

// A verdict's chip: yes reads as good news, no as the quiet one, never red,
// since a persona the post is not for saying no is information, not an error.
const VERDICT_TONE = Object.freeze({
  yes:   "bg-success/10 text-success",
  maybe: "bg-warning/10 text-warning",
  no:    "bg-muted text-muted-foreground",
});

/**
 * A post's pre-publish review: the score the agent gave it, the checks the
 * server ran, and what to fix. Advice only — nothing here disables Publish.
 *
 * `assessment` is the backend's PublishAssessment as it stands now (the
 * checks are recomputed on every read; `stale` says the score predates an
 * edit). Unscored, it still carries the checks.
 *
 * Props:
 *   - assessment : PublishAssessment
 *   - compact    : the publish dialog's cut — score, failed checks, the two
 *                  weakest fixes
 *   - onReview   : ask the agent for a (re)review; absent where no session is
 *                  open, and the panel says how to get one instead
 */
export default function PublishReviewPanel({ assessment, compact = false, onReview }) {
  const { t, i18n } = useLingui();
  const headingId = useId();
  if (!assessment) return null;

  const scored = isScored(assessment);
  const checks = assessment.checks || [];
  const failed = failedChecks(assessment);
  const total = checks.length;
  const passed = total - failed.length;
  const markers = compact ? weakestMarkers(assessment, COMPACT_FIXES) : assessment.markers || [];
  const band = BAND_META[assessment.band];
  const scoredAgo = assessment.scored_at ? relativeTime(assessment.scored_at, { locale: i18n.locale }) : "";

  const list = new Intl.ListFormat(i18n.locale, { type: "conjunction" });
  function where(offenders) {
    return list.format(
      (offenders || []).map((id) => {
        const n = slideNumber(id);
        if (n != null) return t`slide ${n}`;
        const r = replyNumber(id);
        if (r != null) return t`reply ${r}`;
        return id === "caption" ? t`the caption` : id;
      }),
    );
  }
  function sentence(check) {
    const at = where(check.offenders);
    switch (check.id) {
      case SanityCheckId.SLIDES_HAVE_IMAGES: return t`No image on ${at}`;
      case SanityCheckId.IMAGES_FRESH: return t`Image older than its prompt on ${at}`;
      case SanityCheckId.SLIDES_HAVE_HEADLINES: return t`No headline on ${at}`;
      case SanityCheckId.CAPTION_PRESENT: return t`No caption`;
      case SanityCheckId.CAPTION_LENGTH: return t`Longer than the platform allows: ${at}`;
      case SanityCheckId.NO_PLACEHOLDER_TEXT: return t`Placeholder text on ${at}`;
      case SanityCheckId.HASHTAGS_PRESENT: return t`No hashtags`;
      case SanityCheckId.HASHTAGS_UNIQUE: return t`Repeated hashtags: ${at}`;
      default: return check.id;
    }
  }

  return (
    <section aria-labelledby={headingId} className="space-y-4 rounded-2xl border border-border bg-card p-4">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={headingId} className="text-sm font-semibold"><Trans>Pre-publish review</Trans></h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {scored && scoredAgo
              ? <Trans>Scored {scoredAgo} · advice only, publish either way</Trans>
              : <Trans>Advice only, publish either way</Trans>}
          </p>
        </div>
        {onReview && (
          <Button size="sm" variant="outline" onClick={onReview}>
            <RefreshCw aria-hidden="true" />
            {scored ? <Trans>Review again</Trans> : <Trans>Review</Trans>}
          </Button>
        )}
      </header>

      {scored ? (
        <div className="space-y-1.5">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-semibold leading-none tabular-nums">{assessment.overall}</span>
            <span className="text-xs text-muted-foreground">/ 100</span>
            {band && <Badge variant={band.badgeVariant}>{i18n._(band.label)}</Badge>}
          </div>
          {assessment.stale && (
            <p className="flex items-center gap-1.5 text-xs text-warning">
              <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />
              <Trans>The post changed after this score.</Trans>
            </p>
          )}
        </div>
      ) : (
        !onReview && (
          <p className="text-sm">
            <Trans>Not scored yet. Revise with Duct and ask for a review to get one.</Trans>
          </p>
        )
      )}

      <div className="space-y-1.5">
        {failed.length === 0 ? (
          <p className="flex items-center gap-1.5 text-xs text-success">
            <CheckCircle2 className="size-3.5 shrink-0" aria-hidden="true" />
            <Trans>All {total} checks pass</Trans>
          </p>
        ) : (
          <>
            <p className="text-xs font-medium text-muted-foreground">
              <Trans>{passed} of {total} checks pass</Trans>
            </p>
            <ul className="space-y-1">
              {failed.map((c) => (
                <li key={c.id} className="flex items-start gap-1.5 text-xs">
                  {c.severity === "soft"
                    ? <TriangleAlert className="mt-px size-3.5 shrink-0 text-warning" aria-hidden="true" />
                    : <CircleX className="mt-px size-3.5 shrink-0 text-destructive" aria-hidden="true" />}
                  <span>{sentence(c)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {scored && markers.length > 0 && (
        <div className="space-y-2">
          {compact && (
            <p className="text-xs font-medium text-muted-foreground"><Trans>Biggest fixes</Trans></p>
          )}
          <ul className="space-y-2.5">
            {markers.map((m) => {
              const label = MARKER_LABELS[m.id] ? i18n._(MARKER_LABELS[m.id]) : m.id;
              return (
                <li key={m.id} className="space-y-1">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="w-28 shrink-0 truncate font-medium">{label}</span>
                    <Progress value={m.score} className="h-1.5 flex-1" aria-label={t`${label} score`} />
                    <span className="w-7 shrink-0 text-right tabular-nums">{m.score}</span>
                  </div>
                  {(m.fix || m.verdict) && (
                    <p className="text-xs text-muted-foreground">{m.fix || m.verdict}</p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {!compact && scored && (assessment.personas || []).length > 0 && (
        <AudiencePanel assessment={assessment} />
      )}

      {!compact && scored && assessment.notes && (
        <p className="border-t border-border/60 pt-3 text-xs text-muted-foreground">{assessment.notes}</p>
      )}
    </section>
  );
}

/**
 * The audience panel: the brand's personas role-played on this post, with
 * how far to trust them said first. A twin's yes on one post leans kind and
 * looks like every other twin's, so the chips show only once the panel has
 * ranked the brand's own past posts better than a coin (panel_check), and a
 * panel that reacts exactly like "anyone scrolling" says so.
 */
function AudiencePanel({ assessment }) {
  const { t, i18n } = useLingui();
  const trusted = panelTrusted(assessment);
  const hooks = assessment.hooks || [];
  const votes = hookVotes(assessment);
  const voters = (assessment.personas || []).length;
  const rows = [
    ...(assessment.baseline ? [{ ...assessment.baseline, baseline: true }] : []),
    ...assessment.personas,
  ];
  function hookName(i) {
    return HOOK_LABELS[i] ? i18n._(HOOK_LABELS[i]) : "";
  }

  return (
    <div className="space-y-3 border-t border-border/60 pt-3">
      <div className="space-y-1">
        <h3 className="text-xs font-semibold"><Trans>How your audience reacts</Trans></h3>
        <PanelTrust check={assessment.panel_check} />
      </div>

      {hooks.length > 1 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground"><Trans>Openings they compared</Trans></p>
          <ol className="space-y-1.5">
            {hooks.map((hook, i) => {
              const top = votes[i] > 0 && votes[i] === Math.max(...votes);
              const label = hookName(i);
              const count = votes[i];
              return (
                <li
                  key={i}
                  className={`rounded-lg border px-2.5 py-1.5 text-xs ${top ? "border-primary/40 bg-primary/5" : "border-border"}`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-medium">{label}</span>
                    <span className="shrink-0 text-2xs text-muted-foreground tabular-nums">
                      {t`${count} of ${voters} would stop`}
                    </span>
                  </div>
                  <p className="mt-0.5 leading-relaxed">{hook}</p>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {panelEchoesBaseline(assessment) && (
        <p className="flex items-start gap-1.5 text-xs text-warning">
          <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <Trans>Your personas react just like anyone would, so this says little about your audience. Add lines they really said in Brand settings to tell them apart.</Trans>
        </p>
      )}

      <ul className="space-y-3">
        {rows.map((r) => {
          const scrollPast = r.scroll_past;
          const picked = hooks.length > 1 && Number.isInteger(r.pick) ? hookName(r.pick) : "";
          return (
            <li key={r.baseline ? "baseline" : r.persona} className={`space-y-1 ${r.baseline ? "text-muted-foreground" : ""}`}>
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <span className={`text-xs ${r.baseline ? "font-medium" : "font-semibold"}`}>
                  {r.baseline ? <Trans>Anyone scrolling</Trans> : r.persona}
                </span>
                {trusted && !r.baseline && (
                  <span className="flex flex-wrap gap-1">
                    {PERSONA_ACTIONS.map(({ key, label }) => {
                      const meta = VERDICT_META[r[key]];
                      if (!meta) return null;
                      const action = i18n._(label);
                      const verdict = i18n._(meta.label);
                      return (
                        <span key={key} className={`rounded-full px-2 py-0.5 text-2xs font-medium ${VERDICT_TONE[meta.tone]}`}>
                          {t`${action}: ${verdict}`}
                        </span>
                      );
                    })}
                  </span>
                )}
              </div>
              {scrollPast && (
                <p className="text-xs text-muted-foreground">
                  <Trans>Would scroll past: {scrollPast}</Trans>
                </p>
              )}
              <p className="text-xs leading-relaxed">“{r.reaction}”</p>
              {picked && <p className="text-xs text-muted-foreground">{t`Stops for: ${picked}`}</p>}
              {!r.baseline && r.fix && <p className="text-xs text-muted-foreground">{r.fix}</p>}
            </li>
          );
        })}
      </ul>

      <p className="text-xs text-muted-foreground">
        <Trans>Duct role-plays the personas in your Brand settings. Advice, not a measurement.</Trans>
      </p>
    </div>
  );
}

/** How far to trust the panel, from how it ranked the brand's past posts. */
function PanelTrust({ check }) {
  const { i18n } = useLingui();
  if (!check) {
    return (
      <p className="text-xs text-muted-foreground">
        <Trans>Not tested on your results yet: that needs five published posts with numbers. Read this as a guess.</Trans>
      </p>
    );
  }
  const metric = PANEL_METRIC_LABELS[check.metric] ? i18n._(PANEL_METRIC_LABELS[check.metric]) : check.metric;
  const { posts, agreed, pairs } = check;
  if (check.fit === PanelFit.TRACKS) {
    return (
      <p className="flex items-start gap-1.5 text-xs text-success">
        <CheckCircle2 className="mt-px size-3.5 shrink-0" aria-hidden="true" />
        <span>
          <Trans>Tested on your last {posts} posts: it ranked them close to their real {metric} ({agreed} of {pairs} pairs right). A lean, not a promise.</Trans>
        </span>
      </p>
    );
  }
  if (check.fit === PanelFit.LOOSE) {
    return (
      <p className="text-xs text-muted-foreground">
        <Trans>Tested on your last {posts} posts: a loose match with their real {metric} ({agreed} of {pairs} pairs right). Read this as a lean.</Trans>
      </p>
    );
  }
  return (
    <p className="flex items-start gap-1.5 text-xs text-warning">
      <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
      <span>
        <Trans>Tested on your last {posts} posts: no better than a coin at ranking their real {metric}. Read this as a guess.</Trans>
      </span>
    </p>
  );
}
