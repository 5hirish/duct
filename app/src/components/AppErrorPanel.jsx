"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

function buildIncidentId(error) {
  if (error?.digest) return `digest:${error.digest}`;
  return `client:${Date.now().toString(36)}`;
}

export default function AppErrorPanel({ error, reset, showHtmlShell = false }) {
  const [copyState, setCopyState] = useState("idle");
  const occurredAt = useMemo(() => new Date().toISOString(), []);
  const incidentId = useMemo(() => buildIncidentId(error), [error]);
  const route =
    typeof window !== "undefined"
      ? `${window.location.pathname}${window.location.search}`
      : "unknown";

  useEffect(() => {
    // Keep full stack/details in console for developer triage.
    // UI remains sanitized for production users.
    console.error("Duct app error boundary", {
      incidentId,
      occurredAt,
      route,
      digest: error?.digest ?? null,
      message: error?.message ?? "Unknown error",
      error,
    });
  }, [error, incidentId, occurredAt, route]);

  const handleCopyDebugInfo = async () => {
    const userAgentData =
      typeof navigator !== "undefined" && navigator.userAgentData
        ? {
            brands: navigator.userAgentData.brands ?? [],
            mobile: navigator.userAgentData.mobile ?? null,
            platform: navigator.userAgentData.platform ?? "unknown",
          }
        : null;
    const debugPayload = {
      incidentId,
      occurredAt,
      route,
      digest: error?.digest ?? null,
      errorMessage: error?.message ?? "Unknown error",
      page: typeof window !== "undefined" ? window.location.href : "unknown",
      referrer: typeof document !== "undefined" ? document.referrer || "none" : "unknown",
      timezone:
        typeof Intl !== "undefined"
          ? Intl.DateTimeFormat().resolvedOptions().timeZone
          : "unknown",
      browser: {
        userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "unknown",
        language: typeof navigator !== "undefined" ? navigator.language : "unknown",
        platform: typeof navigator !== "undefined" ? navigator.platform : "unknown",
        userAgentData,
      },
      screen:
        typeof window !== "undefined"
          ? {
              viewport: `${window.innerWidth}x${window.innerHeight}`,
              screen: `${window.screen.width}x${window.screen.height}`,
              pixelRatio: window.devicePixelRatio,
            }
          : null,
      session: (() => {
        if (typeof window === "undefined") return null;
        const key = "duct_debug_session_id";
        const existing = window.sessionStorage.getItem(key);
        if (existing) return { id: existing };
        const created = `sess_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
        window.sessionStorage.setItem(key, created);
        return { id: created };
      })(),
    };

    try {
      await navigator.clipboard.writeText(JSON.stringify(debugPayload, null, 2));
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1800);
    } catch {
      setCopyState("failed");
      window.setTimeout(() => setCopyState("idle"), 2500);
    }
  };

  const panel = (
    <main id="main-content" className="app-main" tabIndex={-1}>
      <section className="connection-card" style={{ maxWidth: 760, margin: "48px auto" }}>
        <p className="app-subtle" style={{ marginBottom: 10 }}>
          This page could not be loaded.
        </p>
        <h1 style={{ marginBottom: 10 }}>Something went wrong</h1>
        <p className="app-subtle" style={{ fontSize: 14, lineHeight: 1.55 }}>
          We logged this issue. Share the details below so we can trace it quickly.
        </p>

        <div className="generate-alert-detail" style={{ marginTop: 16 }}>
          <strong>Incident ID:</strong> {incidentId}
          {"\n"}
          <strong>When:</strong> {occurredAt}
          {"\n"}
          <strong>Route:</strong> {route}
          {"\n"}
          <strong>Digest:</strong> {error?.digest ?? "Unavailable"}
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 14 }}>
          <button type="button" className="app-button" onClick={reset}>
            Try again
          </button>
          <button type="button" className="app-button app-button--ghost" onClick={handleCopyDebugInfo}>
            {copyState === "copied"
              ? "Copied debug info"
              : copyState === "failed"
                ? "Copy failed"
                : "Copy debug info"}
          </button>
          <Link href="/" className="app-button app-button--ghost" data-slot="button">
            Go to home
          </Link>
          <Link href="/" className="app-button app-button--ghost" data-slot="button">
            Go to sign in
          </Link>
        </div>
      </section>
    </main>
  );

  if (!showHtmlShell) return panel;
  return (
    <html lang="en">
      <body className="min-h-dvh bg-background font-sans text-foreground antialiased">
        {panel}
      </body>
    </html>
  );
}
