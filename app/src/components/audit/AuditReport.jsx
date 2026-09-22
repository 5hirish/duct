"use client";

import { useMemo, useRef } from "react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Phase } from "../workspace/agentPhase";
import { AuditStep } from "../../lib/auditEvents";
import { StepStatus } from "../../lib/agentSteps";
import { saveText } from "../../lib/download";
import PipelineProgress from "../PipelineProgress";
import AuditReportV1 from "./AuditReportV1";

// ---------------------------------------------------------------------------
// Version history — pill toggles
// ---------------------------------------------------------------------------

function VersionPills({ versions, selectedId, onSelect }) {
  if (!versions || versions.length === 0) return null;
  const latest = versions[versions.length - 1];
  const active = selectedId ?? latest.version_id;
  const isOld = active !== latest.version_id;

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {[...versions].reverse().map((v) => {
        const id = v.version_id;
        const label = v.label;
        return (
          <button
            key={v.version_id}
            onClick={() => onSelect(v.version_id)}
            className={`rounded-full px-2.5 py-0.5 text-xs transition-colors border whitespace-nowrap ${
              active === v.version_id
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:border-foreground/50 hover:text-foreground"
            }`}
          >
            <Trans>v{id} — {label}</Trans>
          </button>
        );
      })}
      {isOld && (
        <span className="text-xs text-warning font-medium"><Trans>older version</Trans></span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Synthesis progress — shown in the report panel while Duct works
// ---------------------------------------------------------------------------

// Virtual step ID — not emitted by the backend, driven by isStreamingReport prop
const STEP_WRITE_REPORT = "write_report";

// Module-level tables hold message descriptors; SynthesisProgress resolves
// them for the current locale before PipelineProgress sees them.
const STAGE_META = [
  { id: AuditStep.FETCH_SITEMAP,    label: msg`Mapping your site structure`,          virtual: false },
  { id: AuditStep.CRAWL_PAGES,      label: msg`Reading and parsing your pages`,       virtual: false },
  // conditional: enrichment is skipped for the lead-magnet flow (no business
  // context), so only render this stage once the backend actually emits it.
  { id: AuditStep.ENRICHING,        label: msg`Researching competitors`,              virtual: false, conditional: true },
  { id: AuditStep.SYNTHESIZE_AUDIT, label: msg`Scoring signals & building findings`,  virtual: false },
  { id: STEP_WRITE_REPORT,          label: msg`Generating report`,                    virtual: true  },
];

const SYNTHESIS_LINES = [
  msg`Evaluating title tags and meta descriptions…`,
  msg`Checking structured data coverage…`,
  msg`Reviewing Open Graph completeness…`,
  msg`Analysing internal linking patterns…`,
  msg`Measuring E-E-A-T signals…`,
  msg`Scoring each SEO category…`,
  msg`Composing findings and priorities…`,
];

// Right-aligned payload chips, audit-specific (sitemap page counts, competitor
// counts). Everything else (icons, time estimate, progress bar, rotating lines)
// is the shared PipelineProgress.
function AuditStageChip({ step, status }) {
  if (step?.payload?.landing_pages != null) {
    const pages = step.payload.landing_pages;
    const posts = step.payload.blog_posts;
    return (
      <span className="text-xs text-muted-foreground shrink-0">
        <Plural value={pages} one="# page" other="# pages" />
        {posts > 0 && <>, <Plural value={posts} one="# post" other="# posts" /></>}
      </span>
    );
  }
  if (status === StepStatus.SUCCESS && step?.payload?.competitors != null) {
    const competitors = step.payload.competitors.length;
    return (
      <span className="text-xs text-muted-foreground shrink-0">
        <Plural value={competitors} one="# competitor" other="# competitors" />
      </span>
    );
  }
  return null;
}

function auditStageChip(stage, step, status) {
  return <AuditStageChip step={step} status={status} />;
}

function SynthesisProgress({ steps, isStreamingReport = false }) {
  const { t, i18n } = useLingui();
  const stages = useMemo(
    () => STAGE_META.map((stage) => ({ ...stage, label: i18n._(stage.label) })),
    [i18n],
  );
  const lines = useMemo(() => SYNTHESIS_LINES.map((line) => i18n._(line)), [i18n]);
  // Once the model starts adding categories, swap the static time estimate for live
  // "N/9 categories" progress (emitted per AddAuditCategory call by the backend).
  const synthStep = steps?.find((s) => s.step_id === AuditStep.SYNTHESIZE_AUDIT);
  const done = synthStep?.payload?.categories_done;
  const total = synthStep?.payload?.categories_total ?? 9;
  const estimate = done != null
    ? t`${done}/${total} categories`
    : t`~3 min`;
  return (
    <PipelineProgress
      stages={stages}
      steps={steps}
      activeId={AuditStep.SYNTHESIZE_AUDIT}
      writingId={STEP_WRITE_REPORT}
      writing={isStreamingReport}
      lines={lines}
      estimate={estimate}
      buildingLabel={t`Building report`}
      streamingLabel={t`Generating report`}
      streamingSubtitle={t`Writing your report…`}
      idleSubtitle={t`Working on your report…`}
      stageChip={auditStageChip}
    />
  );
}

// ---------------------------------------------------------------------------
// Failed overlay — shown over the report (or alone) on pipeline failure
// ---------------------------------------------------------------------------

// Interrupted report document — lines written, then cut off mid-page
function InterruptedReport() {
  // Rows: true = written (solid line), false = empty (faded dashes), null = break point
  const rows = [true, true, true, true, null, false, false];

  return (
    <div className="relative mx-auto w-[52px]" style={{ height: "66px" }}>
      {/* Page body */}
      <div className="absolute inset-0 rounded border-2 border-border bg-background rounded-tr-none" />

      {/* Folded corner */}
      <div
        className="absolute top-0 right-0 w-[14px] h-[14px] bg-muted border-l-2 border-b-2 border-border"
        style={{ borderBottomLeftRadius: "3px" }}
      />

      {/* Content rows */}
      <div className="absolute inset-x-2 top-[18px] space-y-[5px]">
        {rows.map((filled, i) => {
          if (filled === null) {
            // Break divider — where writing stopped
            return (
              <div key={i} className="flex items-center gap-1 py-[1px]">
                <div className="flex-1 h-px bg-destructive/40" style={{ borderTop: "1px dashed rgba(239,68,68,0.4)" }} />
                <span className="text-2xs text-destructive/60 font-medium shrink-0"><Trans>stopped</Trans></span>
              </div>
            );
          }
          return (
            <div
              key={i}
              className={`h-[3px] rounded-full transition-all ${
                filled
                  ? "bg-foreground/25"
                  : "bg-muted-foreground/10"
              }`}
              style={{ width: filled ? (i % 2 === 0 ? "100%" : "72%") : (i % 2 === 0 ? "55%" : "40%") }}
            />
          );
        })}
      </div>
    </div>
  );
}

function FailedOverlay({ errorMsg, onRetry, hasReport }) {
  return (
    <div
      className={[
        "flex items-center justify-center z-10",
        hasReport
          ? "absolute inset-0 bg-background/85 backdrop-blur-sm"
          : "h-full p-8",
      ].join(" ")}
    >
      <div className="rounded-2xl border border-destructive/20 bg-background/95 shadow-xl p-8 max-w-xs w-full text-center space-y-6">

        {/* Visual */}
        <div className="flex flex-col items-center gap-3">
          <InterruptedReport />
          <div className="space-y-1">
            <p className="font-semibold text-base tracking-tight">
              {hasReport ? <Trans>Scan cut short</Trans> : <Trans>Scan couldn't finish</Trans>}
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed max-w-[220px] mx-auto">
              {hasReport
                ? <Trans>The pipeline stopped early — your partial results are still visible above.</Trans>
                : errorMsg
                ? errorMsg
                : <Trans>Something interrupted the audit. Your site is fine — this was on our end.</Trans>}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="space-y-2">
          <button
            onClick={onRetry}
            className="w-full rounded-xl bg-destructive/10 hover:bg-destructive/20 border border-destructive/25 px-4 py-2.5 text-sm font-medium text-destructive transition-colors"
          >
            <Trans>↺ Try again</Trans>
          </button>
          <p className="text-2xs text-muted-foreground">
            <Trans>Usually resolves on the first retry</Trans>
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AuditReport
// ---------------------------------------------------------------------------

export default function AuditReport({
  phase,
  steps,
  versions,
  selectedVersionId,
  onSelectVersion,
  streamingHtml,
  errorMsg,
  onRetry,
  leadToken = null,
  leadEmail = null,
  // Rendered in the header once there is a report — the share control, which
  // the workspace owns because it knows the conversation and the project.
  actions = null,
}) {
  const { t } = useLingui();
  const iframeRef = useRef(null);

  const selectedVersion =
    versions?.find((v) => v.version_id === selectedVersionId) ||
    versions?.[versions.length - 1];

  const reportMode = selectedVersion?.report?.report_mode ?? "freehand";
  const structuredData = selectedVersion?.report?.structured_data ?? null;
  // finalHtml is the complete HTML from ARTIFACT_VERSION — never the streaming partial chunks.
  // We only show the iframe once we have the full document to avoid white-flash reloads on
  // every srcDoc update during the streaming phase.
  const finalHtml = selectedVersion?.report?.html_report || "";
  const html = finalHtml || streamingHtml || "";  // used for download
  const hasReport = reportMode === "template" ? !!structuredData : !!finalHtml;
  const isStreamingReport = !finalHtml && !!streamingHtml;  // receiving chunks, final not yet ready
  const isFailed = phase === Phase.FAILED;
  const isPipeline = phase === Phase.PIPELINE || phase === Phase.STARTING;

  function handleDownload() {
    const stem = `duct-seo-v${selectedVersion?.version_id ?? "draft"}`;
    if (reportMode === "template" && structuredData) {
      saveText(JSON.stringify(structuredData, null, 2), `${stem}.json`, "application/json");
      return;
    }
    if (!html) return;
    saveText(html, `${stem}.html`, "text/html");
  }

  function handlePrint() {
    if (reportMode === "template") {
      window.print();
      return;
    }
    // sandbox="allow-modals allow-same-origin" (no allow-scripts) lets the parent call
    // contentWindow.print() while keeping agent HTML scripts inert.
    iframeRef.current?.contentWindow?.print();
  }

  return (
    <div className="flex flex-col h-full relative">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0 overflow-x-auto">
          <span className="text-sm font-medium shrink-0"><Trans>SEO Report</Trans></span>
          <VersionPills
            versions={versions}
            selectedId={selectedVersionId}
            onSelect={onSelectVersion}
          />
        </div>
        {hasReport && (
          <div className="flex items-center gap-1 shrink-0">
            {actions}
            <button
              onClick={handleDownload}
              title={t`Download HTML report`}
              className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted text-sm transition-colors"
            >
              ↓
            </button>
            <button
              onClick={handlePrint}
              title={t`Print report`}
              className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              🖨
            </button>
          </div>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-hidden relative">
        {hasReport ? (
          <>
            {reportMode === "template" && structuredData ? (
              <div className="h-full overflow-auto">
                <AuditReportV1 data={structuredData} leadToken={leadToken} email={leadEmail} />
              </div>
            ) : (
              <iframe
                ref={iframeRef}
                srcDoc={finalHtml}
                sandbox="allow-modals allow-same-origin"
                title={t`SEO Audit Report`}
                className="w-full h-full border-0"
              />
            )}
            {isFailed && (
              <FailedOverlay errorMsg={errorMsg} onRetry={onRetry} hasReport={true} />
            )}
          </>
        ) : isFailed ? (
          <FailedOverlay errorMsg={errorMsg} onRetry={onRetry} hasReport={false} />
        ) : (
          <SynthesisProgress steps={steps || []} isStreamingReport={isStreamingReport} />
        )}
      </div>
    </div>
  );
}
