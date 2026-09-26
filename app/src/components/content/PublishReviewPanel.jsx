"use client";

import { useId } from "react";
import { CheckCircle2, CircleX, RefreshCw, TriangleAlert } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  BAND_META,
  MARKER_LABELS,
  SanityCheckId,
  failedChecks,
  isScored,
  slideNumber,
  weakestMarkers,
} from "@/lib/contentReview";
import { relativeTime } from "@/lib/format";

// How many fixes the publish dialog shows: the dialog is a last look before
// posting, not the place to read all six.
const COMPACT_FIXES = 2;

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
      case SanityCheckId.CAPTION_LENGTH: return t`Caption is longer than Instagram allows`;
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

      {!compact && scored && assessment.notes && (
        <p className="border-t border-border/60 pt-3 text-xs text-muted-foreground">{assessment.notes}</p>
      )}
    </section>
  );
}
