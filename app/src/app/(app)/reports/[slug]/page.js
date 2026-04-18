import Link from "next/link";
import { notFound } from "next/navigation";
import { REPORT_NAV_TRANSITION_TYPES } from "../../../../lib/reportNavTransition";
import { getReportBySlug } from "../../../../lib/reports";
import GoogleAdsReport from "../../../../components/GoogleAdsReport";
import LocalReportDetail from "../../../../components/LocalReportDetail";

export const dynamic = "force-dynamic";

export default async function ReportDetailPage({ params }) {
  const { slug } = await params;

  // Local reports (stored in localStorage) are handled client-side
  if (slug.startsWith("local-")) {
    return <LocalReportDetail slug={slug} />;
  }

  const report = await getReportBySlug(slug);
  if (!report) {
    notFound();
  }

  return (
    <section>
      <p style={{ marginTop: 0, marginBottom: 10 }}>
        <Link href="/reports" transitionTypes={REPORT_NAV_TRANSITION_TYPES}>
          &larr; Back to reports
        </Link>
      </p>
      <h1 className="report-detail-title text-2xl font-semibold tracking-tight" style={{ marginTop: 0, marginBottom: 6 }}>
        {report.title}
      </h1>
      <p className="report-meta" style={{ marginTop: 0, marginBottom: 14 }}>
        {report.themeLabel}
        {report.generatedAt ? ` \u00B7 Generated: ${report.generatedAt}` : ""}
      </p>

      <GoogleAdsReport payload={report.payload} />
    </section>
  );
}
