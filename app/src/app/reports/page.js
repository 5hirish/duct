import Link from "next/link";
import { listReports } from "../../lib/reports";

export const dynamic = "force-dynamic";

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

export default async function ReportsPage() {
  const reports = await listReports();

  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
        <h1 style={{ marginTop: 0, marginBottom: 0 }}>Reports</h1>
        <Link className="btn btn-ghost" href="/generate">
          Generate
        </Link>
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Generated report artifacts from backend renderer.
      </p>

      {reports.length === 0 ? (
        <p>No reports found in backend/reports.</p>
      ) : (
        <div className="report-grid">
          {reports.map((report) => (
            <Link key={report.slug} href={`/reports/${report.slug}`} className="report-card">
              <div className="report-card-body">
                <strong>{report.title}</strong>
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
      )}
    </section>
  );
}

