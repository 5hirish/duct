import Link from "next/link";
import { listReports } from "../../../lib/reports";
import ReportsList from "../../../components/ReportsList";

export const dynamic = "force-dynamic";

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

      <ReportsList serverReports={reports} />
    </section>
  );
}
