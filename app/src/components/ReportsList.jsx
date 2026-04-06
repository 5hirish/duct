"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { getLocalReports, LOCAL_REPORTS_STORAGE_KEY } from "../lib/localReports";
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
    <div className="report-connection-icons" aria-hidden="true">
      {connections.includes("google_ads") && (
        <img
          src="https://upload.wikimedia.org/wikipedia/commons/c/c7/Google_Ads_logo.svg"
          alt="Google Ads"
          width="18"
          height="18"
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
  // Extract the Google Ads brief from envelope or legacy flat format
  return payload?.briefs?.google_ads ?? payload;
}

function getConnectionsFromPayload(payload) {
  // Envelope format: connectors_used is explicit
  if (payload?.connectors_used) return payload.connectors_used;
  const source = unwrapBrief(payload)?.source_metadata?.source;
  if (!source) return [];
  if (source.includes("google_ads")) return ["google_ads"];
  return [source];
}

/** Accessible name for report cards (link `aria-label`); keeps SR context without reading only a truncated line. */
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
    return {
      slug: entry.slug,
      title: formatTitle(entry.slug),
      themeLabel: brief?.source_metadata?.theme === "paid_ads" ? "Paid Ads" : "Report",
      generatedAt: entry.payload?.metadata?.generated_at || brief?.source_metadata?.generated_at || entry.savedAt,
      keyInsight: narrative?.verdict || narrative?.summary || "",
      connections: getConnectionsFromPayload(entry.payload),
      isLocal: true,
    };
  });
}

export default function ReportsList({ serverReports }) {
  const [localReports, setLocalReports] = useState([]);

  const syncLocalReportsFromStorage = useEffectEvent(() => {
    setLocalReports(mapStoredEntriesToReports(getLocalReports()));
  });

  useEffect(() => {
    syncLocalReportsFromStorage();
    function onStorage(event) {
      if (event.key !== null && event.key !== LOCAL_REPORTS_STORAGE_KEY) return;
      syncLocalReportsFromStorage();
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const allReports = [...localReports, ...serverReports.map((r) => ({ ...r, isLocal: false }))];
  allReports.sort((a, b) => {
    if (!a.generatedAt && !b.generatedAt) return 0;
    if (!a.generatedAt) return 1;
    if (!b.generatedAt) return -1;
    return b.generatedAt.localeCompare(a.generatedAt);
  });

  if (allReports.length === 0) {
    return (
      <div className="empty-reports">
        <p style={{ marginTop: 0, marginBottom: 8 }}>No reports yet.</p>
        <p className="app-subtle" style={{ marginTop: 0, marginBottom: 16, maxWidth: 420 }}>
          Generate an intelligence brief from your connected sources. Reports you save appear here.
        </p>
        <Button asChild>
          <Link href="/generate">Generate a report</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="report-grid">
      {allReports.map((report) => (
        <Link
          key={report.slug}
          href={`/reports/${report.slug}`}
          className="report-card"
          aria-label={reportCardAriaLabel(report)}
          transitionTypes={REPORT_NAV_TRANSITION_TYPES}
        >
          <div className="report-card-body">
            <strong>
              {report.title}
              {report.isLocal && <span className="report-badge-local">Local</span>}
            </strong>
            <div className="report-card-compact-row">
              <ConnectionIcons connections={report.connections} />
              <p
                className="report-card-insight report-card-insight--compact"
                title={report.keyInsight || "No key insight available yet."}
              >
                {report.keyInsight || "No key insight available yet."}
              </p>
              <span className="report-meta-right">{formatTimeAgo(report.generatedAt)}</span>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
