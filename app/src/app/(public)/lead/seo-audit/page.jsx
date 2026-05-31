"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import AuditWorkspace from "../../../../components/audit/AuditWorkspace";
import { saveLeadReport, validateLeadToken } from "../../../../lib/api";

const SITE_URL = "https://getduct.ai/seo-audit";

export default function LeadSeoAuditPage() {
  const searchParams = useSearchParams();

  // Capture once on mount — stable even after we strip the params from the URL bar
  const [token]   = useState(() => searchParams.get("token") || "");
  const [url]     = useState(() => searchParams.get("url")   || "");

  const [state, setState]             = useState("validating"); // validating | invalid | ready
  const [sessionId]                   = useState(() => crypto.randomUUID());
  const [auditParams, setAuditParams] = useState(null);

  useEffect(() => {
    if (!url || !token) {
      setState("invalid");
      return;
    }

    // Remove token+url from URL bar immediately — prevents them sitting in
    // browser history or leaking via Referer on subsequent navigation.
    window.history.replaceState(null, "", window.location.pathname);

    validateLeadToken(token)
      .then((data) => {
        setAuditParams({
          url: data.website_url || url,
          business_context: {},
          effort: "standard",
          adaptive_thinking: false,
        });
        setState("ready");
      })
      .catch(() => setState("invalid"));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // run once — url/token captured in stable useState above

  const handleReportReady = useCallback(
    (report) => saveLeadReport(token, report),
    [token],
  );

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
