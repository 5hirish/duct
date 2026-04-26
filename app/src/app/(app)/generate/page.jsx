"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import GoogleAdsReport from "../../../components/GoogleAdsReport";
import {
  fetchGa4Properties,
  fetchGoogleAdsAccounts,
  fetchGscSites,
  generateReportStream,
} from "../../../lib/api";
import { saveLocalReport, generateSlug } from "../../../lib/localReports";
import { getActiveProject, getActiveProjectId } from "../../../lib/projects";
import { fetchModes, getModeByKey, FALLBACK_MODES, DEFAULT_MODE_KEY } from "../../../lib/modes";
import { Button } from "@/components/ui/button";

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

function normalizeGa4PropertyId(id) {
  if (id === null || id === undefined) return "";
  return String(id).trim();
}

function normalizeGscSiteUrl(url) {
  if (url === null || url === undefined) return "";
  return String(url).trim();
}

/** Map wizard step (1–6) to one of four progress phases: sources → configure → generating → report. */
function progressPhase(step) {
  if (step <= 1) return 1;
  if (step <= 4) return 2;
  if (step === 5) return 3;
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

function StepConnections({ connections, selected, onToggle, locked = false }) {
  const hasAny = connections.some((c) => c.connected);

  return (
    <div className="generate-step">
      <h2 className="generate-step-title">Select your data sources</h2>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: locked ? 8 : 16 }}>
        {locked
          ? "Connections are pre-set for this intelligence mode."
          : "Choose which connected tools to include in your insight."}
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

function StepGa4Property({ properties, loading, fetchError, selectedId, onChange }) {
  const [query, setQuery] = useState("");

  if (loading) {
    return (
      <div className="generate-field" style={{ marginBottom: 20 }}>
        <span className="app-subtle">GA4 properties</span>
        <p className="app-subtle" style={{ marginTop: 8, marginBottom: 0 }}>
          Loading properties…
        </p>
      </div>
    );
  }
  if (fetchError) {
    return (
      <div className="generate-alert generate-alert--error" role="alert" style={{ marginBottom: 20 }}>
        <h3 className="generate-alert-title">Could not load GA4 properties</h3>
        <pre className="generate-alert-detail">{fetchError}</pre>
        <Link href="/connections" className="app-link generate-alert-link">
          Review Google Analytics connection
        </Link>
      </div>
    );
  }
  if (!properties.length) {
    return (
      <div className="generate-alert generate-alert--error" role="alert" style={{ marginBottom: 20 }}>
        <h3 className="generate-alert-title">No GA4 properties returned</h3>
        <p className="generate-alert-help">
          We could not find any GA4 properties for this Google user. Confirm this account has Analytics access.
        </p>
        <Link href="/connections" className="app-link generate-alert-link">
          Reconnect Google Analytics
        </Link>
      </div>
    );
  }

  function normalizeText(value) {
    return String(value || "").trim().toLowerCase();
  }

  const filteredProperties = properties.filter((property) => {
    const q = normalizeText(query);
    if (!q) return true;
    return (
      normalizeText(property.property_name).includes(q) ||
      normalizeText(property.account_name).includes(q) ||
      normalizeText(property.property_id).includes(q)
    );
  });

  return (
    <div className="generate-field" style={{ marginBottom: 16 }}>
      <span className="app-subtle" style={{ display: "block", marginBottom: 8 }}>
        GA4 property
      </span>
      <label className="sr-only" htmlFor="ga4-property-search">
        Search fetched GA4 properties
      </label>
      <input
        id="ga4-property-search"
        type="text"
        className="app-input"
        placeholder="Search properties (name, account, or ID)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      <div
        role="radiogroup"
        aria-label="GA4 property"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          maxHeight: 260,
          overflowY: "auto",
          padding: 10,
          border: "1px solid var(--border, rgba(255,255,255,0.12))",
          borderRadius: 10,
          background: "rgba(255,255,255,0.02)",
        }}
      >
        {filteredProperties.map((property) => {
          const propertyId = normalizeGa4PropertyId(property.property_id);
          const selected = selectedId === propertyId;
          return (
            <button
              key={propertyId}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(propertyId)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                width: "100%",
                padding: "10px 12px",
                borderRadius: 10,
                border: selected
                  ? "1px solid var(--color-primary, #4f46e5)"
                  : "1px solid var(--border, rgba(255,255,255,0.12))",
                background: selected ? "rgba(79,70,229,0.12)" : "transparent",
                color: "inherit",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <img
                  src="https://www.google.com/s2/favicons?domain=analytics.google.com&sz=32"
                  alt=""
                  width="16"
                  height="16"
                  style={{ borderRadius: 4, flexShrink: 0 }}
                />
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: "block", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {property.property_name}
                  </span>
                  <span
                    className="app-subtle"
                    style={{ display: "block", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis" }}
                  >
                    {property.account_name}
                  </span>
                </span>
              </span>
              <span className="status-pill grey" style={{ flexShrink: 0 }}>
                ID {propertyId}
              </span>
            </button>
          );
        })}
        {filteredProperties.length === 0 && (
          <p className="app-subtle" style={{ margin: 0, padding: "8px 2px" }}>
            No GA4 properties match "{query}".
          </p>
        )}
      </div>
    </div>
  );
}

function StepGscSite({ sites, loading, fetchError, selectedUrl, onChange }) {
  const [query, setQuery] = useState("");
  if (loading) {
    return (
      <div className="generate-field" style={{ marginBottom: 20 }}>
        <span className="app-subtle">Search Console sites</span>
        <p className="app-subtle" style={{ marginTop: 8, marginBottom: 0 }}>
          Loading sites…
        </p>
      </div>
    );
  }
  if (fetchError) {
    return (
      <div className="generate-alert generate-alert--error" role="alert" style={{ marginBottom: 20 }}>
        <h3 className="generate-alert-title">Could not load Search Console sites</h3>
        <pre className="generate-alert-detail">{fetchError}</pre>
        <Link href="/connections" className="app-link generate-alert-link">
          Review Search Console connection
        </Link>
      </div>
    );
  }
  if (!sites.length) {
    return (
      <div className="generate-alert generate-alert--error" role="alert" style={{ marginBottom: 20 }}>
        <h3 className="generate-alert-title">No Search Console sites returned</h3>
        <p className="generate-alert-help">
          We could not find any verified Search Console properties for this Google user.
        </p>
        <Link href="/connections" className="app-link generate-alert-link">
          Reconnect Search Console
        </Link>
      </div>
    );
  }
  function getDisplayHost(siteUrl) {
    if (!siteUrl) return "";
    if (siteUrl.startsWith("sc-domain:")) return siteUrl.replace("sc-domain:", "");
    try {
      return new URL(siteUrl).hostname;
    } catch {
      return siteUrl;
    }
  }

  function getFaviconUrl(siteUrl) {
    if (!siteUrl || siteUrl.startsWith("sc-domain:")) return "";
    const host = getDisplayHost(siteUrl);
    if (!host) return "";
    // Google-hosted favicon endpoint gives a clean, consistent icon.
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32`;
  }

  function permissionMeta(permissionLevel) {
    const level = String(permissionLevel || "").toLowerCase();
    const isVerified = level.includes("owner") || level.includes("full");
    return {
      isVerified,
      label: isVerified ? "Verified" : "Unverified",
      toneClass: isVerified ? "green" : "grey",
    };
  }

  const filteredSites = sites.filter((site) => {
    const url = normalizeGscSiteUrl(site.site_url);
    const host = getDisplayHost(url);
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (
      host.toLowerCase().includes(q) ||
      url.toLowerCase().includes(q)
    );
  });

  return (
    <div className="generate-field" style={{ marginBottom: 16 }}>
      <span className="app-subtle" style={{ display: "block", marginBottom: 8 }}>
        Search Console site
      </span>
      <label className="sr-only" htmlFor="gsc-site-search">
        Search fetched Search Console sites
      </label>
      <input
        id="gsc-site-search"
        type="text"
        className="app-input"
        placeholder="Search sites (domain, URL, or permission)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      <div
        role="radiogroup"
        aria-label="Search Console site"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          maxHeight: 260,
          overflowY: "auto",
          padding: 10,
          border: "1px solid var(--border, rgba(255,255,255,0.12))",
          borderRadius: 10,
          background: "rgba(255,255,255,0.02)",
        }}
      >
        {filteredSites.map((site) => {
          const url = normalizeGscSiteUrl(site.site_url);
          const host = getDisplayHost(url);
          const faviconUrl = getFaviconUrl(url);
          const selected = selectedUrl === url;
          const permission = permissionMeta(site.permission_level);

          return (
            <button
              key={url}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(url)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                width: "100%",
                padding: "10px 12px",
                borderRadius: 10,
                border: selected
                  ? "1px solid var(--color-primary, #4f46e5)"
                  : "1px solid var(--border, rgba(255,255,255,0.12))",
                background: selected ? "rgba(79,70,229,0.12)" : "transparent",
                color: "inherit",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                {faviconUrl ? (
                  <img
                    src={faviconUrl}
                    alt=""
                    width="16"
                    height="16"
                    style={{ borderRadius: 4, flexShrink: 0 }}
                  />
                ) : (
                  <span aria-hidden="true" style={{ fontSize: 14, lineHeight: 1, flexShrink: 0 }}>
                    🌐
                  </span>
                )}
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: "block", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {host}
                  </span>
                  <span className="app-subtle" style={{ display: "block", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {url}
                  </span>
                </span>
              </span>
              <span className={`status-pill ${permission.toneClass}`} style={{ flexShrink: 0 }}>
                {permission.isVerified ? "✓ " : ""}
                {permission.label}
              </span>
            </button>
          );
        })}
        {filteredSites.length === 0 && (
          <p className="app-subtle" style={{ margin: 0, padding: "8px 2px" }}>
            No sites match "{query}".
          </p>
        )}
      </div>
    </div>
  );
}

const DATE_PRESET_OPTIONS = [
  { key: "7", label: "Last 7 days", daysBack: 7 },
  { key: "30", label: "Last 30 days", daysBack: 30 },
  { key: "90", label: "Last 90 days", daysBack: 90 },
  { key: "custom", label: "Custom", daysBack: null },
];

function goalDisplayLabel(goalKey, customGoalText, goals = []) {
  if (goalKey === "custom") return customGoalText.trim() || "Custom goal";
  return goals.find((g) => g.key === goalKey)?.label ?? goalKey;
}

function dateRangeSummary(datePreset, dateFrom, dateTo) {
  const preset = DATE_PRESET_OPTIONS.find((o) => o.key === datePreset);
  if (datePreset !== "custom" && preset) {
    return `${preset.label} (${dateFrom} → ${dateTo})`;
  }
  return `${dateFrom} → ${dateTo}`;
}

function toPositiveNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) && value > 0 ? value : 0;
  if (typeof value === "string") {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }
  return 0;
}

function normalizeIndustryValue(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "";
  if (normalized === "ecommerce" || normalized.includes("retail")) return "ecommerce";
  if (normalized === "saas" || normalized.includes("software")) return "saas";
  if (normalized.includes("lead")) return "lead_gen";
  if (normalized.includes("agency")) return "agency";
  return "other";
}

function businessContextFromOrganicDraft() {
  return {
    primary_organic_kpi: "",
    monthly_organic_traffic_target: 0,
    primary_content_type: "",
    period_changes: "",
  };
}

function businessContextFromProfileDraft() {
  const draft = getActiveProject() || {};
  return {
    industry: normalizeIndustryValue(draft.company?.industry),
    monthly_budget: toPositiveNumber(draft.targets?.monthly_budget),
    target_cpa: toPositiveNumber(draft.targets?.target_cpa),
    target_roas: toPositiveNumber(draft.targets?.target_roas),
    primary_conversion_action: "",
    target_payback_days: 0,
    gross_margin_percent: 0,
    qualified_lead_value: 0,
    period_changes: "",
  };
}

function buildReportRoutine({
  selectedConnections,
  datePreset,
  dateFrom,
  dateTo,
  goal,
  customGoal,
  context,
  selectedAdsCustomerId,
  adsAccounts,
  selectedGa4PropertyId,
  ga4Properties,
  selectedGscSiteUrl,
  businessContext,
  mode = null,
}) {
  const customerId = normalizeCustomerId(selectedAdsCustomerId);
  const ga4PropertyId = normalizeGa4PropertyId(selectedGa4PropertyId);
  const gscSiteUrl = normalizeGscSiteUrl(selectedGscSiteUrl);
  const selectedAdsAccount = adsAccounts.find((a) => normalizeCustomerId(a.customer_id) === customerId);
  const selectedGa4Property = ga4Properties.find(
    (property) => normalizeGa4PropertyId(property.property_id) === ga4PropertyId
  );

  return {
    schema_version: 1,
    date_preset: datePreset,
    custom_date_from: datePreset === "custom" ? dateFrom : null,
    custom_date_to: datePreset === "custom" ? dateTo : null,
    goal,
    custom_goal: goal === "custom" ? customGoal.trim() : "",
    context,
    connections: selectedConnections,
    targets: {
      ...(selectedConnections.includes("google_ads")
        ? {
            google_ads: {
              customer_id: customerId,
              account_name: selectedAdsAccount?.descriptive_name ?? "",
              currency_code: selectedAdsAccount?.currency_code || "USD",
              login_customer_id: "",
            },
          }
        : {}),
      ...(selectedConnections.includes("ga4")
        ? {
            ga4: {
              property_id: ga4PropertyId,
              property_name: selectedGa4Property?.property_name ?? "",
            },
          }
        : {}),
      ...(selectedConnections.includes("gsc")
        ? {
            gsc: {
              site_url: gscSiteUrl,
            },
          }
        : {}),
    },
    business_context: businessContext,
    mode: mode || null,
  };
}

function profileContextFromDraft() {
  const draft = getActiveProject() || {};
  const growthStage = String(draft.targets?.growth_stage_milestone || "").replaceAll("_", " ");
  const lines = [];
  if (draft.company?.business_model) {
    lines.push(`Business model: ${draft.company.business_model}`);
  }
  if (draft.audience?.primary_segment) {
    lines.push(`Primary segment: ${draft.audience.primary_segment}`);
  }
  if (draft.targets?.north_star_metric) {
    lines.push(`North Star metric: ${draft.targets.north_star_metric}`);
  }
  if (draft.targets?.north_star_goal_window) {
    lines.push(`90-day success definition: ${draft.targets.north_star_goal_window}`);
  }
  if (growthStage) {
    lines.push(`Growth stage milestone: ${growthStage}`);
  }
  if (draft.targets?.north_star_constraints) {
    lines.push(`Primary constraints: ${draft.targets.north_star_constraints}`);
  }
  if (draft.targets?.growth_stage_context) {
    lines.push(`Stage context: ${draft.targets.growth_stage_context}`);
  }
  if (draft.competition?.compare_against) {
    lines.push(`Often compared against: ${draft.competition.compare_against}`);
  }
  if (draft.brand_channels?.growth_motions?.length) {
    lines.push(`Primary growth motions: ${draft.brand_channels.growth_motions.join(", ")}`);
  }
  if (draft.brand_channels?.context_notes) {
    lines.push(`Business context notes: ${draft.brand_channels.context_notes}`);
  }
  return lines.join("\n");
}

function StepGoal({
  goals,
  mode,
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
  showPaidTargets,
  businessContext,
  onBusinessContextChange,
}) {
  return (
    <div className="generate-step">
      <h2 className="generate-step-title">What do you want to analyze?</h2>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 16 }}>
        Select a goal and provide any additional context for a more targeted insight.
      </p>

      <div className="goal-grid">
        {(goals || []).map((g) => (
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
          {mode !== "organic_growth" && (
            <label className="generate-field">
              <span className="app-subtle">Industry</span>
              <select
                className="app-input"
                value={businessContext.industry || ""}
                onChange={(e) => onBusinessContextChange({ ...businessContext, industry: e.target.value })}
              >
                {INDUSTRIES.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </label>
          )}
          {mode === "organic_growth" && (
            <>
              <label className="generate-field">
                <span className="app-subtle">Primary organic KPI</span>
                <select
                  className="app-input"
                  value={businessContext.primary_organic_kpi || ""}
                  onChange={(e) => onBusinessContextChange({ ...businessContext, primary_organic_kpi: e.target.value })}
                >
                  <option value="">Select primary KPI...</option>
                  <option value="organic_traffic">Organic Traffic</option>
                  <option value="keyword_rankings">Keyword Rankings</option>
                  <option value="backlinks">Backlinks</option>
                  <option value="conversions_from_organic">Conversions from Organic</option>
                </select>
              </label>
              <label className="generate-field">
                <span className="app-subtle">Monthly organic traffic target (optional)</span>
                <input
                  type="number"
                  className="app-input"
                  min="0"
                  step="1"
                  placeholder="e.g. 10000"
                  value={businessContext.monthly_organic_traffic_target || ""}
                  onChange={(e) => onBusinessContextChange({ ...businessContext, monthly_organic_traffic_target: parseFloat(e.target.value) || 0 })}
                />
              </label>
              <label className="generate-field">
                <span className="app-subtle">Primary content type</span>
                <select
                  className="app-input"
                  value={businessContext.primary_content_type || ""}
                  onChange={(e) => onBusinessContextChange({ ...businessContext, primary_content_type: e.target.value })}
                >
                  <option value="">Select content type...</option>
                  <option value="blog_articles">Blog/Articles</option>
                  <option value="product_pages">Product Pages</option>
                  <option value="landing_pages">Landing Pages</option>
                  <option value="docs_help">Docs/Help</option>
                </select>
              </label>
              <label className="generate-field">
                <span className="app-subtle">What changed recently? (optional)</span>
                <textarea
                  className="app-input app-textarea"
                  rows={2}
                  placeholder="e.g. Published 10 new articles, migrated to new CMS, added hreflang tags."
                  value={businessContext.period_changes || ""}
                  onChange={(e) => onBusinessContextChange({ ...businessContext, period_changes: e.target.value })}
                />
              </label>
            </>
          )}
          {showPaidTargets && (
            <>
              <label className="generate-field">
                <span className="app-subtle">Primary conversion action</span>
                <input
                  type="text"
                  className="app-input"
                  placeholder="e.g. Demo booked, Trial started, Purchase"
                  value={businessContext.primary_conversion_action || ""}
                  onChange={(e) => onBusinessContextChange({ ...businessContext, primary_conversion_action: e.target.value })}
                />
              </label>
              <label className="generate-field">
                <span className="app-subtle">Monthly budget ($)</span>
                <input
                  type="number"
                  className="app-input"
                  min="0"
                  step="0.01"
                  placeholder="e.g. 5000"
                  value={businessContext.monthly_budget || ""}
                  onChange={(e) => onBusinessContextChange({ ...businessContext, monthly_budget: parseFloat(e.target.value) || 0 })}
                />
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
              <div className="connections-date-row">
                <label className="generate-field">
                  <span className="app-subtle">Target payback (days)</span>
                  <input
                    type="number"
                    className="app-input"
                    min="0"
                    step="1"
                    placeholder="e.g. 90"
                    value={businessContext.target_payback_days || ""}
                    onChange={(e) => onBusinessContextChange({ ...businessContext, target_payback_days: parseFloat(e.target.value) || 0 })}
                  />
                </label>
                <label className="generate-field">
                  <span className="app-subtle">Gross margin (%)</span>
                  <input
                    type="number"
                    className="app-input"
                    min="0"
                    max="100"
                    step="1"
                    placeholder="e.g. 70"
                    value={businessContext.gross_margin_percent || ""}
                    onChange={(e) => onBusinessContextChange({ ...businessContext, gross_margin_percent: parseFloat(e.target.value) || 0 })}
                  />
                </label>
                <label className="generate-field">
                  <span className="app-subtle">Qualified lead value ($)</span>
                  <input
                    type="number"
                    className="app-input"
                    min="0"
                    step="1"
                    placeholder="e.g. 1200"
                    value={businessContext.qualified_lead_value || ""}
                    onChange={(e) => onBusinessContextChange({ ...businessContext, qualified_lead_value: parseFloat(e.target.value) || 0 })}
                  />
                </label>
              </div>
              <p className="app-subtle" style={{ marginTop: 2, marginBottom: 0 }}>
                Add at least one economic guardrail above to improve ROI recommendations.
              </p>
              <label className="generate-field">
                <span className="app-subtle">What changed during this period? (optional)</span>
                <textarea
                  className="app-input app-textarea"
                  rows={2}
                  placeholder="e.g. Switched bid strategy, launched new offer, changed landing pages, tracking updates."
                  value={businessContext.period_changes || ""}
                  onChange={(e) => onBusinessContextChange({ ...businessContext, period_changes: e.target.value })}
                />
              </label>
            </>
          )}
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
  needsGa4Property,
  needsGscSite,
  accountDescriptiveName,
  accountCustomerId,
  ga4PropertyName,
  ga4PropertyId,
  gscSiteUrl,
  goalKey,
  customGoal,
  goals,
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
  const ga4Line =
    needsGa4Property && ga4PropertyId
      ? `${ga4PropertyName || "Property"} (${ga4PropertyId})`
      : needsGa4Property
        ? "—"
        : null;
  const gscLine = needsGscSite ? (gscSiteUrl || "—") : null;

  return (
    <div className="generate-step">
      <h2 className="generate-step-title">Review and generate insight</h2>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 16 }}>
        Confirm the details below. This starts fetching data and building your insight.
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
        {ga4Line !== null && (
          <div>
            <span className="generate-review-label">GA4 property</span>
            <p className="generate-review-value">{ga4Line}</p>
          </div>
        )}
        {gscLine !== null && (
          <div>
            <span className="generate-review-label">Search Console site</span>
            <p className="generate-review-value">{gscLine}</p>
          </div>
        )}
        <div>
          <span className="generate-review-label">Goal</span>
          <p className="generate-review-value">{goalDisplayLabel(goalKey, customGoal, goals)}</p>
        </div>
        <div>
          <span className="generate-review-label">Date range</span>
          <p className="generate-review-value">{dateRangeSummary(datePreset, dateFrom, dateTo)}</p>
        </div>
      </div>
    </div>
  );
}

const PIPELINE_STEPS = [
  { id: "collect_source_data", label: "Collecting source data", connectorScoped: true },
  { id: "normalize_connector_outputs", label: "Normalizing connector outputs", connectorScoped: true },
  { id: "supplementary_fetch", label: "Fetching supplementary insights", connectorScoped: false },
  { id: "synthesize_report", label: "Synthesizing recommendations", connectorScoped: false },
  { id: "assemble_report", label: "Finalizing report", connectorScoped: false },
];

const STEP_STATUS = {
  pending: "pending",
  running: "running",
  success: "success",
  error: "error",
};

function stepStatusKey(stepId, connectorId = "__group") {
  return `${stepId}:${connectorId}`;
}

function statusPriority(status) {
  if (status === STEP_STATUS.error) return 4;
  if (status === STEP_STATUS.running) return 3;
  if (status === STEP_STATUS.success) return 2;
  return 1;
}

function bestStatus(statuses) {
  if (!statuses.length) return STEP_STATUS.pending;
  return statuses
    .slice()
    .sort((a, b) => statusPriority(b) - statusPriority(a))[0];
}

function StepStatusIcon({ status }) {
  if (status === STEP_STATUS.running) {
    return <span className="pipeline-step-icon pipeline-step-icon--spinner" aria-hidden="true" />;
  }
  if (status === STEP_STATUS.success) {
    return <span className="pipeline-step-icon pipeline-step-icon--success" aria-hidden="true">✓</span>;
  }
  if (status === STEP_STATUS.error) {
    return <span className="pipeline-step-icon pipeline-step-icon--error" aria-hidden="true">!</span>;
  }
  return <span className="pipeline-step-icon pipeline-step-icon--pending" aria-hidden="true" />;
}

function connectorLabel(connectorId, connections) {
  return connections.find((c) => c.id === connectorId)?.name ?? connectorId;
}

function createInitialPipelineStatus(selectedConnectorIds) {
  const base = {};
  PIPELINE_STEPS.forEach((step) => {
    base[stepStatusKey(step.id)] = STEP_STATUS.pending;
    selectedConnectorIds.forEach((connectorId) => {
      base[stepStatusKey(step.id, connectorId)] = STEP_STATUS.pending;
    });
  });
  return base;
}

function StepAnalyzing({
  error,
  onRetry,
  statusByKey,
  selectedConnections,
  connections,
}) {
  const multiConnector = selectedConnections.length > 1;

  return (
    <div className="generate-step generate-step--analyzing">
      <h2 className="generate-step-title">Generating your insight...</h2>
      <div className="pipeline-steps">
        {PIPELINE_STEPS.map((step) => {
          const connectorStatuses = selectedConnections.map((connectorId) => ({
            connectorId,
            status: statusByKey[stepStatusKey(step.id, connectorId)] || STEP_STATUS.pending,
          }));
          const groupStatus = step.connectorScoped
            ? bestStatus(connectorStatuses.map((item) => item.status))
            : (statusByKey[stepStatusKey(step.id)] || STEP_STATUS.pending);

          return (
            <div key={step.id} className="pipeline-step-group">
              <div className={`pipeline-step-row status-${groupStatus}`}>
                <StepStatusIcon status={groupStatus} />
                <span>{step.label}</span>
              </div>
              {step.connectorScoped && multiConnector && (
                <div className="pipeline-step-children">
                  {connectorStatuses.map((item) => (
                    <div
                      key={`${step.id}-${item.connectorId}`}
                      className={`pipeline-step-row pipeline-step-row--child status-${item.status}`}
                    >
                      <StepStatusIcon status={item.status} />
                      <span>{connectorLabel(item.connectorId, connections)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {!error && (
        <p className="app-subtle" style={{ marginTop: 14, marginBottom: 0 }}>
          Running live pipeline checks across your selected data sources.
        </p>
      )}
      {error && (
        <div style={{ marginTop: 20 }}>
          <pre className="generate-error">{error}</pre>
          <Button type="button" variant="outline" onClick={onRetry} style={{ marginTop: 10 }}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}

function StepReport({ report, onSave, onRestart, saved }) {
  // Unwrap envelope: brief from connector slot, synthesis alongside
  const brief = report.briefs?.google_ads ?? null;
  const synthesis = report.synthesis ?? null;
  const connectorsUsed = report.connectors_used ?? [];

  return (
    <div className="generate-step">
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 20 }}>
        <Button type="button" onClick={onSave} disabled={saved}>
          {saved ? "Saved to Insights" : "Save to Insights"}
        </Button>
        <Button type="button" variant="outline" onClick={onRestart}>
          Generate another
        </Button>
      </div>
      {brief ? (
        <GoogleAdsReport brief={brief} synthesis={synthesis} />
      ) : (
        <div className="generate-alert" role="status">
          <h3 className="generate-alert-title">Insight generated</h3>
          <p className="generate-alert-help" style={{ marginBottom: 10 }}>
            A Google Ads brief was not included in this run, so the standard insight view is unavailable.
          </p>
          <p className="generate-alert-help" style={{ marginBottom: 10 }}>
            Connectors used: {connectorsUsed.length ? connectorsUsed.join(", ") : "—"}
          </p>
          <pre className="generate-error">{JSON.stringify(report, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

export default function GeneratePage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Mode — read from query param, locked for wizard lifetime
  const modeParam = searchParams.get("mode") || DEFAULT_MODE_KEY;
  const [modes, setModes] = useState(FALLBACK_MODES);
  const [modesLoaded, setModesLoaded] = useState(false);
  const resolvedMode = modes.find((m) => m.key === modeParam && m.active)?.key || DEFAULT_MODE_KEY;
  const [activeMode] = useState(resolvedMode);
  const modeConfig = getModeByKey(modes, activeMode);
  const activeGoals = modeConfig?.goals ?? [];
  const lockedConnections = modeConfig?.locked_connections ?? null;

  useEffect(() => {
    fetchModes()
      .then((fetched) => {
        setModes(fetched);
        setModesLoaded(true);
      })
      .catch(() => setModesLoaded(true)); // stay on fallback
  }, []);

  // Wizard state
  const [step, setStep] = useState(1);
  const [selectedConnections, setSelectedConnections] = useState(
    () => lockedConnections?.length ? [...lockedConnections] : []
  );
  const [goal, setGoal] = useState("");
  const [customGoal, setCustomGoal] = useState("");
  const [context, setContext] = useState(() => profileContextFromDraft());
  const initialRange = defaultDateRange();
  const [dateFrom, setDateFrom] = useState(initialRange.from);
  const [dateTo, setDateTo] = useState(initialRange.to);
  const [datePreset, setDatePreset] = useState("7");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [report, setReport] = useState(null);
  const [saved, setSaved] = useState(false);
  const [businessContext, setBusinessContext] = useState(
    () => activeMode === "organic_growth" ? businessContextFromOrganicDraft() : businessContextFromProfileDraft()
  );

  // Connector target selections (loaded on step 2 when connector is selected)
  const [adsAccounts, setAdsAccounts] = useState([]);
  const [adsAccountsLoading, setAdsAccountsLoading] = useState(false);
  const [adsAccountsError, setAdsAccountsError] = useState(null);
  const [selectedAdsCustomerId, setSelectedAdsCustomerId] = useState("");
  const [ga4Properties, setGa4Properties] = useState([]);
  const [ga4PropertiesLoading, setGa4PropertiesLoading] = useState(false);
  const [ga4PropertiesError, setGa4PropertiesError] = useState(null);
  const [selectedGa4PropertyId, setSelectedGa4PropertyId] = useState("");
  const [gscSites, setGscSites] = useState([]);
  const [gscSitesLoading, setGscSitesLoading] = useState(false);
  const [gscSitesError, setGscSitesError] = useState(null);
  const [selectedGscSiteUrl, setSelectedGscSiteUrl] = useState("");
  const [pipelineStatusByKey, setPipelineStatusByKey] = useState({});

  // Detect connected sources (Google Ads = OAuth token only; account chosen in generate flow)
  const [connections, setConnections] = useState([]);
  useEffect(() => {
    const hasGadsToken = !!sessionStorage.getItem("gads_refresh_token");
    const hasGa4Token = !!sessionStorage.getItem("ga4_refresh_token");
    const hasGscToken = !!sessionStorage.getItem("gsc_refresh_token");
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
        id: "gsc",
        name: "Google Search Console",
        description: "Organic search queries, clicks, impressions.",
        logo: "/icons/google-search-console.png",
        connected: hasGscToken,
        comingSoon: false,
      },
      {
        id: "ga4",
        name: "Google Analytics",
        description: "Website traffic, sessions, engagement.",
        logo: "https://upload.wikimedia.org/wikipedia/commons/7/77/GAnalytics.svg",
        connected: hasGa4Token,
        comingSoon: false,
      },
      {
        id: "meta_ads",
        name: "Meta Ads",
        description: "Facebook and Instagram campaign performance, spend, and conversion outcomes.",
        logo: "/icons/meta-ads.svg",
        connected: false,
        comingSoon: true,
      },
      {
        id: "stripe",
        name: "Stripe",
        description: "Revenue, subscriptions, and billing outcomes for marketing-to-revenue visibility.",
        logo: "https://upload.wikimedia.org/wikipedia/commons/b/ba/Stripe_Logo%2C_revised_2016.svg",
        connected: false,
        comingSoon: true,
      },
      {
        id: "hubspot",
        name: "HubSpot",
        description: "CRM lifecycle and pipeline outcomes to connect acquisition to revenue quality.",
        logo: "/icons/hubspot.svg",
        connected: false,
        comingSoon: true,
      },
    ]);
  }, []);

  useEffect(() => {
    if (step !== 2) return undefined;

    let cancelled = false;
    const tasks = [];

    if (selectedConnections.includes("google_ads")) {
      const adsToken = sessionStorage.getItem("gads_refresh_token");
      if (!adsToken) {
        setAdsAccounts([]);
        setAdsAccountsLoading(false);
        setSelectedAdsCustomerId("");
        setAdsAccountsError("Google Ads is selected, but no refresh token is available.");
      } else {
        setAdsAccountsLoading(true);
        setAdsAccountsError(null);
        tasks.push(
          fetchGoogleAdsAccounts(adsToken)
            .then((items) => {
              if (cancelled) return;
              setAdsAccounts(items);
              const stored = normalizeCustomerId(sessionStorage.getItem("gads_customer_id"));
              const match = stored && items.find((a) => normalizeCustomerId(a.customer_id) === stored);
              const pick = match
                ? normalizeCustomerId(match.customer_id)
                : normalizeCustomerId(items[0]?.customer_id);
              setSelectedAdsCustomerId(pick);
              if (pick) sessionStorage.setItem("gads_customer_id", pick);
              else sessionStorage.removeItem("gads_customer_id");
            })
            .catch((err) => {
              if (!cancelled) {
                setAdsAccountsError(err instanceof Error ? err.message : String(err));
              }
            })
            .finally(() => {
              if (!cancelled) setAdsAccountsLoading(false);
            })
        );
      }
    }

    if (selectedConnections.includes("ga4")) {
      const ga4Token = sessionStorage.getItem("ga4_refresh_token");
      if (!ga4Token) {
        setGa4Properties([]);
        setGa4PropertiesLoading(false);
        setSelectedGa4PropertyId("");
        setGa4PropertiesError("Google Analytics is selected, but no refresh token is available.");
      } else {
        setGa4PropertiesLoading(true);
        setGa4PropertiesError(null);
        tasks.push(
          fetchGa4Properties(ga4Token)
            .then((items) => {
              if (cancelled) return;
              setGa4Properties(items);
              const stored = normalizeGa4PropertyId(sessionStorage.getItem("ga4_property_id"));
              const match = stored && items.find((item) => normalizeGa4PropertyId(item.property_id) === stored);
              const pick = match
                ? normalizeGa4PropertyId(match.property_id)
                : normalizeGa4PropertyId(items[0]?.property_id);
              setSelectedGa4PropertyId(pick);
              if (pick) sessionStorage.setItem("ga4_property_id", pick);
              else sessionStorage.removeItem("ga4_property_id");
            })
            .catch((err) => {
              if (!cancelled) {
                setGa4PropertiesError(err instanceof Error ? err.message : String(err));
              }
            })
            .finally(() => {
              if (!cancelled) setGa4PropertiesLoading(false);
            })
        );
      }
    }

    if (selectedConnections.includes("gsc")) {
      const gscToken = sessionStorage.getItem("gsc_refresh_token");
      if (!gscToken) {
        setGscSites([]);
        setGscSitesLoading(false);
        setSelectedGscSiteUrl("");
        setGscSitesError("Search Console is selected, but no refresh token is available.");
      } else {
        setGscSitesLoading(true);
        setGscSitesError(null);
        tasks.push(
          fetchGscSites(gscToken)
            .then((items) => {
              if (cancelled) return;
              setGscSites(items);
              const stored = normalizeGscSiteUrl(sessionStorage.getItem("gsc_site_url"));
              const match = stored && items.find((item) => normalizeGscSiteUrl(item.site_url) === stored);
              const pick = match
                ? normalizeGscSiteUrl(match.site_url)
                : normalizeGscSiteUrl(items[0]?.site_url);
              setSelectedGscSiteUrl(pick);
              if (pick) sessionStorage.setItem("gsc_site_url", pick);
              else sessionStorage.removeItem("gsc_site_url");
            })
            .catch((err) => {
              if (!cancelled) {
                setGscSitesError(err instanceof Error ? err.message : String(err));
              }
            })
            .finally(() => {
              if (!cancelled) setGscSitesLoading(false);
            })
        );
      }
    }

    Promise.allSettled(tasks);
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

  function onGa4PropertyChange(propertyId) {
    const id = normalizeGa4PropertyId(propertyId);
    setSelectedGa4PropertyId(id);
    if (id) sessionStorage.setItem("ga4_property_id", id);
    else sessionStorage.removeItem("ga4_property_id");
  }

  function onGscSiteChange(siteUrl) {
    const url = normalizeGscSiteUrl(siteUrl);
    setSelectedGscSiteUrl(url);
    if (url) sessionStorage.setItem("gsc_site_url", url);
    else sessionStorage.removeItem("gsc_site_url");
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

  function applyPipelineEvent(event) {
    if (event.event !== "step_started" && event.event !== "step_finished") return;
    const stepId = event.step_id;
    if (!stepId) return;
    const connectorId = event.connector_id || "__group";
    const status = event.status || STEP_STATUS.pending;
    setPipelineStatusByKey((prev) => ({
      ...prev,
      [stepStatusKey(stepId, connectorId)]: status,
      ...(connectorId !== "__group" ? { [stepStatusKey(stepId)]: status } : {}),
    }));
  }

  async function handleGenerate() {
    setStep(5);
    setStatus("loading");
    setError(null);
    setPipelineStatusByKey(createInitialPipelineStatus(selectedConnections));

    const refreshToken = sessionStorage.getItem("gads_refresh_token") || "";
    const ga4RefreshToken = sessionStorage.getItem("ga4_refresh_token") || "";
    const gscRefreshToken = sessionStorage.getItem("gsc_refresh_token") || "";
    const cid = normalizeCustomerId(selectedAdsCustomerId);
    const ga4PropertyId = normalizeGa4PropertyId(selectedGa4PropertyId);
    const gscSiteUrl = normalizeGscSiteUrl(selectedGscSiteUrl);
    const account = adsAccounts.find((a) => normalizeCustomerId(a.customer_id) === cid);

    try {
      const data = await generateReportStream({
        connections: selectedConnections,
        mode: activeMode,
        goal: goal === "custom" ? "custom" : goal,
        custom_goal: goal === "custom" ? customGoal.trim() : "",
        context,
        date_from: dateFrom,
        date_to: dateTo,
        refresh_token: refreshToken,
        ga4_refresh_token: ga4RefreshToken,
        gsc_refresh_token: gscRefreshToken,
        ga4_property_id: ga4PropertyId,
        gsc_site_url: gscSiteUrl,
        customer_id: cid,
        account_name: account?.descriptive_name ?? "",
        currency_code: account?.currency_code || "USD",
        business_context: businessContext,
      }, {
        onEvent: applyPipelineEvent,
      });
      setReport(data);
      setStatus("success");
      setStep(6);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  function handleSave() {
    if (!report) return;
    const slug = generateSlug(selectedAdsCustomerId || sessionStorage.getItem("gads_customer_id") || "", dateTo);
    const routine = buildReportRoutine({
      selectedConnections,
      datePreset,
      dateFrom,
      dateTo,
      goal,
      customGoal,
      context,
      selectedAdsCustomerId,
      adsAccounts,
      selectedGa4PropertyId,
      ga4Properties,
      selectedGscSiteUrl,
      businessContext,
      mode: activeMode,
    });
    saveLocalReport(slug, report, routine, getActiveProjectId() || null, activeMode);
    setSaved(true);
    setTimeout(() => router.push("/insights"), 400);
  }

  function handleRestart() {
    setStep(1);
    setSelectedConnections(lockedConnections?.length ? [...lockedConnections] : []);
    setGoal("");
    setCustomGoal("");
    setContext(profileContextFromDraft());
    const r = defaultDateRange();
    setDateFrom(r.from);
    setDateTo(r.to);
    setDatePreset("7");
    setStatus("idle");
    setError(null);
    setReport(null);
    setSaved(false);
    setBusinessContext(
      activeMode === "organic_growth" ? businessContextFromOrganicDraft() : businessContextFromProfileDraft()
    );
    setAdsAccounts([]);
    setAdsAccountsLoading(false);
    setSelectedAdsCustomerId("");
    setAdsAccountsError(null);
    setGa4Properties([]);
    setGa4PropertiesError(null);
    setGa4PropertiesLoading(false);
    setSelectedGa4PropertyId("");
    setGscSites([]);
    setGscSitesError(null);
    setGscSitesLoading(false);
    setSelectedGscSiteUrl("");
    setPipelineStatusByKey({});
  }

  function handleRetry() {
    handleGenerate();
  }

  const canProceedStep1 = selectedConnections.length > 0;
  const needsAdsAccount = selectedConnections.includes("google_ads");
  const needsGa4Property = selectedConnections.includes("ga4");
  const needsGscSite = selectedConnections.includes("gsc");
  const showPaidTargets = activeMode !== "organic_growth" && selectedConnections.includes("google_ads");
  const hasEconomicGuardrail =
    Number(businessContext.target_payback_days) > 0 ||
    Number(businessContext.gross_margin_percent) > 0 ||
    Number(businessContext.qualified_lead_value) > 0;
  const hasPrimaryConversionAction = String(businessContext.primary_conversion_action || "").trim().length > 0;
  const adsBusinessContextOk =
    activeMode === "organic_growth"
      ? true
      : !showPaidTargets || (hasPrimaryConversionAction && hasEconomicGuardrail);
  const selectedIdNorm = normalizeCustomerId(selectedAdsCustomerId);
  const adsAccountOk =
    !needsAdsAccount ||
    (!adsAccountsLoading &&
      !adsAccountsError &&
      !!selectedIdNorm &&
      adsAccounts.some((a) => normalizeCustomerId(a.customer_id) === selectedIdNorm));
  const selectedGa4PropertyIdNorm = normalizeGa4PropertyId(selectedGa4PropertyId);
  const ga4PropertyOk =
    !needsGa4Property ||
    (!ga4PropertiesLoading &&
      !ga4PropertiesError &&
      !!selectedGa4PropertyIdNorm &&
      ga4Properties.some((item) => normalizeGa4PropertyId(item.property_id) === selectedGa4PropertyIdNorm));
  const selectedGscSiteUrlNorm = normalizeGscSiteUrl(selectedGscSiteUrl);
  const gscSiteOk =
    !needsGscSite ||
    (!gscSitesLoading &&
      !gscSitesError &&
      !!selectedGscSiteUrlNorm &&
      gscSites.some((item) => normalizeGscSiteUrl(item.site_url) === selectedGscSiteUrlNorm));
  const canProceedTargets = adsAccountOk && ga4PropertyOk && gscSiteOk;
  const canProceedConfigure =
    goal &&
    (goal !== "custom" || customGoal.trim()) &&
    dateFrom &&
    dateTo &&
    adsBusinessContextOk;

  function targetBlockedReason() {
    if (needsAdsAccount && adsAccountsLoading) return "Wait for Google Ads accounts to finish loading.";
    if (needsAdsAccount && adsAccountsError) return "Fix the Google Ads account error above, then try again.";
    if (needsAdsAccount && !adsAccounts.length) return "No Google Ads accounts available — connect or fix access first.";
    if (needsAdsAccount && !adsAccountOk) return "Select a Google Ads account from the dropdown.";
    if (needsGa4Property && ga4PropertiesLoading) return "Wait for GA4 properties to finish loading.";
    if (needsGa4Property && ga4PropertiesError) return "Fix the GA4 property error above, then try again.";
    if (needsGa4Property && !ga4Properties.length) return "No GA4 properties available — connect or fix access first.";
    if (needsGa4Property && !ga4PropertyOk) return "Select a GA4 property from the dropdown.";
    if (needsGscSite && gscSitesLoading) return "Wait for Search Console sites to finish loading.";
    if (needsGscSite && gscSitesError) return "Fix the Search Console site error above, then try again.";
    if (needsGscSite && !gscSites.length) return "No Search Console sites available — connect or fix access first.";
    if (needsGscSite && !gscSiteOk) return "Select a Search Console site from the dropdown.";
    return "";
  }

  function configureBlockedReason() {
    if (!goal) return "Select an analysis goal above to continue.";
    if (goal === "custom" && !customGoal.trim()) return "Enter a short description for your custom goal.";
    if (!dateFrom || !dateTo) return "Choose a date range (or pick Custom and set dates).";
    if (activeMode !== "organic_growth" && showPaidTargets && !hasPrimaryConversionAction) return "Enter your primary conversion action for this ads analysis.";
    if (activeMode !== "organic_growth" && showPaidTargets && !hasEconomicGuardrail) return "Add at least one economic guardrail (payback days, gross margin, or qualified lead value).";
    return "";
  }

  const cidForReview = normalizeCustomerId(selectedAdsCustomerId);
  const accountForReview = adsAccounts.find((a) => normalizeCustomerId(a.customer_id) === cidForReview);
  const ga4ForReview = ga4Properties.find(
    (item) => normalizeGa4PropertyId(item.property_id) === selectedGa4PropertyIdNorm
  );
  const gscForReview = gscSites.find(
    (item) => normalizeGscSiteUrl(item.site_url) === selectedGscSiteUrlNorm
  );

  return (
    <section>
      <div className="page-toolbar-back">
        <Button
          variant="ghost"
          size="icon"
          className="connection-back-btn shrink-0 rounded-full"
          asChild
        >
          <Link href="/insights" aria-label="Back to Insights" title="Back to Insights">
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
        </Button>
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
          Generate Insight
          {modeConfig && (
            <span className="mode-badge-wizard" aria-label={`Mode: ${modeConfig.label}`}>
              {modeConfig.emoji} {modeConfig.label}
            </span>
          )}
        </h1>
      </div>

      <ProgressDots step={step} />

      {step === 1 && (
        <>
          <StepConnections
            connections={
              lockedConnections?.length
                ? connections.filter((c) => lockedConnections.includes(c.id))
                : connections
            }
            selected={selectedConnections}
            onToggle={lockedConnections?.length ? () => {} : toggleConnection}
            locked={!!lockedConnections?.length}
          />
          <div style={{ marginTop: 16 }}>
            <Button type="button" disabled={!canProceedStep1} onClick={() => setStep(2)}>
              Next
            </Button>
          </div>
        </>
      )}

      {step === 2 && (
        <>
          <div className="generate-step">
            <h2 className="generate-step-title">Select account/property/site</h2>
            <p className="app-subtle" style={{ marginTop: 0, marginBottom: 16 }}>
              Pick the specific targets for each selected connector.
            </p>
            {selectedConnections.includes("google_ads") && (
              <StepAdsAccount
                accounts={adsAccounts}
                loading={adsAccountsLoading}
                fetchError={adsAccountsError}
                selectedId={selectedAdsCustomerId}
                onChange={onAdsAccountChange}
              />
            )}
            {selectedConnections.includes("ga4") && (
              <StepGa4Property
                properties={ga4Properties}
                loading={ga4PropertiesLoading}
                fetchError={ga4PropertiesError}
                selectedId={selectedGa4PropertyId}
                onChange={onGa4PropertyChange}
              />
            )}
            {selectedConnections.includes("gsc") && (
              <StepGscSite
                sites={gscSites}
                loading={gscSitesLoading}
                fetchError={gscSitesError}
                selectedUrl={selectedGscSiteUrl}
                onChange={onGscSiteChange}
              />
            )}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <Button type="button" variant="outline" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button type="button" disabled={!canProceedTargets} onClick={() => setStep(3)}>
              Next
            </Button>
          </div>
          {!canProceedTargets && (
            <p className="app-subtle generate-step-hint" role="status">
              {targetBlockedReason()}
            </p>
          )}
        </>
      )}

      {step === 3 && (
        <>
          <StepGoal
            goals={activeGoals}
            mode={activeMode}
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
            showPaidTargets={showPaidTargets}
            businessContext={businessContext}
            onBusinessContextChange={setBusinessContext}
          />
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <Button type="button" variant="outline" onClick={() => setStep(2)}>
              Back
            </Button>
            <Button type="button" disabled={!canProceedConfigure} onClick={() => setStep(4)}>
              Next
            </Button>
          </div>
          {!canProceedConfigure && (
            <p className="app-subtle generate-step-hint" role="status">
              {configureBlockedReason()}
            </p>
          )}
        </>
      )}

      {step === 4 && (
        <>
          <StepReview
            selectedConnectionIds={selectedConnections}
            connections={connections}
            needsAdsAccount={needsAdsAccount}
            needsGa4Property={needsGa4Property}
            needsGscSite={needsGscSite}
            accountDescriptiveName={accountForReview?.descriptive_name ?? ""}
            accountCustomerId={cidForReview}
            ga4PropertyName={ga4ForReview?.property_name ?? ""}
            ga4PropertyId={selectedGa4PropertyIdNorm}
            gscSiteUrl={gscForReview?.site_url ?? selectedGscSiteUrlNorm}
            goalKey={goal}
            customGoal={customGoal}
            goals={activeGoals}
            dateFrom={dateFrom}
            dateTo={dateTo}
            datePreset={datePreset}
          />
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <Button type="button" variant="outline" onClick={() => setStep(3)}>
              Back
            </Button>
            <Button type="button" disabled={!canProceedConfigure} onClick={handleGenerate}>
              Generate
            </Button>
          </div>
          {!canProceedConfigure && (
            <p className="app-subtle generate-step-hint" role="status">
              {configureBlockedReason()}
            </p>
          )}
        </>
      )}

      {step === 5 && (
        <StepAnalyzing
          error={error}
          onRetry={handleRetry}
          statusByKey={pipelineStatusByKey}
          selectedConnections={selectedConnections}
          connections={connections}
        />
      )}

      {step === 6 && report && (
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
