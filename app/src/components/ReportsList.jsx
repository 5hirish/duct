"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getLocalReports } from "../lib/localReports";

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
    <div className="report-connection-icons" aria-label="Connections">
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

function getConnectionsFromPayload(payload) {
  const source = payload?.source_metadata?.source;
  if (!source) return [];
  if (source.includes("google_ads")) return ["google_ads"];
  return [source];
}

export default function ReportsList({ serverReports }) {
  const [localReports, setLocalReports] = useState([]);

  useEffect(() => {
    const stored = getLocalReports();
    const mapped = stored.map((entry) => ({
      slug: entry.slug,
      title: formatTitle(entry.slug),
      themeLabel: entry.payload?.source_metadata?.theme === "paid_ads" ? "Paid Ads" : "Report",
      generatedAt: entry.payload?.source_metadata?.generated_at || entry.savedAt,
      keyInsight:
        entry.payload?.narrative?.verdict ||
        entry.payload?.narrative?.summary ||
        "",
      connections: getConnectionsFromPayload(entry.payload),
      isLocal: true,
    }));
    setLocalReports(mapped);
  }, []);

  const allReports = [...localReports, ...serverReports.map((r) => ({ ...r, isLocal: false }))];
  allReports.sort((a, b) => {
    if (!a.generatedAt && !b.generatedAt) return 0;
    if (!a.generatedAt) return 1;
    if (!b.generatedAt) return -1;
    return b.generatedAt.localeCompare(a.generatedAt);
  });

  if (allReports.length === 0) {
    return <p>No reports yet. Generate your first report to get started.</p>;
  }

  return (
    <div className="report-grid">
      {allReports.map((report) => (
        <Link
          key={report.slug}
          href={`/reports/${report.slug}`}
          className="report-card"
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
