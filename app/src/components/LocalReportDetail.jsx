"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import GoogleAdsReport from "./GoogleAdsReport";
import { getLocalReportBySlug } from "../lib/localReports";
import { REPORT_NAV_TRANSITION_TYPES } from "../lib/reportNavTransition";

function formatTitle(slug) {
  return slug
    .replace(/^local-/, "")
    .replace(/[-_]\d+$/, "")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function LocalReportDetail({ slug }) {
  const [payload, setPayload] = useState(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    const data = getLocalReportBySlug(slug);
    if (data) {
      setPayload(data);
    } else {
      setNotFound(true);
    }
  }, [slug]);

  if (notFound) {
    return (
      <section>
        <p style={{ marginTop: 0, marginBottom: 10 }}>
          <Link href="/reports" transitionTypes={REPORT_NAV_TRANSITION_TYPES}>
            &larr; Back to reports
          </Link>
        </p>
        <h1 className="report-detail-title" style={{ marginTop: 0, marginBottom: 6 }}>
          Report not found
        </h1>
        <p>This locally-stored report may have been cleared from your browser.</p>
      </section>
    );
  }

  if (!payload) {
    return (
      <section>
        <p className="app-subtle" role="status" aria-live="polite">
          Loading report…
        </p>
      </section>
    );
  }

  // Detect envelope (v2) vs legacy flat format
  const isEnvelope = Boolean(payload.briefs);
  const brief = isEnvelope ? payload.briefs.google_ads : payload;
  const synthesis = isEnvelope ? payload.synthesis : null;

  const title = formatTitle(slug);
  const theme = brief?.source_metadata?.theme === "paid_ads" ? "Paid Ads" : "Report";
  const generatedAt = isEnvelope
    ? payload.metadata?.generated_at || brief?.source_metadata?.generated_at || ""
    : payload.source_metadata?.generated_at || "";

  return (
    <section>
      <p style={{ marginTop: 0, marginBottom: 10 }}>
        <Link href="/reports" transitionTypes={REPORT_NAV_TRANSITION_TYPES}>
          &larr; Back to reports
        </Link>
      </p>
      <h1 className="report-detail-title" style={{ marginTop: 0, marginBottom: 6 }}>
        {title} <span className="report-badge-local">Local</span>
      </h1>
      <p className="report-meta" style={{ marginTop: 0, marginBottom: 14 }}>
        {theme}
        {generatedAt ? ` \u00B7 Generated: ${generatedAt}` : ""}
      </p>

      <GoogleAdsReport brief={brief} synthesis={synthesis} />
    </section>
  );
}
