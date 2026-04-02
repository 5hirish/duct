import Link from "next/link";
import { notFound } from "next/navigation";
import { getReportBySlug } from "../../../lib/reports";
import GoogleAdsReport from "../../../components/GoogleAdsReport";

export const dynamic = "force-dynamic";

export default async function ReportDetailPage({ params }) {
  const report = await getReportBySlug(params.slug);
  if (!report) {
    notFound();
  }

  return (
    <section>
      <p style={{ marginTop: 0, marginBottom: 10 }}>
        <Link href="/reports">← Back to reports</Link>
      </p>
      <h1 style={{ marginTop: 0, marginBottom: 6 }}>{report.title}</h1>
      <p className="report-meta" style={{ marginTop: 0, marginBottom: 14 }}>
        {report.themeLabel}
        {report.generatedAt ? ` · Generated: ${report.generatedAt}` : ""}
      </p>

      <GoogleAdsReport payload={report.payload} />
    </section>
  );
}
