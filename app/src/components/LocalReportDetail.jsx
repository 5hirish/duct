"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import GoogleAdsReport from "./GoogleAdsReport";
import { getLocalReportBySlug } from "../lib/localReports";

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
          <Link href="/reports">&larr; Back to reports</Link>
        </p>
        <h1 style={{ marginTop: 0, marginBottom: 6 }}>Report not found</h1>
        <p>This locally-stored report may have been cleared from your browser.</p>
      </section>
    );
  }

  if (!payload) {
    return (
      <section>
        <p className="app-subtle">Loading report...</p>
      </section>
    );
  }

  const title = formatTitle(slug);
  const theme = payload.source_metadata?.theme === "paid_ads" ? "Paid Ads" : "Report";
  const generatedAt = payload.source_metadata?.generated_at || "";

  return (
    <section>
      <p style={{ marginTop: 0, marginBottom: 10 }}>
        <Link href="/reports">&larr; Back to reports</Link>
      </p>
      <h1 style={{ marginTop: 0, marginBottom: 6 }}>
        {title} <span className="report-badge-local">Local</span>
      </h1>
      <p className="report-meta" style={{ marginTop: 0, marginBottom: 14 }}>
        {theme}
        {generatedAt ? ` \u00B7 Generated: ${generatedAt}` : ""}
      </p>

      <GoogleAdsReport payload={payload} />
    </section>
  );
}
