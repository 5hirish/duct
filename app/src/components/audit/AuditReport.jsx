"use client";

import { useRef, useState } from "react";

function VersionSelector({ versions, selectedId, onSelect }) {
  if (!versions || versions.length === 0) return null;

  const latest = versions[versions.length - 1];
  const isOld = selectedId !== null && selectedId !== latest.version_id;

  return (
    <div className="flex items-center gap-2">
      <select
        value={selectedId ?? latest.version_id}
        onChange={e => onSelect(Number(e.target.value))}
        className="rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {[...versions].reverse().map(v => (
          <option key={v.version_id} value={v.version_id}>
            v{v.version_id} — {v.label}
          </option>
        ))}
      </select>
      {isOld && (
        <span className="text-xs text-amber-500">older version</span>
      )}
    </div>
  );
}

function ReportSkeleton() {
  return (
    <div className="p-6 space-y-4 animate-pulse">
      <div className="h-6 bg-muted rounded w-1/3" />
      <div className="h-4 bg-muted rounded w-1/2" />
      <div className="grid grid-cols-3 gap-3 mt-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-20 bg-muted rounded" />
        ))}
      </div>
      <div className="space-y-2 mt-4">
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="h-12 bg-muted rounded" />
        ))}
      </div>
      <p className="text-xs text-muted-foreground text-center mt-6">Agent is working…</p>
    </div>
  );
}

export default function AuditReport({ versions, selectedVersionId, onSelectVersion }) {
  const iframeRef = useRef(null);

  const selectedVersion = versions?.find(v => v.version_id === selectedVersionId)
    || versions?.[versions.length - 1];

  function handleDownload() {
    if (!selectedVersion?.report?.html_report) return;
    const blob = new Blob([selectedVersion.report.html_report], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-seo-v${selectedVersion.version_id}.html`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handlePrint() {
    iframeRef.current?.contentWindow?.print();
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium truncate">SEO Report</span>
          <VersionSelector
            versions={versions}
            selectedId={selectedVersionId}
            onSelect={onSelectVersion}
          />
        </div>
        {selectedVersion?.report?.html_report && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={handleDownload}
              title="Download HTML report"
              className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted text-sm"
            >
              ↓
            </button>
            <button
              onClick={handlePrint}
              title="Print report"
              className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted text-sm"
            >
              🖨
            </button>
          </div>
        )}
      </div>

      {/* Report content */}
      <div className="flex-1 overflow-hidden">
        {!selectedVersion?.report?.html_report ? (
          <ReportSkeleton />
        ) : (
          <iframe
            ref={iframeRef}
            srcDoc={selectedVersion.report.html_report}
            sandbox="allow-same-origin allow-modals"
            title="SEO Audit Report"
            className="w-full h-full border-0"
          />
        )}
      </div>
    </div>
  );
}
