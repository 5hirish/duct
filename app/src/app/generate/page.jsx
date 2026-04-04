"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import GoogleAdsReport from "../../components/GoogleAdsReport";
import { generateReport } from "../../lib/api";
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

function defaultDateTo() {
  return new Date().toISOString().slice(0, 10);
}

function defaultDateFrom() {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

function ProgressDots({ step }) {
  return (
    <div className="generate-progress">
      {[1, 2, 3, 4].map((n) => (
        <span
          key={n}
          className={`generate-dot${n < step ? " done" : ""}${n === step ? " active" : ""}`}
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

function StepGoal({ goal, onGoalChange, customGoal, onCustomGoalChange, context, onContextChange, dateFrom, dateTo, onDateFromChange, onDateToChange, businessContext, onBusinessContextChange }) {
  const [showBizCtx, setShowBizCtx] = useState(false);
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

      <button
        type="button"
        className="btn btn-ghost"
        style={{ marginTop: 14, fontSize: 13, padding: "6px 10px" }}
        onClick={() => setShowBizCtx((prev) => !prev)}
      >
        {showBizCtx ? "Hide" : "Show"} business context (optional)
      </button>

      {showBizCtx && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 10 }}>
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
      )}

      <div className="connections-date-row" style={{ marginTop: 14 }}>
        <label className="generate-field">
          <span className="app-subtle">Date from</span>
          <input
            type="date"
            className="app-input"
            value={dateFrom}
            onChange={(e) => onDateFromChange(e.target.value)}
          />
        </label>
        <label className="generate-field">
          <span className="app-subtle">Date to</span>
          <input
            type="date"
            className="app-input"
            value={dateTo}
            onChange={(e) => onDateToChange(e.target.value)}
          />
        </label>
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
      <GoogleAdsReport payload={report} />
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
  const [dateFrom, setDateFrom] = useState(defaultDateFrom);
  const [dateTo, setDateTo] = useState(defaultDateTo);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [report, setReport] = useState(null);
  const [saved, setSaved] = useState(false);
  const [businessContext, setBusinessContext] = useState({ industry: "", target_cpa: 0, target_roas: 0 });

  // Detect connected sources
  const [connections, setConnections] = useState([]);
  useEffect(() => {
    const hasGadsToken = !!sessionStorage.getItem("gads_refresh_token");
    const hasGadsAccount = !!sessionStorage.getItem("gads_customer_id");
    setConnections([
      {
        id: "google_ads",
        name: "Google Ads",
        description: "Campaign performance, spend, conversions, ROAS.",
        logo: "https://upload.wikimedia.org/wikipedia/commons/c/c7/Google_Ads_logo.svg",
        connected: hasGadsToken && hasGadsAccount,
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

  function toggleConnection(id) {
    setSelectedConnections((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]
    );
  }

  async function handleGenerate() {
    setStep(3);
    setStatus("loading");
    setError(null);

    const refreshToken = sessionStorage.getItem("gads_refresh_token") || "";
    const customerId = sessionStorage.getItem("gads_customer_id") || "";

    try {
      const data = await generateReport({
        connections: selectedConnections,
        goal: goal === "custom" ? "custom" : goal,
        custom_goal: goal === "custom" ? customGoal.trim() : "",
        context,
        date_from: dateFrom,
        date_to: dateTo,
        refresh_token: refreshToken,
        customer_id: customerId,
        account_name: "",
        currency_code: "USD",
        business_context: businessContext,
      });
      setReport(data);
      setStatus("success");
      setStep(4);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  function handleSave() {
    if (!report) return;
    const customerId = sessionStorage.getItem("gads_customer_id") || "";
    const slug = generateSlug(customerId, dateTo);
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
    setDateFrom(defaultDateFrom());
    setDateTo(defaultDateTo());
    setStatus("idle");
    setError(null);
    setReport(null);
    setSaved(false);
    setBusinessContext({ industry: "", target_cpa: 0, target_roas: 0 });
  }

  function handleRetry() {
    handleGenerate();
  }

  const canProceedStep1 = selectedConnections.length > 0;
  const canProceedStep2 =
    goal && (goal !== "custom" || customGoal.trim()) && dateFrom && dateTo;

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
              disabled={!canProceedStep2}
              onClick={handleGenerate}
            >
              Generate
            </button>
          </div>
        </>
      )}

      {step === 3 && <StepAnalyzing error={error} onRetry={handleRetry} />}

      {step === 4 && report && (
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
