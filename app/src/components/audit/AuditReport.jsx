"use client";

import { useRef } from "react";
import { Phase } from "./auditPhase";
import { AuditStep } from "../../lib/auditEvents";
import { StepStatus } from "../../lib/agentSteps";
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
      {[...versions].reverse().map((v) => (
        <button
          key={v.version_id}
          onClick={() => onSelect(v.version_id)}
          className={`rounded-full px-2.5 py-0.5 text-xs transition-colors border whitespace-nowrap ${
            active === v.version_id
              ? "bg-primary text-primary-foreground border-primary"
              : "border-border text-muted-foreground hover:border-foreground/50 hover:text-foreground"
          }`}
        >
          v{v.version_id} — {v.label}
        </button>
      ))}
      {isOld && (
        <span className="text-xs text-amber-500 font-medium">older version</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Synthesis progress — shown in the report panel while Duct works
// ---------------------------------------------------------------------------

// Virtual step ID — not emitted by the backend, driven by isStreamingReport prop
const STEP_WRITE_REPORT = "write_report";

const STAGE_META = [
  { id: AuditStep.FETCH_SITEMAP,    label: "Mapping your site structure",          virtual: false },
  { id: AuditStep.CRAWL_PAGES,      label: "Reading and parsing your pages",       virtual: false },
  // conditional: enrichment is skipped for the lead-magnet flow (no business
  // context), so only render this stage once the backend actually emits it.
  { id: AuditStep.ENRICHING,        label: "Researching competitors",              virtual: false, conditional: true },
  { id: AuditStep.SYNTHESIZE_AUDIT, label: "Scoring signals & building findings",  virtual: false },
  { id: STEP_WRITE_REPORT,          label: "Generating report",                    virtual: true  },
];

const SYNTHESIS_LINES = [
  "Evaluating title tags and meta descriptions…",
  "Checking structured data coverage…",
  "Reviewing Open Graph completeness…",
  "Analysing internal linking patterns…",
  "Measuring E-E-A-T signals…",
  "Scoring each SEO category…",
  "Composing findings and priorities…",
];

// Right-aligned payload chips, audit-specific (sitemap page counts, competitor
// counts). Everything else (icons, time estimate, progress bar, rotating lines)
// is the shared PipelineProgress.
function auditStageChip(stage, step, status) {
  if (step?.payload?.landing_pages != null) {
    return (
      <span className="text-xs text-muted-foreground shrink-0">
        {step.payload.landing_pages} page{step.payload.landing_pages !== 1 ? "s" : ""}
        {step.payload.blog_posts > 0 && `, ${step.payload.blog_posts} post${step.payload.blog_posts !== 1 ? "s" : ""}`}
      </span>
    );
  }
  if (status === StepStatus.SUCCESS && step?.payload?.competitors != null) {
    return (
      <span className="text-xs text-muted-foreground shrink-0">
        {step.payload.competitors.length} competitor{step.payload.competitors.length !== 1 ? "s" : ""}
      </span>
    );
  }
  return null;
}

function SynthesisProgress({ steps, isStreamingReport = false }) {
  // Once the model starts adding categories, swap the static time estimate for live
  // "N/9 categories" progress (emitted per AddAuditCategory call by the backend).
  const synthStep = steps?.find((s) => s.step_id === AuditStep.SYNTHESIZE_AUDIT);
  const done = synthStep?.payload?.categories_done;
  const estimate = done != null
    ? `${done}/${synthStep.payload.categories_total ?? 9} categories`
    : "~3 min";
  return (
    <PipelineProgress
      stages={STAGE_META}
      steps={steps}
      activeId={AuditStep.SYNTHESIZE_AUDIT}
      writingId={STEP_WRITE_REPORT}
      writing={isStreamingReport}
      lines={SYNTHESIS_LINES}
      estimate={estimate}
      buildingLabel="Building report"
      streamingLabel="Generating report"
      streamingSubtitle="Writing your report…"
      idleSubtitle="Working on your report…"
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
                <span className="text-[8px] text-destructive/60 font-medium shrink-0">stopped</span>
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
              {hasReport ? "Scan cut short" : "Scan couldn't finish"}
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed max-w-[220px] mx-auto">
              {hasReport
                ? "The pipeline stopped early — your partial results are still visible above."
                : errorMsg
                ? errorMsg
                : "Something interrupted the audit. Your site is fine — this was on our end."}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="space-y-2">
          <button
            onClick={onRetry}
            className="w-full rounded-xl bg-destructive/10 hover:bg-destructive/20 border border-destructive/25 px-4 py-2.5 text-sm font-medium text-destructive transition-colors"
          >
            ↺ Try again
          </button>
          <p className="text-[11px] text-muted-foreground/70">
            Usually resolves on the first retry
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
}) {
  const iframeRef = useRef(null);

  const selectedVersion =
    versions?.find((v) => v.version_id === selectedVersionId) ||
    versions?.[versions.length - 1];

  const reportMode = selectedVersion?.report?.report_mode ?? "freehand";
  const structuredData = selectedVersion?.report?.structured_data ?? null;
  // finalHtml is the complete HTML from REPORT_UPDATED — never the streaming partial chunks.
  // We only show the iframe once we have the full document to avoid white-flash reloads on
  // every srcDoc update during the streaming phase.
  const finalHtml = selectedVersion?.report?.html_report || "";
  const html = finalHtml || streamingHtml || "";  // used for download
  const hasReport = reportMode === "template" ? !!structuredData : !!finalHtml;
  const isStreamingReport = !finalHtml && !!streamingHtml;  // receiving chunks, final not yet ready
  const isFailed = phase === Phase.FAILED;
  const isPipeline = phase === Phase.PIPELINE || phase === Phase.STARTING;

  function handleDownload() {
    if (reportMode === "template" && structuredData) {
      const blob = new Blob([JSON.stringify(structuredData, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `duct-seo-v${selectedVersion?.version_id ?? "draft"}.json`;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    if (!html) return;
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `duct-seo-v${selectedVersion?.version_id ?? "draft"}.html`;
    a.click();
    URL.revokeObjectURL(url);
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
          <span className="text-sm font-medium shrink-0">SEO Report</span>
          <VersionPills
            versions={versions}
            selectedId={selectedVersionId}
            onSelect={onSelectVersion}
          />
        </div>
        {hasReport && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={handleDownload}
              title="Download HTML report"
              className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted text-sm transition-colors"
            >
              ↓
            </button>
            <button
              onClick={handlePrint}
              title="Print report"
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
                title="SEO Audit Report"
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
