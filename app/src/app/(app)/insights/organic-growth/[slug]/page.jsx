import Link from "next/link";
import { notFound } from "next/navigation";
import { REPORT_NAV_TRANSITION_TYPES } from "../../../../../lib/reportNavTransition";
import { getReportBySlug } from "../../../../../lib/reports";
import InsightDashboard from "../../../../../components/InsightDashboard";
import LocalInsightDetail from "../../../../../components/LocalInsightDetail";

export const dynamic = "force-dynamic";

export default async function InsightDetailPage({ params }) {
  const { slug } = await params;

  if (slug.startsWith("local-")) {
    return <LocalInsightDetail slug={slug} />;
  }

  const report = await getReportBySlug(slug);
  if (!report) notFound();

  return (
    <section>
      <p style={{ marginTop: 0, marginBottom: 10 }}>
        <Link href="/insights/organic-growth" transitionTypes={REPORT_NAV_TRANSITION_TYPES}>
          &larr; Back to insights
        </Link>
      </p>
      <h1 className="report-detail-title text-2xl font-semibold tracking-tight" style={{ marginTop: 0, marginBottom: 6 }}>
        {report.title}
      </h1>
      <p className="report-meta" style={{ marginTop: 0, marginBottom: 14 }}>
        {report.themeLabel}
        {report.generatedAt ? ` · Generated: ${report.generatedAt}` : ""}
      </p>
      <InsightDashboard brief={report.payload} briefs={{ google_ads: report.payload }} synthesis={null} />
    </section>
  );
}
