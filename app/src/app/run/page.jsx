"use client";

import { useMemo, useState } from "react";
import GoogleAdsReport from "../../components/GoogleAdsReport";
import { runGoogleAdsReport } from "../../lib/api";

function defaultDateTo() {
  return new Date().toISOString().slice(0, 10);
}

function defaultDateFrom() {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

export default function RunReportPage() {
  const [customerId, setCustomerId] = useState("");
  const [developerToken, setDeveloperToken] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [refreshToken, setRefreshToken] = useState("");
  const [loginCustomerId, setLoginCustomerId] = useState("");
  const [dateFrom, setDateFrom] = useState(defaultDateFrom);
  const [dateTo, setDateTo] = useState(defaultDateTo);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [report, setReport] = useState(null);

  const busy = status === "loading";

  const payloadParams = useMemo(
    () => ({
      customer_id: customerId.trim(),
      developer_token: developerToken,
      client_id: clientId,
      client_secret: clientSecret,
      refresh_token: refreshToken,
      login_customer_id: loginCustomerId.trim(),
      date_from: dateFrom,
      date_to: dateTo,
      theme: "paid_ads",
    }),
    [
      customerId,
      developerToken,
      clientId,
      clientSecret,
      refreshToken,
      loginCustomerId,
      dateFrom,
      dateTo,
    ]
  );

  async function onSubmit(e) {
    e.preventDefault();
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

  async function onDemo() {
    setError("");
    setStatus("loading");
    try {
      const data = await runGoogleAdsReport({
        use_demo: true,
        date_to: dateTo,
        theme: "paid_ads",
      });
      setReport(data);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  return (
    <section>
      <h1 style={{ marginTop: 0 }}>Run report</h1>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Fetch live Google Ads data via the backend API, then render with the same report component as
        static artifacts.
      </p>

      <form
        onSubmit={onSubmit}
        style={{
          display: "grid",
          gap: 14,
          maxWidth: 520,
          marginBottom: 24,
        }}
      >
        <label style={{ display: "grid", gap: 4 }}>
          <span className="app-subtle">Customer ID</span>
          <input
            className="app-input"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            placeholder="123-456-7890"
            disabled={busy}
            autoComplete="off"
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="app-subtle">Developer token</span>
          <input
            type="password"
            className="app-input"
            value={developerToken}
            onChange={(e) => setDeveloperToken(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="app-subtle">OAuth client ID</span>
          <input
            type="password"
            className="app-input"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="app-subtle">OAuth client secret</span>
          <input
            type="password"
            className="app-input"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="app-subtle">Refresh token</span>
          <input
            type="password"
            className="app-input"
            value={refreshToken}
            onChange={(e) => setRefreshToken(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="app-subtle">Login customer ID (MCC, optional)</span>
          <input
            className="app-input"
            value={loginCustomerId}
            onChange={(e) => setLoginCustomerId(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
        </label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
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
          <button type="submit" className="app-button" disabled={busy}>
            Run report
          </button>
          <button type="button" className="app-button app-button--ghost" onClick={onDemo} disabled={busy}>
            Demo mode
          </button>
        </div>
      </form>

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
