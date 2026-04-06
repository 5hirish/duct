import { listReports } from "../../../lib/reports";
import ReportsList from "../../../components/ReportsList";
import { ReportsGenerateCta } from "./ReportsGenerateCta";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const reports = await listReports();

  return (
    <section>
      <div className="page-toolbar">
        <h1 className="page-toolbar-title">Reports</h1>
        <ReportsGenerateCta />
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Open a brief to view insights, or generate a new one from your connected data.
      </p>

      <ReportsList serverReports={reports} />
    </section>
  );
}
