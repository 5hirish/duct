"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import GoogleAdsReport from "../../components/GoogleAdsReport";
import { fetchGoogleAdsAccounts, generateReport } from "../../lib/api";
import { saveLocalReport, generateSlug } from "../../lib/localReports";

const GOALS = [
  {
    key: "lower_cac",
    icon: "\u{1F4C9}",
    label: "Lower CAC",
    description: "Find which campaigns and audiences deliver the cheapest conversions \u2014 cut waste, keep quality.",
  },
  {
    key: "maximize_roas",
    icon: "\u{1F4B0}",
    label: "Maximize ROAS",
    description: "Identify top-returning campaigns and reallocate budget away from underperformers.",
  },
  {
    key: "scale_conversions",
    icon: "\u{1F680}",
    label: "Scale conversions",
    description: "Grow conversion volume while keeping cost efficiency in check \u2014 find headroom to spend more.",
  },
  {
    key: "audit_spend",
    icon: "\u{1F50D}",
    label: "Audit spend efficiency",
    description: "Spot wasted budget, flag underperformers, and surface reallocation opportunities across campaigns.",
  },
  {
    key: "custom",
    icon: "\u{270F}\u{FE0F}",
    label: "Custom goal",
    description: "Describe your own analysis goal \u2014 the AI agent will tailor the report to your intent.",
  },
];

function formatLocalYmd(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Rolling window ending today: `daysBack` is subtracted from start (matches prior default: 7 → from = today − 7). */
function rangeEndingToday(daysBack) {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - daysBack);
  return { from: formatLocalYmd(from), to: formatLocalYmd(to) };
}

function defaultDateRange() {
  return rangeEndingToday(7);
}

/** Google Ads customer IDs must be compared as strings — API JSON may use numbers, <select> values are strings. */
function normalizeCustomerId(id) {
  if (id === null || id === undefined) return "";
  return String(id).replace(/\D/g, "") || String(id);
}

/** Map wizard step (1–5) to one of four progress phases: sources → configure → generating → report. */
function progressPhase(step) {
  if (step <= 1) return 1;
  if (step <= 3) return 2;
  if (step === 4) return 3;
  return 4;
}

function ProgressDots({ step }) {
  const phase = progressPhase(step);
  return (
    <div className="generate-progress">
      {[1, 2, 3, 4].map((n) => (
        <span
          key={n}
          className={`generate-dot${n < phase ? " done" : ""}${n === phase ? " active" : ""}`}
        />
      ))}
    </div>
  );
}

function StepConnections({ connections, selected, onToggle }) {
  const hasAny = connections.some((c) => c.connected);

  return (
    <div className="generate-step">
      <h2 className="generate-step-title">Select your data sources</h2>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 16 }}>
        Choose which connected tools to include in your report.
      </p>
      <div className="connection-grid">
        {connections.map((conn) => (
          <button
            key={conn.id}
            type="button"
            className={`connection-card connection-card--selectable${
              selected.includes(conn.id) ? " connection-card--selected" : ""
            }${!conn.connected ? " connection-card--disabled" : ""}`}
            disabled={!conn.connected}
            aria-pressed={selected.includes(conn.id)}
            onClick={() => conn.connected && onToggle(conn.id)}
          >
            <div className="connection-card-head">
              <div className="connection-logo" aria-hidden="true">
                <img src={conn.logo} alt={`${conn.name} logo`} width="28" height="28" />
              </div>
              <div>
                <h3 className="connection-title">{conn.name}</h3>
                <p className="connection-description">{conn.description}</p>
              </div>
            </div>
            <div className="connection-status-row">
              <span
                className={`status-pill ${conn.connected ? "green" : conn.comingSoon ? "yellow" : "grey"}`}
              >
                {conn.connected ? "Connected" : conn.comingSoon ? "Coming soon" : "Not connected"}
              </span>
            </div>
          </button>
        ))}
      </div>
      {!hasAny && (
        <p style={{ marginTop: 16 }}>
          No connections available.{" "}
          <Link href="/connections" className="app-link">
            Connect a data source first
          </Link>
          .
        </p>
      )}
    </div>
  );
}

const INDUSTRIES = [
  { value: "", label: "Select industry..." },
  { value: "ecommerce", label: "E-commerce" },
  { value: "saas", label: "SaaS / B2B" },
  { value: "lead_gen", label: "Lead generation" },
  { value: "agency", label: "Agency / multi-client" },
  { value: "other", label: "Other" },
];

function StepAdsAccount({ accounts, loading, fetchError, selectedId, onChange }) {
  if (loading) {
    return (
      <div className="generate-field" style={{ marginBottom: 20 }}>
        <span className="app-subtle">Google Ads accounts</span>
        <p className="app-subtle" style={{ marginTop: 8, marginBottom: 0 }}>
          Loading accounts…
        </p>
      </div>
    );
  }
  if (fetchError) {
    return (
      <div className="generate-alert generate-alert--error" role="alert" style={{ marginBottom: 20 }}>
        <h3 className="generate-alert-title">Could not load Google Ads accounts</h3>
        <pre className="generate-alert-detail">{fetchError}</pre>
        <p className="generate-alert-help">
          Check that the backend can reach the Google Ads API, your developer token is configured, and your
          refresh token is still valid.
        </p>
        <Link href="/connections" className="app-link generate-alert-link">
          Review Google Ads connection
        </Link>
      </div>
    );
  }
  if (!accounts.length) {
    return (
      <div className="generate-alert generate-alert--error" role="alert" style={{ marginBottom: 20 }}>
        <h3 className="generate-alert-title">No Google Ads accounts returned</h3>
        <p className="generate-alert-help">
          The API responded with an empty account list (
          <code className="generate-alert-code">{"{ \"accounts\": [] }"}</code>
          ). You can still see accounts in the Google Ads UI while the API returns nothing.
        </p>
        <ul className="generate-alert-list">
          <li>
            Developer token is still in <strong>Test</strong> access (production accounts are often blocked until
            the token is approved).
          </li>
          <li>
            Sub-accounts under a manager may need <code className="generate-alert-code">GOOGLE_ADS_LOGIN_CUSTOMER_ID</code>{" "}
            set to your MCC ID on the server.
          </li>
          <li>You completed OAuth with a different Google user than the one that owns those Ads accounts.</li>
        </ul>
        <p className="generate-alert-help">
          <Link href="/connections" className="app-link generate-alert-link">
            Reconnect Google Ads
          </Link>
          {" · "}
          Check backend logs for warnings when listing accounts.
        </p>
      </div>
    );
  }
  return (
    <label className="generate-field" style={{ marginBottom: 16 }}>
      <span className="app-subtle">Google Ads account</span>
      <select
        className="app-input"
        value={selectedId}
        onChange={(e) => onChange(e.target.value)}
      >
        {accounts.map((account) => (
          <option key={normalizeCustomerId(account.customer_id)} value={normalizeCustomerId(account.customer_id)}>
            {account.descriptive_name} ({account.customer_id})
            {account.manager ? " — MCC" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

const DATE_PRESET_OPTIONS = [
  { key: "7", label: "Last 7 days", daysBack: 7 },
  { key: "30", label: "Last 30 days", daysBack: 30 },
  { key: "90", label: "Last 90 days", daysBack: 90 },
  { key: "custom", label: "Custom", daysBack: null },
];

function goalDisplayLabel(goalKey, customGoalText) {
  if (goalKey === "custom") return customGoalText.trim() || "Custom goal";
  return GOALS.find((g) => g.key === goalKey)?.label ?? goalKey;
}

function dateRangeSummary(datePreset, dateFrom, dateTo) {
  const preset = DATE_PRESET_OPTIONS.find((o) => o.key === datePreset);
  if (datePreset !== "custom" && preset) {
    return `${preset.label} (${dateFrom} → ${dateTo})`;
  }
  return `${dateFrom} → ${dateTo}`;
}

function StepGoal({
  goal,
  onGoalChange,
  customGoal,
  onCustomGoalChange,
  context,
  onContextChange,
  dateFrom,
  dateTo,
  onDateFromChange,
  onDateToChange,
  datePreset,
  onDatePresetChange,
  businessContext,
  onBusinessContextChange,
}) {
  return (
    <div className="generate-step">
      <h2 className="generate-step-title">What do you want to analyze?</h2>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 16 }}>
        Select a goal and provide any additional context for a more targeted report.
      </p>

      <div className="goal-grid">
        {GOALS.map((g) => (
          <button
            key={g.key}
            type="button"
            className={`goal-card${goal === g.key ? " goal-card--selected" : ""}`}
            onClick={() => onGoalChange(g.key)}
            aria-pressed={goal === g.key}
          >
            <span className="goal-icon" aria-hidden="true">{g.icon}</span>
            <div>
              <p className="goal-title">{g.label}</p>
              <p className="goal-desc">{g.description}</p>
            </div>
            <span className="goal-radio" aria-hidden="true" />
          </button>
        ))}
      </div>

      {goal === "custom" && (
        <label className="generate-field" style={{ marginTop: 14 }}>
          <span className="app-subtle">Custom goal</span>
          <input
            type="text"
            className="app-input"
            placeholder="e.g. Identify top-performing audiences"
            value={customGoal}
            onChange={(e) => onCustomGoalChange(e.target.value)}
          />
        </label>
      )}

      <div style={{ marginTop: 18 }}>
        <span className="app-subtle" style={{ display: "block", marginBottom: 8 }}>
          Business context (optional)
        </span>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label className="generate-field">
            <span className="app-subtle">Industry</span>
            <select
              className="app-input"
              value={businessContext.industry}
              onChange={(e) => onBusinessContextChange({ ...businessContext, industry: e.target.value })}
            >
              {INDUSTRIES.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
          <div className="connections-date-row">
            <label className="generate-field">
              <span className="app-subtle">Target CPA ($)</span>
              <input
                type="number"
                className="app-input"
                min="0"
                step="0.01"
                placeholder="e.g. 50"
                value={businessContext.target_cpa || ""}
                onChange={(e) => onBusinessContextChange({ ...businessContext, target_cpa: parseFloat(e.target.value) || 0 })}
              />
            </label>
            <label className="generate-field">
              <span className="app-subtle">Target ROAS (x)</span>
              <input
                type="number"
                className="app-input"
                min="0"
                step="0.1"
                placeholder="e.g. 3.0"
                value={businessContext.target_roas || ""}
                onChange={(e) => onBusinessContextChange({ ...businessContext, target_roas: parseFloat(e.target.value) || 0 })}
              />
            </label>
          </div>
        </div>
      </div>

      <label className="generate-field" style={{ marginTop: 14 }}>
        <span className="app-subtle">Additional context (optional)</span>
        <textarea
          className="app-input app-textarea"
          rows={3}
          placeholder="e.g. We just launched a new campaign last Monday, focus on early signals..."
          value={context}
          onChange={(e) => onContextChange(e.target.value)}
        />
      </label>

      <div style={{ marginTop: 18 }}>
        <span className="app-subtle" style={{ display: "block", marginBottom: 8 }}>
          Date range
        </span>
        <div className="date-preset-row" role="group" aria-label="Date range preset">
          {DATE_PRESET_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              className={`date-preset-chip${datePreset === opt.key ? " date-preset-chip--selected" : ""}`}
              aria-pressed={datePreset === opt.key}
              onClick={() => onDatePresetChange(opt.key)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {datePreset === "custom" && (
          <div className="connections-date-row" style={{ marginTop: 12 }}>
            <label className="generate-field">
              <span className="app-subtle">Start date</span>
              <input
                type="date"
                className="app-input"
                value={dateFrom}
                onChange={(e) => onDateFromChange(e.target.value)}
              />
            </label>
            <label className="generate-field">
              <span className="app-subtle">End date</span>
              <input
                type="date"
                className="app-input"
                value={dateTo}
                onChange={(e) => onDateToChange(e.target.value)}
              />
            </label>
          </div>
        )}
      </div>
    </div>
  );
}

function StepReview({
  selectedConnectionIds,
  connections,
  needsAdsAccount,
  accountDescriptiveName,
  accountCustomerId,
  goalKey,
  customGoal,
  dateFrom,
  dateTo,
  datePreset,
}) {
  const sourceNames = selectedConnectionIds
    .map((id) => connections.find((c) => c.id === id)?.name)
    .filter(Boolean);
  const accountLine =
    needsAdsAccount && accountCustomerId
      ? `${accountDescriptiveName || "Account"} (${accountCustomerId})`
      : needsAdsAccount
        ? "—"
        : null;

  return (
    <div className="generate-step">
      <h2 className="generate-step-title">Review and generate</h2>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 16 }}>
        Confirm the details below. This starts fetching data and building your report.
      </p>
      <div className="generate-review">
        <div>
          <span className="generate-review-label">Data sources</span>
          <p className="generate-review-value">
            {sourceNames.length ? sourceNames.join(", ") : "—"}
          </p>
        </div>
        {accountLine !== null && (
          <div>
            <span className="generate-review-label">Google Ads account</span>
            <p className="generate-review-value">{accountLine}</p>
          </div>
        )}
        <div>
          <span className="generate-review-label">Goal</span>
          <p className="generate-review-value">{goalDisplayLabel(goalKey, customGoal)}</p>
        </div>
        <div>
          <span className="generate-review-label">Date range</span>
          <p className="generate-review-value">{dateRangeSummary(datePreset, dateFrom, dateTo)}</p>
        </div>
      </div>
    </div>
  );
}

const ANALYZING_LINES = [
  "Connecting to Google Ads...",
  "Fetching campaign data...",
  "Analyzing performance...",
  "Generating insights...",
];

function StepAnalyzing({ error, onRetry }) {
  const [visibleLines, setVisibleLines] = useState([]);
  const timersRef = useRef([]);

  useEffect(() => {
    setVisibleLines([]);
    const timers = [];
    ANALYZING_LINES.forEach((_, i) => {
      timers.push(
        setTimeout(() => {
          setVisibleLines((prev) => [...prev, i]);
        }, i * 600)
      );
    });
    timersRef.current = timers;
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="generate-step generate-step--analyzing">
      <h2 className="generate-step-title">Generating your report...</h2>
      <div className="analyzing-lines">
        {ANALYZING_LINES.map((line, i) => (
          <div
            key={i}
            className={`analyzing-line${visibleLines.includes(i) ? " visible" : ""}`}
          >
            <span className="analyzing-spinner" />
            {line}
          </div>
        ))}
      </div>
      {error && (
        <div style={{ marginTop: 20 }}>
          <pre className="generate-error">{error}</pre>
          <button type="button" className="btn btn-ghost" onClick={onRetry} style={{ marginTop: 10 }}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

function StepReport({ report, onSave, onRestart, saved }) {
  // Unwrap envelope: brief from connector slot, synthesis alongside
  const brief = report.briefs?.google_ads ?? report;
  const synthesis = report.synthesis ?? null;

  return (
    <div className="generate-step">
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 20 }}>
        <button
          type="button"
          className="btn btn-orange"
          onClick={onSave}
          disabled={saved}
        >
          {saved ? "Saved to Reports" : "Save to Reports"}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onRestart}>
          Generate another
        </button>
      </div>
      <GoogleAdsReport brief={brief} synthesis={synthesis} />
    </div>
  );
}

export default function GeneratePage() {
  const router = useRouter();

  // Wizard state
  const [step, setStep] = useState(1);
  const [selectedConnections, setSelectedConnections] = useState([]);
  const [goal, setGoal] = useState("");
  const [customGoal, setCustomGoal] = useState("");
  const [context, setContext] = useState("");
  const initialRange = defaultDateRange();
  const [dateFrom, setDateFrom] = useState(initialRange.from);
  const [dateTo, setDateTo] = useState(initialRange.to);
  const [datePreset, setDatePreset] = useState("7");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [report, setReport] = useState(null);
  const [saved, setSaved] = useState(false);
  const [businessContext, setBusinessContext] = useState({ industry: "", target_cpa: 0, target_roas: 0 });

  // Google Ads account (loaded on step 2 when Google Ads is selected)
  const [adsAccounts, setAdsAccounts] = useState([]);
  const [adsAccountsLoading, setAdsAccountsLoading] = useState(false);
  const [adsAccountsError, setAdsAccountsError] = useState(null);
  const [selectedAdsCustomerId, setSelectedAdsCustomerId] = useState("");
  const [analyzingKey, setAnalyzingKey] = useState(0);

  // Detect connected sources (Google Ads = OAuth token only; account chosen in generate flow)
  const [connections, setConnections] = useState([]);
  useEffect(() => {
    const hasGadsToken = !!sessionStorage.getItem("gads_refresh_token");
    setConnections([
      {
        id: "google_ads",
        name: "Google Ads",
        description: "Campaign performance, spend, conversions, ROAS.",
        logo: "https://upload.wikimedia.org/wikipedia/commons/c/c7/Google_Ads_logo.svg",
        connected: hasGadsToken,
        comingSoon: false,
      },
      {
        id: "search_console",
        name: "Google Search Console",
        description: "Organic search queries, clicks, impressions.",
        logo: "https://upload.wikimedia.org/wikipedia/commons/d/dc/Google_Search_Console_logo.svg",
        connected: false,
        comingSoon: true,
      },
      {
        id: "analytics",
        name: "Google Analytics",
        description: "Website traffic, sessions, engagement.",
        logo: "https://upload.wikimedia.org/wikipedia/commons/7/77/GAnalytics.svg",
        connected: false,
        comingSoon: true,
      },
    ]);
  }, []);

  useEffect(() => {
    if (step !== 2 || !selectedConnections.includes("google_ads")) return undefined;
    const token = sessionStorage.getItem("gads_refresh_token");
    if (!token) return undefined;

    let cancelled = false;
    setAdsAccountsLoading(true);
    setAdsAccountsError(null);

    fetchGoogleAdsAccounts(token)
      .then((items) => {
        if (cancelled) return;
        setAdsAccounts(items);
        const storedRaw = sessionStorage.getItem("gads_customer_id");
        const stored = normalizeCustomerId(storedRaw);
        const match = stored && items.find((a) => normalizeCustomerId(a.customer_id) === stored);
        const pick = match ? normalizeCustomerId(match.customer_id) : normalizeCustomerId(items[0]?.customer_id);
        setSelectedAdsCustomerId(pick);
        if (pick) sessionStorage.setItem("gads_customer_id", pick);
      })
      .catch((err) => {
        if (!cancelled) {
          setAdsAccountsError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setAdsAccountsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [step, selectedConnections]);

  function onAdsAccountChange(customerId) {
    const id = normalizeCustomerId(customerId);
    setSelectedAdsCustomerId(id);
    if (id) sessionStorage.setItem("gads_customer_id", id);
    else sessionStorage.removeItem("gads_customer_id");
  }

  function toggleConnection(id) {
    setSelectedConnections((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]
    );
  }

  function applyDatePreset(preset) {
    setDatePreset(preset);
    if (preset !== "custom") {
      const days = preset === "7" ? 7 : preset === "30" ? 30 : 90;
      const { from, to } = rangeEndingToday(days);
      setDateFrom(from);
      setDateTo(to);
    }
  }

  async function handleGenerate() {
    setAnalyzingKey((k) => k + 1);
    setStep(4);
    setStatus("loading");
    setError(null);

    const refreshToken = sessionStorage.getItem("gads_refresh_token") || "";
    const cid = normalizeCustomerId(selectedAdsCustomerId);
    const account = adsAccounts.find((a) => normalizeCustomerId(a.customer_id) === cid);

    try {
      const data = await generateReport({
        connections: selectedConnections,
        goal: goal === "custom" ? "custom" : goal,
        custom_goal: goal === "custom" ? customGoal.trim() : "",
        context,
        date_from: dateFrom,
        date_to: dateTo,
        refresh_token: refreshToken,
        customer_id: cid,
        account_name: account?.descriptive_name ?? "",
        currency_code: account?.currency_code || "USD",
        business_context: businessContext,
      });
      setReport(data);
      setStatus("success");
      setStep(5);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  function handleSave() {
    if (!report) return;
    const slug = generateSlug(selectedAdsCustomerId || sessionStorage.getItem("gads_customer_id") || "", dateTo);
    saveLocalReport(slug, report);
    setSaved(true);
    setTimeout(() => router.push("/reports"), 400);
  }

  function handleRestart() {
    setStep(1);
    setSelectedConnections([]);
    setGoal("");
    setCustomGoal("");
    setContext("");
    const r = defaultDateRange();
    setDateFrom(r.from);
    setDateTo(r.to);
    setDatePreset("7");
    setStatus("idle");
    setError(null);
    setReport(null);
    setSaved(false);
    setBusinessContext({ industry: "", target_cpa: 0, target_roas: 0 });
    setAdsAccounts([]);
    setSelectedAdsCustomerId("");
    setAdsAccountsError(null);
    setAnalyzingKey(0);
  }

  function handleRetry() {
    handleGenerate();
  }

  const canProceedStep1 = selectedConnections.length > 0;
  const needsAdsAccount = selectedConnections.includes("google_ads");
  const selectedIdNorm = normalizeCustomerId(selectedAdsCustomerId);
  const adsAccountOk =
    !needsAdsAccount ||
    (!adsAccountsLoading &&
      !adsAccountsError &&
      !!selectedIdNorm &&
      adsAccounts.some((a) => normalizeCustomerId(a.customer_id) === selectedIdNorm));
  const canProceedConfigure =
    goal &&
    (goal !== "custom" || customGoal.trim()) &&
    dateFrom &&
    dateTo &&
    adsAccountOk;

  function configureBlockedReason() {
    if (!goal) return "Select an analysis goal above to continue.";
    if (goal === "custom" && !customGoal.trim()) return "Enter a short description for your custom goal.";
    if (!dateFrom || !dateTo) return "Choose a date range (or pick Custom and set dates).";
    if (needsAdsAccount && adsAccountsLoading) return "Wait for Google Ads accounts to finish loading.";
    if (needsAdsAccount && adsAccountsError) return "Fix the Google Ads account error above, then try again.";
    if (needsAdsAccount && !adsAccounts.length) return "No Google Ads accounts available — connect or fix access first.";
    if (needsAdsAccount && !adsAccountOk) return "Select a Google Ads account from the dropdown.";
    return "";
  }

  const cidForReview = normalizeCustomerId(selectedAdsCustomerId);
  const accountForReview = adsAccounts.find((a) => normalizeCustomerId(a.customer_id) === cidForReview);

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
        <h1 style={{ marginTop: 0, marginBottom: 0 }}>Generate Report</h1>
      </div>

      <ProgressDots step={step} />

      {step === 1 && (
        <>
          <StepConnections
            connections={connections}
            selected={selectedConnections}
            onToggle={toggleConnection}
          />
          <div style={{ marginTop: 16 }}>
            <button
              type="button"
              className="btn btn-orange"
              disabled={!canProceedStep1}
              onClick={() => setStep(2)}
            >
              Next
            </button>
          </div>
        </>
      )}

      {step === 2 && (
        <>
          {selectedConnections.includes("google_ads") && (
            <StepAdsAccount
              accounts={adsAccounts}
              loading={adsAccountsLoading}
              fetchError={adsAccountsError}
              selectedId={selectedAdsCustomerId}
              onChange={onAdsAccountChange}
            />
          )}
          <StepGoal
            goal={goal}
            onGoalChange={setGoal}
            customGoal={customGoal}
            onCustomGoalChange={setCustomGoal}
            context={context}
            onContextChange={setContext}
            dateFrom={dateFrom}
            dateTo={dateTo}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
            datePreset={datePreset}
            onDatePresetChange={applyDatePreset}
            businessContext={businessContext}
            onBusinessContextChange={setBusinessContext}
          />
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button type="button" className="btn btn-ghost" onClick={() => setStep(1)}>
              Back
            </button>
            <button
              type="button"
              className="btn btn-orange"
              disabled={!canProceedConfigure}
              onClick={() => setStep(3)}
            >
              Next
            </button>
          </div>
          {!canProceedConfigure && (
            <p className="app-subtle generate-step-hint" role="status">
              {configureBlockedReason()}
            </p>
          )}
        </>
      )}

      {step === 3 && (
        <>
          <StepReview
            selectedConnectionIds={selectedConnections}
            connections={connections}
            needsAdsAccount={needsAdsAccount}
            accountDescriptiveName={accountForReview?.descriptive_name ?? ""}
            accountCustomerId={cidForReview}
            goalKey={goal}
            customGoal={customGoal}
            dateFrom={dateFrom}
            dateTo={dateTo}
            datePreset={datePreset}
          />
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button type="button" className="btn btn-ghost" onClick={() => setStep(2)}>
              Back
            </button>
            <button
              type="button"
              className="btn btn-orange"
              disabled={!canProceedConfigure}
              onClick={handleGenerate}
            >
              Generate
            </button>
          </div>
          {!canProceedConfigure && (
            <p className="app-subtle generate-step-hint" role="status">
              {configureBlockedReason()}
            </p>
          )}
        </>
      )}

      {step === 4 && <StepAnalyzing key={analyzingKey} error={error} onRetry={handleRetry} />}

      {step === 5 && report && (
        <StepReport
          report={report}
          onSave={handleSave}
          onRestart={handleRestart}
          saved={saved}
        />
      )}
    </section>
  );
}
