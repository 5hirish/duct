import { listReports } from "../../../../lib/reports";
import InsightsModeSelector from "../InsightsModeSelector";

export const dynamic = "force-dynamic";

export default async function OrganicGrowthPage() {
  const reports = await listReports();

  return (
    <section>
      <div className="page-toolbar">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Organic Growth</h1>
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Open an insight brief to explore recommendations, or generate a new insight from your connected data.
      </p>
      <InsightsModeSelector serverReports={reports} />
    </section>
  );
}
