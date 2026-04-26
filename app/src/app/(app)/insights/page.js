import { listReports } from "../../../lib/reports";
import ReportsPageClient from "../../../components/ReportsPageClient";
import { InsightsGenerateCta } from "./InsightsGenerateCta";

export const dynamic = "force-dynamic";

export default async function InsightsPage() {
  const reports = await listReports();

  return (
    <section>
      <div className="page-toolbar">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Insights</h1>
        <InsightsGenerateCta />
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Open an insight brief to explore recommendations, or generate a new insight from your connected data.
      </p>

      <ReportsPageClient serverReports={reports} />
    </section>
  );
}
