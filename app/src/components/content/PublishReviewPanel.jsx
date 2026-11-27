"use client";

import { useId, useState } from "react";
import {
  Bookmark,
  CheckCircle2,
  ChevronDown,
  CircleX,
  Hand,
  MessageCircle,
  RefreshCw,
  Send,
  Sparkles,
  TriangleAlert,
  UserRound,
  Wand2,
} from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
  scoreTone,
  slideNumber,
  weakestMarkers,
} from "@/lib/contentReview";
import { relativeTime } from "@/lib/format";

// The fixes read first: the two weakest markers. Six fixes at once was the
// wall of text the review used to be (2026-11-27).
const FIRST_FIXES = 2;

const TONE_TEXT = { good: "text-success", mixed: "text-warning", weak: "text-destructive" };
const TONE_BAR = { good: "bg-success", mixed: "bg-warning", weak: "bg-destructive" };

// One glyph per action, in the order a feed meets a post.
const ACTION_ICON = { stop: Hand, comment: MessageCircle, save: Bookmark, share: Send, click: UserRound };

/**
 * A post's pre-publish review, built to be scanned: the score as a ring, the
 * two fixes worth doing first (each one tap from done), the six markers as
 * tiles that open on demand, and the audience as faces and dots rather than
 * paragraphs. Advice only — nothing here disables Publish.
 *
 * `assessment` is the backend's PublishAssessment as it stands now (checks
 * recomputed on every read; `stale` says the score predates an edit).
 *
 * Props:
 *   - assessment : PublishAssessment
 *   - compact    : the publish dialog's cut — score and failed checks
 *   - onReview   : ask the agent for a (re)review; absent with no session
 *   - onFix      : send the agent one instruction (a fix, an opening to use);
 *                  absent with no session, and the buttons are not drawn
 */
export default function PublishReviewPanel({ assessment, compact = false, onReview, onFix }) {
  const { i18n } = useLingui();
  const headingId = useId();
  if (!assessment) return null;

  const scored = isScored(assessment);
  const band = BAND_META[assessment.band];
  const scoredAgo = assessment.scored_at ? relativeTime(assessment.scored_at, { locale: i18n.locale }) : "";

  return (
    <Card size="sm" role="region" aria-labelledby={headingId} className="@container">
      <header className="flex flex-wrap items-start gap-4">
        {scored && <ScoreRing score={assessment.overall} size={compact ? 52 : 72} />}
        {/* basis-48: in a narrow pane the button wraps under the words
            rather than crushing them to a word a line. */}
        <div className="min-w-0 flex-1 basis-48 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id={headingId} className="text-sm font-semibold"><Trans>Pre-publish review</Trans></h2>
            {scored && band && <Badge variant={band.badgeVariant}>{i18n._(band.label)}</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            {scored && scoredAgo
              ? <Trans>Scored {scoredAgo} · advice only, publish either way</Trans>
              : <Trans>Advice only, publish either way</Trans>}
          </p>
          {scored && !compact && assessment.notes && <p className="text-sm leading-snug">{assessment.notes}</p>}
          {scored && assessment.stale && (
            <p className="flex items-center gap-1.5 text-xs text-warning">
              <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />
              <Trans>The post changed after this score.</Trans>
            </p>
          )}
        </div>
        {onReview && !compact && (
          <Button size="sm" variant="outline" onClick={onReview}>
            <RefreshCw aria-hidden="true" />
            {scored ? <Trans>Review again</Trans> : <Trans>Review</Trans>}
          </Button>
        )}
      </header>

      {!scored && !onReview && (
        <p className="text-sm"><Trans>Not scored yet. Revise with Duct and ask for a review to get one.</Trans></p>
      )}

      {/* The dialog's cut is the score and the checks: the fixes live on the
          Review tab, and four paragraphs of advice buried the Post button. */}
      {scored && !compact && <FirstFixes assessment={assessment} onFix={onFix} />}

      <Checks assessment={assessment} />

      {scored && !compact && <MarkerTiles assessment={assessment} />}

      {scored && !compact && (assessment.personas || []).length > 0 && (
        <AudiencePanel assessment={assessment} onFix={onFix} />
      )}
    </Card>
  );
}

/** The score as a ring filled to it, coloured by how good it is. */
function ScoreRing({ score, size }) {
  const { t } = useLingui();
  const stroke = size > 60 ? 7 : 5;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const value = Math.max(0, Math.min(100, score || 0));
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={t`Score ${value} out of 100`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-muted" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={circumference * (1 - value / 100)}
          className={`stroke-current ${TONE_TEXT[scoreTone(value)]}`}
        />
      </svg>
      <span className={`absolute inset-0 flex items-center justify-center font-semibold tabular-nums ${size > 60 ? "text-2xl" : "text-base"}`}>
        {value}
      </span>
    </div>
  );
}

/** The two fixes worth doing first, each a tap from done in a live session. */
function FirstFixes({ assessment, onFix }) {
  const { i18n } = useLingui();
  const fixes = weakestMarkers(assessment, FIRST_FIXES).filter((m) => m.fix || m.verdict);
  if (!fixes.length) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground"><Trans>Fix first</Trans></p>
      <ul className="grid gap-2 @lg:grid-cols-2">
        {fixes.map((m) => {
          const label = MARKER_LABELS[m.id] ? i18n._(MARKER_LABELS[m.id]) : m.id;
          const tone = scoreTone(m.score);
          return (
            <li key={m.id}>
              <Card variant="quiet" size="sm" className="h-full gap-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{label}</span>
                  <span className={`text-sm font-semibold tabular-nums ${TONE_TEXT[tone]}`}>{m.score}</span>
                </div>
                <p className="text-sm leading-snug text-muted-foreground">{m.fix || m.verdict}</p>
                {onFix && m.fix && (
                  <Button
                    size="sm" variant="outline" className="mt-auto w-fit"
                    onClick={() => onFix(`From the review, fix the ${m.id.replaceAll("_", " ")}: ${m.fix} Change only what this needs.`)}
                  >
                    <Wand2 aria-hidden="true" /> <Trans>Fix this</Trans>
                  </Button>
                )}
              </Card>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** The server's checks: one line when all pass, the failures when not. */
function Checks({ assessment }) {
  const { t, i18n } = useLingui();
  const checks = assessment.checks || [];
  const failed = failedChecks(assessment);
  if (!checks.length) return null;
  if (!failed.length) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-success">
        <CheckCircle2 className="size-3.5 shrink-0" aria-hidden="true" />
        <Trans>All {checks.length} checks pass</Trans>
      </p>
    );
  }
  const list = new Intl.ListFormat(i18n.locale, { type: "conjunction" });
  const where = (offenders) =>
    list.format(
      (offenders || []).map((id) => {
        const n = slideNumber(id);
        if (n != null) return t`slide ${n}`;
        const r = replyNumber(id);
        if (r != null) return t`reply ${r}`;
        return id === "caption" ? t`the caption` : id;
      }),
    );
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
    <ul className="flex flex-wrap gap-1.5">
      {failed.map((c) => (
        <li key={c.id}>
          <Badge variant={c.severity === "soft" ? "warning" : "destructive"} className="h-auto whitespace-normal py-1">
            {c.severity === "soft" ? <TriangleAlert aria-hidden="true" /> : <CircleX aria-hidden="true" />}
            {sentence(c)}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

/** Six tiles, one per marker: a number and a bar at a glance, the verdict
 *  and its fix when a tile is opened. */
function MarkerTiles({ assessment }) {
  const { i18n } = useLingui();
  const [open, setOpen] = useState("");
  const markers = assessment.markers || [];
  const opened = markers.find((m) => m.id === open);
  if (!markers.length) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground"><Trans>Scores</Trans></p>
      <div className="grid grid-cols-2 gap-2 @md:grid-cols-3">
        {markers.map((m) => {
          const label = MARKER_LABELS[m.id] ? i18n._(MARKER_LABELS[m.id]) : m.id;
          const tone = scoreTone(m.score);
          const active = m.id === open;
          return (
            <button
              key={m.id}
              type="button"
              aria-expanded={active}
              onClick={() => setOpen(active ? "" : m.id)}
              className={`flex min-h-11 flex-col gap-1.5 rounded-lg px-3 py-2 text-left transition-colors ${active ? "bg-accent" : "bg-muted/60 hover:bg-muted"}`}
            >
              <span className="flex w-full items-baseline justify-between gap-2">
                <span className="truncate text-xs font-medium">{label}</span>
                <span className={`text-sm font-semibold tabular-nums ${TONE_TEXT[tone]}`}>{m.score}</span>
              </span>
              <span className="h-1 w-full overflow-hidden rounded-full bg-background/60" aria-hidden="true">
                <span className={`block h-full rounded-full ${TONE_BAR[tone]}`} style={{ width: `${m.score}%` }} />
              </span>
            </button>
          );
        })}
      </div>
      {opened && (
        <div className="space-y-1 rounded-lg bg-muted/40 px-3 py-2 text-sm">
          {opened.verdict && <p className="font-medium">{opened.verdict}</p>}
          {opened.why && <p className="text-muted-foreground">{opened.why}</p>}
          {opened.fix && (
            <p><span className="font-medium"><Trans>Fix:</Trans></span> {opened.fix}</p>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The audience panel: the brand's personas role-played on this post, with
 * how far to trust them said first. A twin's yes on one post leans kind and
 * looks like every other twin's, so the yes/maybe/no grid shows only once
 * the panel has ranked the brand's own past posts better than a coin
 * (panel_check); untested, it is faces, openings and words.
 */
function AudiencePanel({ assessment, onFix }) {
  const trusted = panelTrusted(assessment);
  const people = assessment.personas || [];
  return (
    <div className="space-y-4 border-t border-border/60 pt-4">
      <div className="space-y-1">
        <h3 className="text-sm font-semibold"><Trans>How your audience reacts</Trans></h3>
        <PanelTrust check={assessment.panel_check} />
      </div>

      <Openings assessment={assessment} onFix={onFix} />

      {trusted && <VerdictGrid people={people} />}

      {panelEchoesBaseline(assessment) && (
        <p className="flex items-start gap-1.5 text-xs text-warning">
          <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <Trans>Your personas react just like anyone would, so this says little about your audience. Add lines they really said in Brand settings to tell them apart.</Trans>
        </p>
      )}

      <People assessment={assessment} />
    </div>
  );
}

/** The openings the panel chose between: votes as dots, the pick marked,
 *  and the pick one tap from slide 1 when it is not the post's own. */
function Openings({ assessment, onFix }) {
  const { t, i18n } = useLingui();
  const hooks = assessment.hooks || [];
  if (hooks.length < 2) return null;
  const votes = hookVotes(assessment);
  const voters = (assessment.personas || []).length;
  const top = Math.max(...votes);
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground"><Trans>Which opening stops them</Trans></p>
      <ol className="space-y-1.5">
        {hooks.map((hook, i) => {
          const label = HOOK_LABELS[i] ? i18n._(HOOK_LABELS[i]) : "";
          const count = votes[i];
          const pick = count > 0 && count === top;
          return (
            <li key={i} className={`flex items-start gap-3 rounded-lg px-3 py-2 ${pick ? "bg-primary/10" : "bg-muted/40"}`}>
              <div className="min-w-0 flex-1 space-y-0.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium text-muted-foreground">{label}</span>
                  {pick && <Badge variant="default"><Sparkles aria-hidden="true" /> <Trans>Audience pick</Trans></Badge>}
                </div>
                <p className="text-sm leading-snug">{hook}</p>
                {pick && i > 0 && onFix && (
                  <Button
                    size="sm" variant="outline" className="mt-1"
                    onClick={() => onFix(`Put the opening the audience picked on slide 1, word for word: "${hook}". Change nothing else.`)}
                  >
                    <Trans>Use this opening</Trans>
                  </Button>
                )}
              </div>
              <span className="flex shrink-0 items-center gap-1 pt-1" role="img" aria-label={t`${count} of ${voters} would stop`}>
                {Array.from({ length: voters }, (_, k) => (
                  <span key={k} className={`size-2 rounded-full ${k < count ? "bg-primary" : "bg-muted-foreground/25"}`} />
                ))}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Who would do what: personas down, the five actions across, a dot each. */
function VerdictGrid({ people }) {
  const { t, i18n } = useLingui();
  const shown = PERSONA_ACTIONS.filter(({ key }) => people.some((r) => VERDICT_META[r[key]]));
  return (
    <div className="space-y-2">
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="w-full text-left font-normal text-muted-foreground"><span className="sr-only"><Trans>Persona</Trans></span></th>
            {shown.map(({ key, label }) => {
              const Icon = ACTION_ICON[key];
              const name = i18n._(label);
              return (
                <th key={key} className="px-1.5 pb-1.5 font-normal text-muted-foreground" title={name}>
                  <Icon className="mx-auto size-3.5" aria-hidden="true" />
                  <span className="sr-only">{name}</span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {people.map((r) => (
            <tr key={r.persona} className="border-t border-border/50">
              <td className="max-w-0 truncate py-1.5 pr-2">{personaName(r.persona)}</td>
              {shown.map(({ key, label }) => {
                const meta = VERDICT_META[r[key]];
                const verdict = meta ? i18n._(meta.label) : t`Not asked`;
                return (
                  <td key={key} className="px-1.5 py-1.5 text-center" title={`${i18n._(label)}: ${verdict}`}>
                    <VerdictDot tone={meta?.tone} />
                    <span className="sr-only">{`${i18n._(label)}: ${verdict}`}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-muted-foreground" aria-hidden="true">
        {shown.map(({ key, label }) => {
          const Icon = ACTION_ICON[key];
          return (
            <span key={key} className="inline-flex items-center gap-1"><Icon className="size-3" /> {i18n._(label)}</span>
          );
        })}
      </p>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-muted-foreground" aria-hidden="true">
        <span className="inline-flex items-center gap-1"><VerdictDot tone="yes" /> <Trans>Yes</Trans></span>
        <span className="inline-flex items-center gap-1"><VerdictDot tone="maybe" /> <Trans>Maybe</Trans></span>
        <span className="inline-flex items-center gap-1"><VerdictDot tone="no" /> <Trans>No</Trans></span>
      </p>
    </div>
  );
}

function VerdictDot({ tone }) {
  const cls = tone === "yes"
    ? "bg-success"
    : tone === "maybe"
      ? "bg-warning"
      : tone === "no"
        ? "border border-muted-foreground/50"
        : "bg-muted";
  return <span className={`mx-auto block size-2.5 rounded-full ${cls}`} aria-hidden="true" />;
}

/** Each persona as a face and a name; their words one tap away. */
function People({ assessment }) {
  const { t, i18n } = useLingui();
  const [open, setOpen] = useState("");
  const hooks = assessment.hooks || [];
  const rows = [
    ...(assessment.baseline ? [{ ...assessment.baseline, baseline: true }] : []),
    ...(assessment.personas || []),
  ];
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground"><Trans>In their words</Trans></p>
      <ul className="divide-y divide-border/50">
        {rows.map((r) => {
          const key = r.baseline ? "baseline" : r.persona;
          const active = open === key;
          const name = r.baseline ? t`Anyone scrolling` : personaName(r.persona);
          const tagline = r.baseline ? "" : personaTagline(r.persona);
          const picked = hooks.length > 1 && Number.isInteger(r.pick) && HOOK_LABELS[r.pick] ? i18n._(HOOK_LABELS[r.pick]) : "";
          return (
            <li key={key}>
              <button
                type="button"
                aria-expanded={active}
                onClick={() => setOpen(active ? "" : key)}
                className="flex min-h-11 w-full items-center gap-3 py-2 text-left"
              >
                <span
                  className={`flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${r.baseline ? "bg-muted text-muted-foreground" : "bg-primary/15 text-brand"}`}
                  aria-hidden="true"
                >
                  {r.baseline ? "?" : name.charAt(0).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{name}</span>
                  {(tagline || picked) && (
                    <span className="block truncate text-xs text-muted-foreground">
                      {[tagline, picked && t`stops for ${picked}`].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </span>
                <ChevronDown className={`size-4 shrink-0 text-muted-foreground transition-transform ${active ? "rotate-180" : ""}`} aria-hidden="true" />
              </button>
              {active && (
                <div className="space-y-1.5 pb-3 pl-11 text-sm">
                  <p className="leading-snug">“{r.reaction}”</p>
                  {r.scroll_past && (
                    <p className="text-muted-foreground"><Trans>Would scroll past: {r.scroll_past}</Trans></p>
                  )}
                  {!r.baseline && r.fix && (
                    <p><span className="font-medium"><Trans>Would win them:</Trans></span> {r.fix}</p>
                  )}
                </div>
              )}
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

// "Maya, 29, Toronto: three apps, three seasons" → "Maya, 29, Toronto" and
// "three apps, three seasons": the name on the row, the rest under it.
function personaName(label) {
  const text = String(label || "");
  const at = text.indexOf(":");
  return at > 0 ? text.slice(0, at).trim() : text;
}

function personaTagline(label) {
  const text = String(label || "");
  const at = text.indexOf(":");
  return at > 0 ? text.slice(at + 1).trim() : "";
}

/** How far to trust the panel, from how it ranked the brand's past posts. */
function PanelTrust({ check }) {
  const { i18n } = useLingui();
  if (!check) {
    return (
      <p className="text-xs text-muted-foreground">
        <Trans>A guess until it has been tested on five of your published posts.</Trans>
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
