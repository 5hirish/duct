"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getLocalReports, LOCAL_REPORTS_STORAGE_KEY } from "../lib/localReports";
import { FALLBACK_MODES, getModeByKey } from "../lib/modes";
import { REPORT_NAV_TRANSITION_TYPES } from "../lib/reportNavTransition";

function formatTimeAgo(iso) {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "";
  const diffMs = dt.getTime() - Date.now();
  const mins = Math.round(diffMs / 60000);
  const absMins = Math.abs(mins);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (absMins < 60) return rtf.format(mins, "minute");
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return rtf.format(hours, "hour");
  const days = Math.round(hours / 24);
  return rtf.format(days, "day");
}

function ConnectionIcons({ connections }) {
  if (!connections?.length) return null;
  return (
    <div className="flex items-center gap-1.5" aria-hidden="true">
      {connections.includes("google_ads") && (
        <img
          src="https://upload.wikimedia.org/wikipedia/commons/c/c7/Google_Ads_logo.svg"
          alt="Google Ads"
          width="16"
          height="16"
          className="size-4"
        />
      )}
    </div>
  );
}

function formatTitle(slug) {
  return slug
    .replace(/^local-/, "")
    .replace(/[-_]\d+$/, "")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function unwrapBrief(payload) {
  return payload?.briefs?.google_ads ?? payload;
}

function getConnectionsFromPayload(payload) {
  if (payload?.connectors_used) return payload.connectors_used;
  const source = unwrapBrief(payload)?.source_metadata?.source;
  if (!source) return [];
  if (source.includes("google_ads")) return ["google_ads"];
  return [source];
}

function reportCardAriaLabel(report, maxInsightLen = 160) {
  const localNote = report.isLocal ? " Stored in this browser." : "";
  const raw = (report.keyInsight || "").trim();
  if (!raw) {
    return `${report.title}.${localNote} View report.`;
  }
  const clipped = raw.length > maxInsightLen ? `${raw.slice(0, maxInsightLen).trim()}…` : raw;
  return `${report.title}. ${clipped}${localNote}`;
}

function mapStoredEntriesToReports(stored) {
  return stored.map((entry) => {
    const brief = unwrapBrief(entry.payload);
    const synthesis = entry.payload?.synthesis;
    const narrative = synthesis?.narrative ?? brief?.narrative;
    const entryMode = entry.mode || entry.routine?.mode || null;
    return {
      slug: entry.slug,
      title: formatTitle(entry.slug),
      mode: entryMode,
      themeLabel: brief?.source_metadata?.theme === "paid_ads" ? "Paid Ads" : "Report",
      generatedAt: entry.payload?.metadata?.generated_at || brief?.source_metadata?.generated_at || entry.savedAt,
      keyInsight: narrative?.verdict || narrative?.summary || "",
      connections: getConnectionsFromPayload(entry.payload),
      isLocal: true,
      isLive: Boolean(entry.routine),
    };
  });
}

function isDemoReport(report) {
  return report.slug === "google-ads-report";
}

export default function ReportsList({
  serverReports,
  projectId = null,
  mode = null,
  showGenerateButton = true,
}) {
  const [localReports, setLocalReports] = useState([]);

  const syncLocalReportsFromStorage = useEffectEvent(() => {
    setLocalReports(mapStoredEntriesToReports(getLocalReports(projectId, mode)));
  });

  useEffect(() => {
    syncLocalReportsFromStorage();
    function onStorage(event) {
      if (event.key !== null && event.key !== LOCAL_REPORTS_STORAGE_KEY) return;
      syncLocalReportsFromStorage();
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [projectId]);

  const filteredServerReports = mode
    ? serverReports.filter((r) => (r.mode || null) === mode)
    : serverReports;
  const allReports = [...localReports, ...filteredServerReports.map((r) => ({ ...r, isLocal: false }))];
  allReports.sort((a, b) => {
    if (!a.generatedAt && !b.generatedAt) return 0;
    if (!a.generatedAt) return 1;
    if (!b.generatedAt) return -1;
    return b.generatedAt.localeCompare(a.generatedAt);
  });

  if (allReports.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="mb-2 text-sm font-medium">No insights yet.</p>
        <p className="mb-5 text-sm text-muted-foreground max-w-sm mx-auto">
          Generate an intelligence brief from your connected sources. Saved insights appear here.
        </p>
        {showGenerateButton && (
          <Button asChild>
            <Link href={mode ? `/insights/generate?mode=${mode}` : "/insights/generate"}>Generate an insight</Link>
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="report-grid">
      {allReports.map((report) => (
        <Link
          key={report.slug}
          href={`/insights/${report.slug}`}
          className="group relative overflow-hidden flex flex-col justify-between min-h-24 rounded-3xl border border-border bg-card p-4 text-sm shadow-sm ring-1 ring-foreground/5 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          aria-label={reportCardAriaLabel(report)}
          transitionTypes={REPORT_NAV_TRANSITION_TYPES}
        >
          {isDemoReport(report) && (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute -right-10 top-4 w-36 rotate-45 bg-primary py-1 text-center text-[10px] font-semibold uppercase tracking-[0.18em] text-primary-foreground shadow-sm"
            >
              Demo
            </span>
          )}
          <div className="flex flex-col gap-1">
            <div className="flex items-start justify-between gap-2">
              <strong className="font-semibold leading-tight text-foreground">
                {report.title}
              </strong>
              <div className="flex items-center gap-1">
                {report.isLocal && (
                  <Badge variant="outline" className="shrink-0 text-xs">Local</Badge>
                )}
                {report.isLocal && report.isLive && (
                  <Badge variant="secondary" className="shrink-0 text-xs">Live</Badge>
                )}
                {(() => {
                  const modeConf = getModeByKey(FALLBACK_MODES, report.mode);
                  return modeConf ? (
                    <Badge variant="outline" className="shrink-0 text-xs">
                      {modeConf.emoji} {modeConf.short_label}
                    </Badge>
                  ) : null;
                })()}
              </div>
            </div>
            <div className="flex items-center gap-1.5 min-w-0">
              <ConnectionIcons connections={report.connections} />
              <p
                className="text-xs text-muted-foreground flex-1 min-w-0 truncate"
                title={report.keyInsight || "No key insight available yet."}
              >
                {report.keyInsight || "No key insight available yet."}
              </p>
              <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                {formatTimeAgo(report.generatedAt)}
              </span>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
