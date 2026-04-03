"use client";

import { useState } from "react";
import { resolveTheme } from "../lib/themes";

// ─── Tone helpers ────────────────────────────────────────────────────────────

function toneForRoas(value) {
  if (value >= 2.5) return "green";
  if (value >= 1.5) return "yellow";
  return "red";
}

function trendToneForMetric(metric, delta) {
  const { direction } = delta;
  if (direction === "flat") return "grey";
  if (metric === "conversions" || metric === "roas") return direction === "up" ? "green" : "red";
  if (metric === "cpa") return direction === "down" ? "green" : "red";
  return "grey";
}

function actionTone(action) {
  if (action === "scale") return "green";
  if (action === "pause") return "red";
  if (["tighten", "refresh", "investigate"].includes(action)) return "yellow";
  return "grey";
}

function chipAccent(tone) {
  return (
    {
      red: "kpi-chip--accent-red",
      yellow: "kpi-chip--accent-yellow",
      green: "kpi-chip--accent-green",
      grey: "kpi-chip--accent-grey",
    }[tone] ?? "kpi-chip--accent-grey"
  );
}

function signalLevel(finding) {
  if (finding.type === "win") return "green";
  if (finding.type === "risk") return finding.confidence === "high" ? "red" : "yellow";
  return "yellow";
}

// ─── Icons ───────────────────────────────────────────────────────────────────

function TrendIcon({ direction }) {
  if (direction === "up")
    return (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path d="m18 15-6-6-6 6" />
      </svg>
    );
  if (direction === "down")
    return (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path d="m6 9 6 6 6-6" />
      </svg>
    );
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M5 12h14" />
    </svg>
  );
}

function SpendIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9.5" />
      <path d="M12 6v12" />
      <path d="M15.5 9.25a3.25 3.25 0 0 0-6.5 0c0 1.5 1.36 2.03 2.72 2.55 1.5.58 3.78 1.32 3.78 3.7a3.25 3.25 0 0 1-6.5 0" />
    </svg>
  );
}

function ConvIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function CpaIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  );
}

function RoasIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M22 7L13.5 15.5 8.5 10.5 2 17" />
      <path d="M16 7h6v6" />
    </svg>
  );
}

// ─── Sparkline ───────────────────────────────────────────────────────────────

function Sparkline({ points, accent }) {
  const w = 130, h = 44, padX = 4, padY = 6;
  const n = points.length;
  if (n < 2) return null;

  const mn = Math.min(...points);
  const mx = Math.max(...points);
  const rng = mx - mn || 1;

  const coords = points.map((p, i) => ({
    x: padX + (i / (n - 1)) * (w - 2 * padX),
    y: h - padY - ((p - mn) / rng) * (h - 2 * padY),
  }));

  const linePoints = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const firstX = coords[0].x.toFixed(1);
  const lastX = coords[n - 1].x.toFixed(1);
  const baseY = (h - padY).toFixed(1);

  const dFill =
    coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ") +
    ` L ${lastX},${baseY} L ${firstX},${baseY} Z`;

  const gradId = `sparkGrad-${accent.replace("#", "")}`;

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={accent} stopOpacity="0.35" />
          <stop offset="100%" stopColor={accent} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path className="spark-fill" d={dFill} fill={`url(#${gradId})`} />
      <polyline className="spark-line" points={linePoints} stroke={accent} />
    </svg>
  );
}

// ─── KPI Chip ─────────────────────────────────────────────────────────────────

function KpiChip({ label, value, delta, tone, Icon }) {
  return (
    <div className={`kpi-chip ${chipAccent(tone)}`}>
      <div className="kpi-chip-head">
        <span className="kpi-icon" aria-hidden="true">
          <Icon />
        </span>
        <p className="kpi-label">{label}</p>
      </div>
      <p className="kpi-value">{value}</p>
      <div className="kpi-delta">
        <span className={`kpi-trend tone-${tone}`} aria-hidden="true">
          <TrendIcon direction={delta.direction} />
        </span>
        <span>{delta.formatted}</span>
      </div>
    </div>
  );
}

// ─── Signal block ─────────────────────────────────────────────────────────────

function SignalBlock({ finding }) {
  const level = signalLevel(finding);
  const pillLabel = finding.type === "win" ? "Win" : finding.type === "risk" ? "Risk" : "Watch";
  const evidence = finding.evidence?.slice(0, 3).join(" • ");

  return (
    <div className={`signal-block signal-level-${level}`}>
      <span className={`signal-pill ${level}`}>{pillLabel}</span>
      <p className="signal-title">{finding.title}</p>
      <p className="signal-body">{finding.impact}</p>
      {evidence && <p className="signal-body signal-evidence">Evidence: {evidence}</p>}
      <div className="signal-action">
        <div className="signal-action-row">
          <div className="signal-action-cell">
            <span className="signal-action-label">Action</span>
            <span className="signal-action-value">{finding.recommended_action}</span>
          </div>
          <div className="signal-action-cell">
            <span className="signal-action-label">Confidence</span>
            <span className="signal-action-value">
              {finding.confidence.charAt(0).toUpperCase() + finding.confidence.slice(1)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Signals section (with show-more) ────────────────────────────────────────

const LEVEL_PRI = { red: 0, yellow: 1, green: 2 };

function SignalsSection({ highlights, risks, accent }) {
  const [expanded, setExpanded] = useState(false);

  const all = [...risks, ...highlights].sort(
    (a, b) => (LEVEL_PRI[signalLevel(a)] ?? 3) - (LEVEL_PRI[signalLevel(b)] ?? 3)
  );
  const visible = all.slice(0, 2);
  const extra = all.slice(2);

  return (
    <>
      <div className="signal-grid">
        {visible.map((f) => (
          <SignalBlock key={f.finding_id} finding={f} />
        ))}
      </div>

      {extra.length > 0 && (
        <>
          {expanded && (
            <div className="rpt-signal-extra-wrap" style={{ marginTop: 12 }}>
              {extra.map((f) => (
                <SignalBlock key={f.finding_id} finding={f} />
              ))}
            </div>
          )}
          <button
            type="button"
            className="rpt-show-more-signals"
            style={{ "--rpt-accent": accent }}
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Show less signals" : "Show more signals"}
          </button>
        </>
      )}
    </>
  );
}

// ─── ROAS bars ────────────────────────────────────────────────────────────────

function RoasBars({ campaigns, accent }) {
  const maxR = Math.max(...campaigns.map((c) => c.roas), 1);
  return (
    <div className="rpt-bar-block">
      <p className="rpt-bar-label">ROAS by campaign</p>
      {campaigns.map((c) => {
        const pct = Math.round((c.roas / maxR) * 100);
        return (
          <div className="rpt-bar-row" key={c.campaign_id ?? c.campaign_name}>
            <div className="rpt-bar-top">
              <span className="rpt-bar-name">{c.campaign_name}</span>
              <span className="rpt-bar-val">{c.roas.toFixed(2)}x</span>
            </div>
            <div className="rpt-bar-track">
              <div
                className="rpt-bar-fill"
                style={{
                  width: `${pct}%`,
                  background: `linear-gradient(90deg, #93c5fd, ${accent})`,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Campaign disclosure table ────────────────────────────────────────────────

function CampaignTable({ campaigns, currency }) {
  const [open, setOpen] = useState(false);

  function fmt(value) {
    const sym = currency === "USD" ? "$" : `${currency} `;
    return `${sym}${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  return (
    <div className="rpt-disclosure">
      <button
        type="button"
        className="rpt-disclosure-btn"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>
          Campaign breakdown
          <span className="rpt-disclosure-meta"> · {campaigns.length}</span>
        </span>
        <span className={`rpt-disclosure-chevron${open ? " open" : ""}`} aria-hidden="true">
          ▼
        </span>
      </button>

      {open && (
        <div className="rpt-disclosure-panel">
          <div className="camp-table-wrap">
            <table className="camp-table">
              <thead>
                <tr>
                  <th>Campaign</th>
                  <th>Spend</th>
                  <th>CPA</th>
                  <th>ROAS</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c, i) => (
                  <tr
                    key={c.campaign_id ?? c.campaign_name}
                    className={i % 2 === 1 ? "camp-row camp-row--alt" : "camp-row"}
                  >
                    <td>{c.campaign_name}</td>
                    <td>{fmt(c.spend)}</td>
                    <td>{fmt(c.cost_per_conversion)}</td>
                    <td>{c.roas.toFixed(2)}x</td>
                    <td>
                      <span className={`status-pill ${actionTone(c.action)}`}>
                        {c.action.replace(/_/g, " ")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Root component ───────────────────────────────────────────────────────────

export default function GoogleAdsReport({ payload }) {
  const theme = resolveTheme(payload.source_metadata?.theme);
  const accent = theme.accent;

  const { source_metadata: meta, account_summary, period_comparison, campaigns, highlights, risks, narrative } = payload;

  const roasValue = account_summary.roas.value;
  const verdictTone = toneForRoas(roasValue);

  const roasDelta = period_comparison.roas.delta;
  const heroDeltaTone = roasDelta.direction === "up" ? "green" : roasDelta.direction === "down" ? "red" : "grey";

  const sparkPoints = [
    period_comparison.spend.previous.value,
    account_summary.spend.value,
  ];

  const spendDelta = period_comparison.spend.delta;
  const convDelta = period_comparison.conversions.delta;
  const cpaDelta = period_comparison.cost_per_conversion.delta;

  const metaText = [
    `Source: ${meta.source}`,
    `${meta.window_current} vs ${meta.window_previous}`,
    `Account: ${meta.account_name}`,
    theme.label ? `Theme: ${theme.label}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const summaryText = `${narrative.summary} Operator takeaway: ${narrative.operator_takeaway}`;
  const sourcesText = `Generated at ${meta.generated_at} · ${meta.source_file ?? meta.export_type}`;

  return (
    <div className="rpt-sheet" style={{ "--rpt-accent": accent }}>
      <div className="rpt-header">
        <p className="rpt-meta">{metaText}</p>
        <div className={`rpt-verdict ${verdictTone}`} role="status">
          {narrative.verdict}
        </div>
        <p className="rpt-summary">{summaryText}</p>
      </div>

      <div className="rpt-body">
        {/* Hero */}
        <div className="rpt-hero-visual">
          <div className="kpi-hero-block">
            <p className="kpi-hero-label">ROAS</p>
            <p className="kpi-hero-value">{account_summary.roas.formatted}</p>
            <div className="kpi-hero-delta">
              <span className={`kpi-trend tone-${heroDeltaTone}`} aria-hidden="true">
                <TrendIcon direction={roasDelta.direction} />
              </span>
              <span>{roasDelta.formatted}</span>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--navy-3)", margin: "0 0 6px" }}>
              {meta.window_current} vs previous (indexed)
            </p>
            <div className="kpi-sparkline-svg" aria-hidden="true">
              <Sparkline points={sparkPoints} accent={accent} />
            </div>
          </div>
        </div>

        {/* KPI strip */}
        <div className="kpi-strip">
          <KpiChip
            label="Spend"
            value={account_summary.spend.formatted}
            delta={spendDelta}
            tone={trendToneForMetric("spend", spendDelta)}
            Icon={SpendIcon}
          />
          <KpiChip
            label="Conversions"
            value={account_summary.conversions.formatted}
            delta={convDelta}
            tone={trendToneForMetric("conversions", convDelta)}
            Icon={ConvIcon}
          />
          <KpiChip
            label="CPA"
            value={account_summary.cost_per_conversion.formatted}
            delta={cpaDelta}
            tone={trendToneForMetric("cpa", cpaDelta)}
            Icon={CpaIcon}
          />
          <KpiChip
            label="ROAS"
            value={account_summary.roas.formatted}
            delta={roasDelta}
            tone={trendToneForMetric("roas", roasDelta)}
            Icon={RoasIcon}
          />
        </div>

        {/* ROAS bars */}
        <RoasBars campaigns={campaigns} accent={accent} />

        {/* Signals */}
        <p className="rpt-section-label">Signals</p>
        <SignalsSection highlights={highlights} risks={risks} accent={accent} />

        {/* Campaign table */}
        <CampaignTable campaigns={campaigns} currency={meta.currency_code} />

        <p className="rpt-sources">{sourcesText}</p>
      </div>
    </div>
  );
}
