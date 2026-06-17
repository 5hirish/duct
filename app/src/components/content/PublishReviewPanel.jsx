"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, ChevronDown, Download, RefreshCw, Send, Sparkles, X } from "lucide-react";

/**
 * Pre-publish review panel — additive + collapsible. Renders the PUBLISH_ASSESSMENT
 * payload from the review_post sub-agent: an overall score + band, the deterministic
 * completeness (sanity) checks, and the six subjective content markers (each with a
 * score bar + the single most valuable fix). Never replaces the slides/copy preview;
 * it slots in beside them in the viewport body.
 *
 * Advisory only — both actions stay available regardless of score:
 *   onImprove() — hand the prioritized fixes to the agent in the same session
 *   onPublish() — proceed to the publish flow
 */

const BAND_META = {
  "Strong":     { ring: "#10b981", text: "text-emerald-600 dark:text-emerald-400", soft: "bg-emerald-500/10" },
  "Good":       { ring: "#3b82f6", text: "text-blue-600 dark:text-blue-400",       soft: "bg-blue-500/10" },
  "Needs work": { ring: "#f59e0b", text: "text-amber-600 dark:text-amber-400",     soft: "bg-amber-500/10" },
  "Not ready":  { ring: "#ef4444", text: "text-red-600 dark:text-red-400",         soft: "bg-red-500/10" },
};

function bandMeta(band) { return BAND_META[band] || BAND_META["Needs work"]; }

function ScoreRing({ value, color, size = 52 }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value || 0));
  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="4"
        stroke="currentColor" className="text-border/40" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="4"
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)}
        style={{ transition: "stroke-dashoffset .8s ease" }} />
    </svg>
  );
}

function MarkerRow({ m }) {
  const score = m.score ?? 0;
  const bar = score >= 70 ? "bg-emerald-500" : score >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="font-medium">{m.label || m.id}</span>
        <span className="tabular-nums text-muted-foreground">{score}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full ${bar}`} style={{ width: `${score}%`, transition: "width .6s ease" }} />
      </div>
      {(m.verdict || m.fix) && (
        <p className="text-[11px] leading-snug text-muted-foreground">
          {m.verdict}
          {m.fix ? <> · <span className="font-medium text-foreground/80">Fix:</span> {m.fix}</> : null}
        </p>
      )}
    </div>
  );
}

export default function PublishReviewPanel({ assessment, reviewing = false, stale = false, published = false, onImprove, onRerun, onPublish, onDownload }) {
  const [open, setOpen] = useState(true);
  // Re-open whenever a fresh assessment lands.
  useEffect(() => { if (assessment) setOpen(true); }, [assessment?.generated_at]);

  if (!assessment) {
    if (!reviewing) return null;
    return (
      <section className="rounded-2xl border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-sm">
          <span className="size-4 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
          <span className="font-medium">Reviewing before publish…</span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Scoring the hook, momentum, save-worthiness, visuals and CTA — watch the chat for progress.
        </p>
      </section>
    );
  }

  const a = assessment;
  const bm = bandMeta(a.band);
  const sanity = a.sanity || [];
  const markers = a.markers || [];

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <div className="relative flex items-center justify-center">
          <ScoreRing value={a.overall} color={bm.ring} />
          <span className="absolute text-sm font-semibold tabular-nums">{a.overall}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{published ? "Content review" : "Pre-publish review"}</span>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${bm.soft} ${bm.text}`}>{a.band}</span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Content {a.content_score}/100 · {a.sanity_passed}/{a.sanity_total} checks passed
            {reviewing ? " · refreshing…" : stale ? " · out of date" : ""}
          </p>
        </div>
        <ChevronDown className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="space-y-4 border-t border-border/60 px-4 py-3">
          {stale && (
            <div className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              The draft changed since this review — rerun it for an up-to-date score.
            </div>
          )}

          {a.notes && <p className="text-xs italic text-muted-foreground">{a.notes}</p>}

          <div className="space-y-1.5">
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Completeness</h4>
            {sanity.map((c) => {
              const Icon = c.passed ? Check : c.severity === "soft" ? AlertTriangle : X;
              const color = c.passed
                ? "text-emerald-500"
                : c.severity === "soft" ? "text-amber-500" : "text-red-500";
              return (
                <div key={c.id} className="flex items-start gap-2 text-xs">
                  <Icon className={`mt-0.5 size-3.5 shrink-0 ${color}`} />
                  <span className={c.passed ? "text-muted-foreground" : "text-foreground"}>
                    {c.label}
                    {!c.passed && c.detail ? <span className="text-muted-foreground"> — {c.detail}</span> : null}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="space-y-2.5">
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Content quality</h4>
            {markers.map((m) => <MarkerRow key={m.id} m={m} />)}
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            {published ? (
              // Already live: this is a read-only record of the review — the only
              // action is downloading the slides (to repost / archive).
              onDownload && (
                <button
                  type="button"
                  onClick={onDownload}
                  className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-semibold hover:bg-muted/50"
                >
                  <Download className="size-3.5" /> Download slides
                </button>
              )
            ) : (
              <>
                {/* Once the draft has changed since this review, the useful next step
                    is to re-score it — so the primary action flips to "Rerun review".
                    Otherwise it's "Improve with Duct" (hand the fixes to the agent). */}
                {stale && onRerun ? (
                  <button
                    type="button"
                    onClick={onRerun}
                    disabled={reviewing}
                    className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    <RefreshCw className="size-3.5" /> {reviewing ? "Reviewing…" : "Rerun review"}
                  </button>
                ) : onImprove ? (
                  <button
                    type="button"
                    onClick={onImprove}
                    disabled={reviewing}
                    className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    <Sparkles className="size-3.5" /> Improve with Duct
                  </button>
                ) : null}
                {onPublish && (
                  <button
                    type="button"
                    onClick={onPublish}
                    className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-semibold hover:bg-muted/50"
                  >
                    <Send className="size-3.5" /> Publish now
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
