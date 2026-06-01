"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ChatSidebar from "./ChatSidebar";
import InsightDashboard from "./InsightDashboard";
import { refreshInsightBriefs } from "../lib/api";
import {
  getInsightEntry,
  patchInsightRefresh,
} from "../lib/localInsights";
import { REPORT_NAV_TRANSITION_TYPES } from "../lib/reportNavTransition";
import { InsightContextProvider } from "./InsightContext";

function formatTitle(slug) {
  return slug
    .replace(/^local-/, "")
    .replace(/[-_]\d+$/, "")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function LocalInsightDetail({ slug }) {
  const [entry, setEntry] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [liveBriefs, setLiveBriefs] = useState(null);
  const [refreshState, setRefreshState] = useState({
    last_refreshed_at: null,
    refresh_status: "idle",
    refresh_error: null,
    live_briefs: null,
  });

  useEffect(() => {
    const nextEntry = getInsightEntry(slug);
    if (nextEntry) {
      setEntry(nextEntry);
      setRefreshState(nextEntry.refresh || {});
      setLiveBriefs(nextEntry.refresh?.live_briefs || null);
    } else {
      setNotFound(true);
    }
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    async function runRefresh(manual = false) {
      if (!entry?.routine) return;
      const hasAnyToken = Boolean(
        sessionStorage.getItem("gads_refresh_token") ||
          sessionStorage.getItem("ga4_refresh_token") ||
          sessionStorage.getItem("gsc_refresh_token")
      );
      if (!hasAnyToken && !manual) return;

      const loadingPatch = {
        refresh_status: "loading",
        refresh_error: null,
      };
      patchInsightRefresh(slug, loadingPatch);
      if (!cancelled) {
        setRefreshState((prev) => ({ ...prev, ...loadingPatch }));
      }

      try {
        const result = await refreshInsightBriefs(entry.routine);
        const successPatch = {
          last_refreshed_at: result.refreshed_at,
          refresh_status: "idle",
          refresh_error: null,
          live_briefs: result.briefs,
        };
        patchInsightRefresh(slug, successPatch);
        if (!cancelled) {
          setLiveBriefs(result.briefs);
          setRefreshState((prev) => ({ ...prev, ...successPatch }));
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const errorPatch = {
          refresh_status: "error",
          refresh_error: message,
        };
        patchInsightRefresh(slug, errorPatch);
        if (!cancelled) {
          setRefreshState((prev) => ({ ...prev, ...errorPatch }));
        }
      }
    }

    runRefresh(false);
    return () => {
      cancelled = true;
    };
  }, [entry, slug]);

  if (notFound) {
    return (
      <section>
        <p style={{ marginTop: 0, marginBottom: 10 }}>
          <Link href="/insights/organic-growth" transitionTypes={REPORT_NAV_TRANSITION_TYPES}>
            &larr; Back to insights
          </Link>
        </p>
        <h1 className="report-detail-title" style={{ marginTop: 0, marginBottom: 6 }}>
          Insight not found
        </h1>
        <p>This locally-stored insight may have been cleared from your browser.</p>
      </section>
    );
  }

  if (!entry?.payload) {
    return (
      <section>
        <p className="app-subtle" role="status" aria-live="polite">
          Loading insight…
        </p>
      </section>
    );
  }

  const payload = entry.payload;
  const isEnvelope = Boolean(payload.briefs);
  const brief = liveBriefs?.google_ads || (isEnvelope ? payload.briefs.google_ads : payload);
  const briefs = isEnvelope ? (liveBriefs || payload.briefs) : { google_ads: brief };
  const synthesis = isEnvelope ? payload.synthesis : null;
  const supplementary = isEnvelope ? payload.supplementary : null;

  const title = formatTitle(slug);
  const theme = brief?.source_metadata?.theme === "paid_ads" ? "Paid Ads" : "Report";
  const generatedAt = isEnvelope
    ? payload.metadata?.generated_at || brief?.source_metadata?.generated_at || ""
    : payload.source_metadata?.generated_at || "";
  const refreshedAt = refreshState.last_refreshed_at || "";
  const refreshStatus = refreshState.refresh_status || "idle";
  const canRefresh = Boolean(entry.routine);

  async function handleRefreshClick() {
    if (!entry?.routine || refreshStatus === "loading") return;
    const loadingPatch = { refresh_status: "loading", refresh_error: null };
    patchInsightRefresh(slug, loadingPatch);
    setRefreshState((prev) => ({ ...prev, ...loadingPatch }));
    try {
      const result = await refreshInsightBriefs(entry.routine);
      const successPatch = {
        last_refreshed_at: result.refreshed_at,
        refresh_status: "idle",
        refresh_error: null,
        live_briefs: result.briefs,
      };
      patchInsightRefresh(slug, successPatch);
      setLiveBriefs(result.briefs);
      setRefreshState((prev) => ({ ...prev, ...successPatch }));
      const latest = getInsightEntry(slug);
      if (latest) setEntry(latest);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const errorPatch = { refresh_status: "error", refresh_error: message };
      patchInsightRefresh(slug, errorPatch);
      setRefreshState((prev) => ({ ...prev, ...errorPatch }));
    }
  }

  return (
    <section>
      <p style={{ marginTop: 0, marginBottom: 10 }}>
        <Link href="/insights/organic-growth" transitionTypes={REPORT_NAV_TRANSITION_TYPES}>
          &larr; Back to insights
        </Link>
      </p>
      <h1 className="report-detail-title" style={{ marginTop: 0, marginBottom: 6 }}>
        {title} <span className="report-badge-local">Local</span>
      </h1>
      <p className="report-meta" style={{ marginTop: 0, marginBottom: 14 }}>
        {theme}
        {generatedAt ? ` \u00B7 Generated: ${generatedAt}` : ""}
      </p>
      {canRefresh && (
        <div className="generate-alert" style={{ marginBottom: 14 }}>
          <p className="app-subtle" style={{ marginTop: 0, marginBottom: 8 }}>
            {refreshStatus === "loading"
              ? "Refreshing live data..."
              : refreshState.refresh_error
                ? "Could not refresh - showing saved data."
                : refreshedAt
                  ? `Live data as of ${refreshedAt}`
                  : "Live refresh ready"}
          </p>
          <button
            type="button"
            className="app-link"
            onClick={handleRefreshClick}
            disabled={refreshStatus === "loading"}
          >
            {refreshStatus === "loading" ? "Refreshing..." : "Refresh now"}
          </button>
        </div>
      )}

      <InsightContextProvider
        entry={{
          ...entry,
          refresh: {
            ...(entry.refresh || {}),
            ...refreshState,
          },
        }}
        liveBriefs={liveBriefs}
      >
        <div className="insight-detail-layout">
          <div className="insight-detail-main">
            <InsightDashboard
              brief={brief}
              briefs={briefs}
              synthesis={synthesis}
              supplementary={supplementary}
            />
          </div>
          <aside className="insight-detail-sidebar">
            <ChatSidebar />
          </aside>
        </div>
      </InsightContextProvider>
    </section>
  );
}
