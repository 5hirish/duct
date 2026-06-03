"use client";

import { useCallback, useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import AuditWorkspace from "../../../../components/audit/AuditWorkspace";
import AuditReportV1 from "../../../../components/audit/AuditReportV1";
import { saveLeadReport, validateLeadToken } from "../../../../lib/api";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL
  ? `${process.env.NEXT_PUBLIC_SITE_URL}/seo-audit`
  : process.env.NODE_ENV === "development"
  ? "http://localhost:8090/seo-audit.html"
  : "https://getduct.ai/seo-audit";

// Mirrors AgentEffort enum in backend/agents/models.py
const AgentEffort = Object.freeze({
  LOW:   "low",
  MEDIUM: "medium",
  HIGH:  "high",
  XHIGH: "xhigh",
  MAX:   "max",
});

// Mirrors CrawlDepth enum in backend/agents/audit/schema.py
const CrawlDepth = Object.freeze({
  LIGHT: "light",
  DEEP:  "deep",
});

// Mirrors ReportMode enum in backend/agents/audit/schema.py
const ReportMode = Object.freeze({
  FREEHAND: "freehand",
  TEMPLATE: "template",
});

function timeAgo(isoString) {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const h = Math.floor(diffMs / 36e5);
  if (h < 1) return "less than an hour ago";
  return h === 1 ? "1 hour ago" : `${h} hours ago`;
}

function LeadSeoAuditInner() {
  const searchParams = useSearchParams();

  // Capture once on mount — stable even after we strip the params from the URL bar
  const [token] = useState(() => searchParams.get("token") || "");
  const [url]   = useState(() => searchParams.get("url")   || "");

  const [state, setState]             = useState("validating"); // validating | invalid | cached | ready
  const [sessionId]                   = useState(() => crypto.randomUUID());
  const [auditParams, setAuditParams] = useState(null);
  const [cachedReport, setCachedReport] = useState(null);
  const [cachedAt, setCachedAt]         = useState(null);

  useEffect(() => {
    if (!url || !token) {
      setState("invalid");
      return;
    }

    // AbortController prevents the double-invoke from React StrictMode (dev)
    // from creating two audit sessions.
    const controller = new AbortController();

    // Remove token+url from URL bar immediately — prevents them sitting in
    // browser history or leaking via Referer on subsequent navigation.
    window.history.replaceState(null, "", window.location.pathname);

    validateLeadToken(token)
      .then((data) => {
        if (controller.signal.aborted) return;
        if (data.cached_report) {
          setCachedReport(data.cached_report);
          setCachedAt(data.cached_at);
          setState("cached");
          return;
        }
        setAuditParams({
          url: data.website_url || url,
          business_context: {},
          effort: AgentEffort.LOW,
          adaptive_thinking: false,
          report_mode: ReportMode.TEMPLATE,
          template_id: "seo_v1",
          crawl_depth: CrawlDepth.LIGHT,
          max_blog_posts: 2,
        });
        setState("ready");
      })
      .catch(() => { if (!controller.signal.aborted) setState("invalid"); });

    return () => controller.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // run once — url/token captured in stable useState above

  const handleReportReady = useCallback(
    (report) => saveLeadReport(token, report),
    [token],
  );

  // ── Loading ──────────────────────────────────────────────────────────────
  if (state === "validating") {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <span className="size-5 rounded-full border-2 border-orange-500 border-t-transparent animate-spin" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">Verifying your access…</p>
        </div>
      </div>
    );
  }

  // ── Invalid token ────────────────────────────────────────────────────────
  if (state === "invalid") {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <div className="max-w-sm w-full rounded-xl border border-border bg-card p-8 text-center shadow-sm">
          <div className="size-12 rounded-full bg-orange-50 flex items-center justify-center mx-auto mb-4" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-orange-500">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 8v4m0 4h.01"/>
            </svg>
          </div>
          <h1 className="text-lg font-semibold text-foreground mb-2">Invalid or expired link</h1>
          <p className="text-sm text-muted-foreground mb-6">
            This audit link is no longer valid. Links expire after 24 hours. Please enter your website again to get a fresh audit.
          </p>
          <a
            href={SITE_URL}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-orange-700 transition-colors"
          >
            Get a new free audit →
          </a>
        </div>
      </div>
    );
  }

  // ── Cached report ────────────────────────────────────────────────────────
  if (state === "cached") {
    return (
      <div className="flex flex-col flex-1 min-h-0 overflow-y-auto">
        <div className="shrink-0 flex items-center justify-between gap-4 px-4 py-2 bg-amber-50 border-b border-amber-200 text-sm">
          <span className="text-amber-800">
            ⚡ Showing a cached audit from {cachedAt ? timeAgo(cachedAt) : "recently"} —
            results may not reflect recent changes.
          </span>
          <a
            href={SITE_URL}
            className="shrink-0 inline-flex items-center gap-1 rounded-md border border-amber-400 bg-white px-3 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-50 transition-colors"
          >
            Run fresh audit →
          </a>
        </div>
        <div className="flex-1 overflow-y-auto">
          <AuditReportV1 report={cachedReport} />
        </div>
        <div className="shrink-0 flex items-center justify-between gap-4 px-4 py-2 bg-orange-50 border-t border-orange-200 text-sm">
          <span className="font-medium text-orange-900">Save and share this report</span>
          <a
            href="/"
            className="inline-flex items-center gap-1 rounded-md bg-orange-600 px-3 py-1 text-xs font-semibold text-white hover:bg-orange-700 transition-colors"
          >
            Sign up free →
          </a>
        </div>
      </div>
    );
  }

  // ── Fresh audit ──────────────────────────────────────────────────────────
  return (
    <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
      <AuditWorkspace
        sessionId={sessionId}
        auditParams={auditParams}
        publicMode={true}
        onReportReady={handleReportReady}
      />
    </div>
  );
}

export default function LeadSeoAuditPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-1 items-center justify-center">
        <span className="size-5 rounded-full border-2 border-orange-500 border-t-transparent animate-spin" aria-hidden="true" />
      </div>
    }>
      <LeadSeoAuditInner />
    </Suspense>
  );
}
