import Link from "next/link";
import { notFound } from "next/navigation";
import { Trans } from "@lingui/react/macro";
import { activateRequestI18n } from "@/i18n/server";
import { REPORT_NAV_TRANSITION_TYPES } from "../../../../../lib/reportNavTransition";
import { getReportBySlug } from "../../../../../lib/reports";
import InsightDashboard from "../../../../../components/InsightDashboard";
import LocalInsightDetail from "../../../../../components/LocalInsightDetail";

export const dynamic = "force-dynamic";

export default async function InsightDetailPage({ params }) {
  // A server page renders without its parents on a client-side navigation,
  // so the request's catalogue is activated here as well as in the root layout.
  await activateRequestI18n();
  const { slug } = await params;

  if (slug.startsWith("local-")) {
    return <LocalInsightDetail slug={slug} />;
  }

  const report = await getReportBySlug(slug);
  if (!report) notFound();

  const generatedAt = report.generatedAt;

  return (
    <section>
      <p style={{ marginTop: 0, marginBottom: 10 }}>
        <Link href="/insights/organic-growth" transitionTypes={REPORT_NAV_TRANSITION_TYPES}>
          <Trans>&larr; Back to insights</Trans>
        </Link>
      </p>
      <h1 className="report-detail-title text-2xl font-semibold tracking-tight" style={{ marginTop: 0, marginBottom: 6 }}>
        {report.title}
      </h1>
      <p className="report-meta" style={{ marginTop: 0, marginBottom: 14 }}>
        {report.themeLabel}
        {generatedAt ? <> · <Trans>Generated: {generatedAt}</Trans></> : ""}
      </p>
      <InsightDashboard brief={report.payload} briefs={{ google_ads: report.payload }} synthesis={null} />
    </section>
  );
}
