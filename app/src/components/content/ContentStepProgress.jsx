"use client";

import { STEP_LABELS, ContentStep } from "../../lib/contentEvents";
import { StepStatus } from "../../lib/agentSteps";
import { mediaUrl } from "../../lib/contentApi";
import { fmtCount } from "../../lib/contentMetrics";
import AgentStepTimeline from "../workspace/AgentStepTimeline";

/**
 * The content/clone pipeline step list above the chat. Renders through the
 * shared <AgentStepTimeline> (same primitive the audit agent uses) so the rich
 * behaviour — status icons, expand/collapse, per-step detail panels — stays in
 * one place. Clone ingest steps carry structured `payload` and get dedicated
 * detail renderers (reference preview, video understanding, why-it-worked);
 * everything else falls back to its `summary` text. Sub-agent dispatches
 * (step_id "dispatch_subagent:<name>") are grouped under a "Sub-agents" heading.
 */

// Clone ingest step ids (backend emits `clone_<stage>`; see runner _on_step).
const CloneStep = Object.freeze({
  SCRAPING:  "clone_scraping",
  MEDIA:     "clone_media",
  WATCHING:  "clone_watching",
  ANALYZING: "clone_analyzing",
});

const DETAIL_COMPONENTS = {
  [CloneStep.SCRAPING]:  ScrapePreview,
  [CloneStep.WATCHING]:  VideoUnderstanding,
  [CloneStep.ANALYZING]: DiagnosticDetail,
};

export default function ContentStepProgress({ steps }) {
  if (!steps || steps.length === 0) return null;

  const isDispatch = (s) => s.step_id?.startsWith(`${ContentStep.DISPATCH_SUBAGENT}:`);
  const pipelineSteps = steps.filter((s) => !isDispatch(s));
  const dispatchSteps = steps.filter(isDispatch).map(withHumanLabel);

  return (
    <div className="space-y-3 border-b border-border/60 px-4 py-3">
      {pipelineSteps.length > 0 && (
        <AgentStepTimeline
          steps={pipelineSteps}
          labels={STEP_LABELS}
          detailComponents={DETAIL_COMPONENTS}
          renderMeta={renderMeta}
          size="xs"
          className="space-y-1.5"
        />
      )}

      {dispatchSteps.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Sub-agents</p>
          <AgentStepTimeline steps={dispatchSteps} size="xs" className="space-y-1.5" />
        </div>
      )}
    </div>
  );
}

function humanize(name) {
  return String(name || "agent").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Give a dispatch step a readable label when the backend didn't send one.
function withHumanLabel(s) {
  if (s.label) return s;
  return { ...s, label: humanize(s.step_id?.split(":", 2)[1]) };
}

// Inline right-of-row meta: the media step shows how many assets we saved
// (mirrors the audit agent surfacing crawl/competitor counts on the row).
function renderMeta(step) {
  const p = step.payload;
  const isDone = step.status === StepStatus.SUCCESS || step.status === StepStatus.ERROR;
  if (step.step_id === CloneStep.MEDIA && isDone && p) {
    const n = (p.cover ? 1 : 0) + (Number(p.slides) || 0);
    return (
      <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
        {n} image{n !== 1 ? "s" : ""}{p.video ? " + video" : ""}
      </span>
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Clone-step detail panels
// ---------------------------------------------------------------------------

function statChips(p) {
  return [
    ["views", p.views], ["likes", p.likes], ["comments", p.comments],
    ["shares", p.shares], ["saves", p.saves],
  ].filter(([, v]) => typeof v === "number" && v > 0);
}

// The "tiny post preview" — same idea as the paste-a-URL dialog: cover + handle
// + caption + the engagement counts the clone is modeling.
function ScrapePreview({ payload }) {
  const p = payload || {};
  const chips = statChips(p);
  return (
    <div className="flex gap-3">
      {p.thumbnail && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={mediaUrl(p.thumbnail)}
          alt=""
          loading="lazy"
          className="h-24 w-[3.4rem] shrink-0 rounded-md border border-border/50 object-cover"
        />
      )}
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-center gap-1.5">
          {p.post_type && (
            <span className="rounded bg-muted px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {p.post_type}
            </span>
          )}
          {p.author && <span className="truncate text-[11px] text-foreground/80">@{p.author}</span>}
        </div>
        {p.caption && (
          <p className="line-clamp-3 text-[11px] leading-relaxed text-muted-foreground">{p.caption}</p>
        )}
        {chips.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {chips.map(([k, v]) => (
              <span key={k} className="rounded bg-muted/60 px-1.5 py-px text-[10px] text-muted-foreground">
                {fmtCount(v)} {k}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Gemini's frame-by-frame deconstruction of the reference clip — "show the
// learning" so the user sees what the agent actually watched.
function VideoUnderstanding({ payload }) {
  const p = payload || {};
  if (!p.analyzed || !p.analysis) {
    return <p className="text-[11px] italic text-muted-foreground">Couldn't read the clip — used the cover + metadata instead.</p>;
  }
  return (
    <p className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded bg-muted/50 p-2 text-[11px] leading-relaxed text-muted-foreground">
      {p.analysis}
    </p>
  );
}

// Why the reference won — the dominant lever + the public engagement counts.
function DiagnosticDetail({ payload }) {
  const p = payload || {};
  const chips = statChips(p);
  if (!p.lever && chips.length === 0) {
    return <p className="text-[11px] italic text-muted-foreground">No engagement signal was available for this reference.</p>;
  }
  return (
    <div className="space-y-1.5">
      {p.lever && (
        <p className="text-[11px] text-foreground">
          <span className="font-medium uppercase tracking-wide text-violet-600 dark:text-violet-400">{p.lever}</span>
          {p.summary ? ` — ${p.summary}` : ""}
        </p>
      )}
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {chips.map(([k, v]) => (
            <span key={k} className="rounded bg-muted/60 px-1.5 py-px text-[10px] text-muted-foreground">
              {fmtCount(v)} {k}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
