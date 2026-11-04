import { notFound } from "next/navigation";
import { Trans } from "@lingui/react/macro";
import { activateRequestI18n } from "@/i18n/server";
import { getReportBySlug } from "../../../../../lib/reports";
import InsightDashboard from "../../../../../components/InsightDashboard";
import LocalInsightDetail from "../../../../../components/LocalInsightDetail";
import { Page, PageHeader } from "@/components/ui/page";

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
    <Page>
      <PageHeader
        back={{ href: "/insights/organic-growth", label: <Trans>Home</Trans> }}
        title={report.title}
        status={
          <>
            {report.themeLabel}
            {generatedAt ? <> · <Trans>Generated {generatedAt}</Trans></> : ""}
          </>
        }
      />
      <InsightDashboard brief={report.payload} briefs={{ google_ads: report.payload }} synthesis={null} />
    </Page>
  );
}
