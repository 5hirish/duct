"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BASE, fetchGoogleAdsAccounts } from "../../../lib/api";

export default function ConnectionsPage() {
  /** False until client mount — keeps SSR + first client paint identical (avoids hydration mismatch). */
  const [mounted, setMounted] = useState(false);
  const [authState, setAuthState] = useState("checking");
  const [error, setError] = useState("");

  useEffect(() => {
    setMounted(true);

    const hash = window.location.hash;
    if (hash.startsWith("#refresh_token=")) {
      const token = decodeURIComponent(hash.slice("#refresh_token=".length));
      if (token) {
        sessionStorage.setItem("gads_refresh_token", token);
      }
      window.history.replaceState(null, "", window.location.pathname);
    }

    const token = sessionStorage.getItem("gads_refresh_token") || "";
    if (!token) {
      setAuthState("unauthenticated");
      return;
    }

    async function verifyConnection() {
      try {
        setError("");
        const items = await fetchGoogleAdsAccounts(token);
        if (items.length > 0) {
          setAuthState("ready");
        } else {
          setAuthState("selecting_account");
        }
      } catch (err) {
        setAuthState("unauthenticated");
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    verifyConnection();
  }, []);

  function signOut() {
    sessionStorage.removeItem("gads_refresh_token");
    sessionStorage.removeItem("gads_customer_id");
    setAuthState("unauthenticated");
  }

  const isConnected = authState === "ready" || authState === "selecting_account";
  const statusPillClass = !mounted
    ? "grey"
    : authState === "checking"
      ? "grey"
      : isConnected
        ? "green"
        : "grey";
  const statusPillLabel = !mounted
    ? "Not connected"
    : authState === "checking"
      ? "Checking…"
      : isConnected
        ? "Connected"
        : "Not connected";

  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
        <Link
          className="btn btn-ghost connection-back-btn"
          href="/reports"
          aria-label="Back to Reports"
          title="Back to Reports"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M15 18 9 12l6-6"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </Link>
        <h1 style={{ marginTop: 0, marginBottom: 0 }}>Connections</h1>
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Manage data source connections for reports. Choose your Google Ads account when you{" "}
        <Link href="/generate" className="app-link">
          generate a report
        </Link>
        .
      </p>

      <div className="connection-grid">
        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/c/c7/Google_Ads_logo.svg"
                alt="Google Ads logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Ads</h2>
              <p className="connection-description">
                Campaign performance metrics including spend, clicks, impressions, conversions, and ROAS.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className={`status-pill ${statusPillClass}`} suppressHydrationWarning>
              {statusPillLabel}
            </span>
            {!mounted ? (
              <span className="app-subtle" aria-hidden="true">
                &nbsp;
              </span>
            ) : authState === "checking" ? (
              <span className="app-subtle">Verifying access…</span>
            ) : isConnected ? (
              <button type="button" className="app-button app-button--ghost" onClick={signOut}>
                Disconnect
              </button>
            ) : (
              <a
                className="app-button"
                href={`${BASE}/auth/connectors/google_ads/oauth/authorize`}
              >
                Connect
              </a>
            )}
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/d/dc/Google_Search_Console_logo.svg"
                alt="Google Search Console logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Search Console</h2>
              <p className="connection-description">
                Organic search queries, clicks, impressions, and average position data for SEO reporting.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming soon</span>
            <button type="button" className="app-button app-button--ghost" disabled>
              Coming soon
            </button>
          </div>
        </article>

        <article className="connection-card">
          <div className="connection-card-head">
            <div className="connection-logo" aria-hidden="true">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/7/77/GAnalytics.svg"
                alt="Google Analytics logo"
                width="28"
                height="28"
              />
            </div>
            <div>
              <h2 className="connection-title">Google Analytics</h2>
              <p className="connection-description">
                Website traffic, sessions, engagement, and conversion trend data for performance reporting.
              </p>
            </div>
          </div>
          <div className="connection-status-row">
            <span className="status-pill yellow">Coming soon</span>
            <button type="button" className="app-button app-button--ghost" disabled>
              Coming soon
            </button>
          </div>
        </article>
      </div>

      {error && authState === "unauthenticated" && (
        <pre
          style={{
            marginTop: 20,
            padding: 12,
            borderRadius: 8,
            background: "rgba(180, 40, 40, 0.12)",
            color: "var(--app-fg, inherit)",
            overflow: "auto",
            fontSize: 13,
          }}
        >
          {error}
        </pre>
      )}

      {authState === "selecting_account" && (
        <p className="app-subtle" style={{ marginTop: 20 }}>
          Google Ads authorized, but no accessible customer accounts were returned. Check account access in Google Ads
          or try another Google user.
        </p>
      )}
    </section>
  );
}
