import Link from "next/link";
import { listReports } from "../../lib/reports";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const reports = await listReports();

  return (
    <section>
      <h1 style={{ marginTop: 0 }}>Reports</h1>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Generated report artifacts from backend renderer.
      </p>

      {reports.length === 0 ? (
        <p>No reports found in backend/reports.</p>
      ) : (
        <div className="report-grid">
          {reports.map((report) => (
            <Link key={report.slug} href={`/reports/${report.slug}`} className="report-card">
              <strong>{report.title}</strong>
              <p className="report-meta">
                {report.themeLabel}
                {report.generatedAt ? ` · Generated: ${report.generatedAt}` : ""}
              </p>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

