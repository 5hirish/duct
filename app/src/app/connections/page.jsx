"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import GoogleAdsReport from "../../components/GoogleAdsReport";
import { BASE, fetchGoogleAdsAccounts, runGoogleAdsReport } from "../../lib/api";

function defaultDateTo() {
  return new Date().toISOString().slice(0, 10);
}

function defaultDateFrom() {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

export default function ConnectionsPage() {
  /** False until client mount — keeps SSR + first client paint identical (avoids hydration mismatch). */
  const [mounted, setMounted] = useState(false);
  const [authState, setAuthState] = useState("checking");
  const [refreshToken, setRefreshToken] = useState("");
  const [accounts, setAccounts] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  /** Set in useEffect so SSR/first paint never embed `new Date()` (avoids hydration drift). */
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [report, setReport] = useState(null);

  const busy = status === "loading";

  const selectedAccount = useMemo(
    () => accounts.find((item) => item.customer_id === selectedAccountId) ?? null,
    [accounts, selectedAccountId]
  );

  const payloadParams = useMemo(() => {
    if (!selectedAccount || !refreshToken) return null;
    return {
      customer_id: selectedAccount.customer_id,
      refresh_token: refreshToken,
      date_from: dateFrom,
      date_to: dateTo,
      account_name: selectedAccount.descriptive_name,
      currency_code: selectedAccount.currency_code || "USD",
      theme: "paid_ads",
    };
  }, [selectedAccount, refreshToken, dateFrom, dateTo]);

  useEffect(() => {
    setMounted(true);
    setDateFrom(defaultDateFrom());
    setDateTo(defaultDateTo());

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

    async function loadAccounts() {
      try {
        setError("");
        setRefreshToken(token);
        const items = await fetchGoogleAdsAccounts(token);
        setAccounts(items);
        if (items.length > 0) {
          const storedAccountId = sessionStorage.getItem("gads_customer_id");
          const initialId =
            storedAccountId && items.some((item) => item.customer_id === storedAccountId)
              ? storedAccountId
              : items[0].customer_id;
          setSelectedAccountId(initialId);
          setAuthState("ready");
        } else {
          setSelectedAccountId("");
          setAuthState("selecting_account");
        }
      } catch (err) {
        setAuthState("unauthenticated");
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    loadAccounts();
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    if (!payloadParams) return;
    setError("");
    setStatus("loading");
    try {
      const data = await runGoogleAdsReport(payloadParams);
      setReport(data);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  function signOut() {
    sessionStorage.removeItem("gads_refresh_token");
    sessionStorage.removeItem("gads_customer_id");
    setRefreshToken("");
    setAccounts([]);
    setSelectedAccountId("");
    setReport(null);
    setStatus("idle");
    setAuthState("unauthenticated");
  }

  function onAccountChange(value) {
    setSelectedAccountId(value);
    if (value) {
      sessionStorage.setItem("gads_customer_id", value);
      setAuthState("ready");
    } else {
      sessionStorage.removeItem("gads_customer_id");
      setAuthState("selecting_account");
    }
  }

  const isConnected = authState === "ready" || authState === "selecting_account";
  const statusPillClass = !mounted
    ? "grey"
    : authState === "checking"
      ? "grey"
      : isConnected
        ? "green"
        : "grey";
  /** Pre-mount label matches legacy SSR output so cached RSC HTML hydrates cleanly. */
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
        Manage data source connections for reports.
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
              <span className="app-subtle">Loading accounts…</span>
            ) : isConnected ? (
              <button type="button" className="app-button app-button--ghost" onClick={signOut} disabled={busy}>
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

      {(authState === "selecting_account" || authState === "ready") && (
        <form
          onSubmit={onSubmit}
          style={{
            display: "grid",
            gap: 14,
            maxWidth: 640,
            margin: "24px 0",
          }}
        >
          <label style={{ display: "grid", gap: 4 }}>
            <span className="app-subtle">Google Ads account</span>
            <select
              className="app-input"
              value={selectedAccountId}
              onChange={(e) => onAccountChange(e.target.value)}
              disabled={busy}
            >
              {accounts.length === 0 && <option value="">No accessible accounts found</option>}
              {accounts.length > 0 &&
                accounts.map((account) => (
                  <option key={account.customer_id} value={account.customer_id}>
                    {account.descriptive_name} ({account.customer_id})
                    {account.manager ? " - MCC" : ""}
                  </option>
                ))}
            </select>
          </label>
          <div className="connections-date-row">
            <label style={{ display: "grid", gap: 4 }}>
              <span className="app-subtle">Date from</span>
              <input
                type="date"
                className="app-input"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                disabled={busy}
              />
            </label>
            <label style={{ display: "grid", gap: 4 }}>
              <span className="app-subtle">Date to</span>
              <input
                type="date"
                className="app-input"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                disabled={busy}
              />
            </label>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <button type="submit" className="app-button" disabled={busy || !selectedAccountId}>
              Run report
            </button>
          </div>
        </form>
      )}

      {busy && (
        <p className="app-subtle" style={{ marginBottom: 20 }}>
          Fetching campaign data… Generating AI insights…
        </p>
      )}
      {status === "error" && error && (
        <pre
          style={{
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
      {report && <GoogleAdsReport payload={report} />}
    </section>
  );
}
