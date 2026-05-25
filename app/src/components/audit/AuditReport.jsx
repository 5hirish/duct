"use client";

import { useRef } from "react";
import { Phase } from "./auditPhase";
import { AuditStep } from "../../lib/auditEvents";
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

const STAGE_META = [
  { id: AuditStep.FETCH_SITEMAP, label: "Mapping your site structure",   icon: "🗺" },
  { id: AuditStep.CRAWL_PAGES,  label: "Reading and parsing your pages", icon: "📄" },
  { id: AuditStep.SYNTHESIZE_AUDIT, label: "Scoring signals & building findings", icon: "⚡" },
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

function SynthesisProgress({ steps }) {
  // Pick a rotating line based on the current second so it feels alive
  const lineIdx = Math.floor(Date.now() / 3000) % SYNTHESIS_LINES.length;
  const synthStep = steps.find((s) => s.step_id === AuditStep.SYNTHESIZE_AUDIT);
  const isSynthesising = synthStep?.status === "running";

  return (
    <div className="flex flex-col items-center justify-center h-full px-8 py-12 text-center select-none">
      {/* Brand + animation */}
      <div className="mb-8 space-y-3">
        <div className="flex items-center justify-center gap-2">
          <span className="text-2xl font-bold tracking-tight">Duct</span>
          <span className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="inline-block size-1.5 rounded-full bg-primary animate-bounce"
                style={{ animationDelay: `${i * 0.18}s` }}
              />
            ))}
          </span>
        </div>
        <p className="text-sm text-muted-foreground min-h-[1.25rem] transition-all">
          {isSynthesising ? SYNTHESIS_LINES[lineIdx] : "Working on your report…"}
        </p>
      </div>

      {/* Step list */}
      <div className="w-full max-w-xs space-y-2 text-left">
        {STAGE_META.map((stage) => {
          const step = steps.find((s) => s.step_id === stage.id);
          const status = step?.status ?? "pending";

          return (
            <div
              key={stage.id}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all duration-300 ${
                status === "running"
                  ? "bg-primary/8 border border-primary/20"
                  : status === "success"
                  ? "opacity-50"
                  : "opacity-20"
              }`}
            >
              {status === "running" ? (
                <span className="size-3.5 shrink-0 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              ) : status === "success" ? (
                <span className="text-green-500 text-sm shrink-0">✓</span>
              ) : (
                <span className="size-3.5 shrink-0 rounded-full border border-muted-foreground/30" />
              )}
              <span className="text-sm flex-1">{stage.label}</span>
              {status === "running" && stage.id === AuditStep.SYNTHESIZE_AUDIT && (
                <span className="text-xs text-muted-foreground shrink-0">~3 min</span>
              )}
              {status === "running" && stage.id !== AuditStep.SYNTHESIZE_AUDIT && (
                <span className="text-xs text-muted-foreground shrink-0 animate-pulse">now</span>
              )}
              {step?.payload?.landing_pages != null && (
                <span className="text-xs text-muted-foreground shrink-0">
                  {step.payload.landing_pages} page{step.payload.landing_pages !== 1 ? "s" : ""}
                  {step.payload.blog_posts > 0 && `, ${step.payload.blog_posts} post${step.payload.blog_posts !== 1 ? "s" : ""}`}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Indeterminate bar for synthesize step */}
      {isSynthesising && (
        <div className="mt-6 w-full max-w-xs">
          <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
            <span>Building report</span>
            <span>~3 min</span>
          </div>
          <div className="h-1 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary origin-left"
              style={{
                animation: "duct-progress 180s cubic-bezier(0.1, 0, 0.25, 1) forwards",
              }}
            />
          </div>
          <style>{`
            @keyframes duct-progress {
              from { width: 0% }
              to   { width: 82% }
            }
          `}</style>
        </div>
      )}
    </div>
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
}) {
  const iframeRef = useRef(null);

  const selectedVersion =
    versions?.find((v) => v.version_id === selectedVersionId) ||
    versions?.[versions.length - 1];

  const reportMode = selectedVersion?.report?.report_mode ?? "freehand";
  const structuredData = selectedVersion?.report?.structured_data ?? null;
  const html = selectedVersion?.report?.html_report || streamingHtml || "";
  const hasReport = reportMode === "template" ? !!structuredData : !!html;
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
                <AuditReportV1 data={structuredData} />
              </div>
            ) : (
              <iframe
                ref={iframeRef}
                srcDoc={html}
                sandbox="allow-modals"
                title="SEO Audit Report"
                className="w-full h-full border-0"
              />
            )}
            {/* Failed overlay on top of existing report — don't nuke it */}
            {isFailed && (
              <FailedOverlay errorMsg={errorMsg} onRetry={onRetry} hasReport={true} />
            )}
          </>
        ) : isFailed ? (
          <FailedOverlay errorMsg={errorMsg} onRetry={onRetry} hasReport={false} />
        ) : (
          <SynthesisProgress steps={steps || []} />
        )}
      </div>
    </div>
  );
}
