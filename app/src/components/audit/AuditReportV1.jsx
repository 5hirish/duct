"use client";

// ---------------------------------------------------------------------------
// CSS-only tooltips via data-tooltip attribute
// ---------------------------------------------------------------------------

const TOOLTIP_STYLE = `
[data-tooltip] { position: relative; cursor: help; }
[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: #1f2937;
  color: #f9fafb;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.5;
  white-space: normal;
  width: 220px;
  text-align: left;
  pointer-events: none;
  opacity: 0;
  z-index: 50;
  transition: opacity 0.15s ease;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
[data-tooltip]:hover::after { opacity: 1; }
details > summary { list-style: none; }
details > summary::-webkit-details-marker { display: none; }
`;

// ---------------------------------------------------------------------------
// Health gauge — pure SVG semicircle arc
// ---------------------------------------------------------------------------

const ARC_R = 54;
const ARC_LEN = Math.PI * ARC_R; // half-circumference ≈ 169.6

function gaugeColor(score) {
  if (score >= 85) return "#10b981";
  if (score >= 70) return "#f59e0b";
  if (score >= 55) return "#f97316";
  return "#ef4444";
}

const BAND_LABEL = {
  healthy:    "Healthy",
  good:       "Good",
  needs_work: "Needs Work",
  critical:   "Critical",
};

function ScoreGauge({ score, band }) {
  const filled = Math.min((score / 100) * ARC_LEN, ARC_LEN);
  const color  = gaugeColor(score);
  const label  = BAND_LABEL[band] ?? band;

  return (
    <div
      className="flex flex-col items-center shrink-0"
      data-tooltip={`${score}/100 — ${label}. Weighted average across all 9 SEO categories.`}
    >
      {/* viewBox: 0 0 120 70 | arc: M(6,64) → A54 → (114,64) sweeping over the top */}
      <svg viewBox="0 0 120 70" width="120" height="70" role="img" aria-label={`Score ${score} out of 100, ${label}`}>
        {/* Track */}
        <path
          d="M 6,64 A 54,54 0 0 1 114,64"
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.1"
          strokeWidth="9"
          strokeLinecap="round"
        />
        {/* Fill */}
        <path
          d="M 6,64 A 54,54 0 0 1 114,64"
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${ARC_LEN}`}
        />
        {/* Score number */}
        <text
          x="60" y="52"
          textAnchor="middle"
          fontSize="26"
          fontWeight="700"
          fill="currentColor"
        >
          {score}
        </text>
      </svg>
      <span className="text-xs font-semibold -mt-1" style={{ color }}>
        {label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Severity badge
// ---------------------------------------------------------------------------

const SEVERITY_CFG = {
  fail:        { label: "FAIL", border: "border-red-300 dark:border-red-800",    text: "text-red-600 dark:text-red-400",    dot: "bg-red-500",   bg: "bg-red-50 dark:bg-red-950/40"    },
  warn:        { label: "WARN", border: "border-amber-300 dark:border-amber-800", text: "text-amber-600 dark:text-amber-400", dot: "bg-amber-500", bg: "bg-amber-50 dark:bg-amber-950/40" },
  pass:        { label: "PASS", border: "border-green-300 dark:border-green-800", text: "text-green-600 dark:text-green-400", dot: "bg-green-500", bg: "bg-green-50 dark:bg-green-950/30" },
  opportunity: { label: "OPP",  border: "border-blue-300 dark:border-blue-800",   text: "text-blue-600 dark:text-blue-400",  dot: "bg-blue-400",  bg: "bg-blue-50 dark:bg-blue-950/30"   },
};

const SEVERITY_TOOLTIP = {
  fail:        "Actively hurting your rankings or visibility. Fix as soon as possible.",
  warn:        "Not critical yet but will limit your potential if left unaddressed.",
  pass:        "No issue found. This signal is working in your favour.",
  opportunity: "No problem, but improving this could meaningfully boost traffic.",
};

function SeverityBadge({ severity }) {
  const cfg = SEVERITY_CFG[severity] ?? SEVERITY_CFG.pass;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-semibold tracking-wide uppercase ${cfg.text} ${cfg.border} ${cfg.bg}`}
      data-tooltip={SEVERITY_TOOLTIP[severity]}
    >
      <span className={`size-1.5 rounded-full shrink-0 ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Category scorecard
// ---------------------------------------------------------------------------

function scoreBarColor(score) {
  if (score >= 85) return "#10b981";
  if (score >= 70) return "#f59e0b";
  if (score >= 55) return "#f97316";
  return "#ef4444";
}

function CategoryCard({ category }) {
  const color = scoreBarColor(category.score);
  const hasBad = category.fail_count > 0 || category.warn_count > 0;

  return (
    <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-2">
        <span
          className="text-sm font-semibold leading-tight"
          data-tooltip={category.tooltip}
        >
          {category.label}
        </span>
        <span className="text-lg font-bold shrink-0 tabular-nums" style={{ color }}>
          {category.score}
        </span>
      </div>

      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${category.score}%`, backgroundColor: color }}
        />
      </div>

      <div className="flex items-center gap-2 text-[11px] flex-wrap">
        {category.fail_count > 0 && (
          <span className="text-red-500 font-semibold">{category.fail_count}F</span>
        )}
        {category.warn_count > 0 && (
          <span className="text-amber-500 font-semibold">{category.warn_count}W</span>
        )}
        {category.opp_count > 0 && (
          <span className="text-blue-500 font-semibold">{category.opp_count}O</span>
        )}
        {category.pass_count > 0 && (
          <span className="text-green-600 font-semibold">{category.pass_count}P</span>
        )}
        {!hasBad && category.opp_count === 0 && (
          <span className="text-muted-foreground">All clear</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Finding card
// ---------------------------------------------------------------------------

const IMPACT_STYLE = {
  critical: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  high:     "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  medium:   "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  low:      "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};
const EFFORT_STYLE = {
  low:    "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  medium: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  high:   "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

function FindingCard({ finding }) {
  const cfg = SEVERITY_CFG[finding.severity] ?? SEVERITY_CFG.pass;

  return (
    <div className={`rounded-lg border p-4 space-y-3 ${cfg.border} ${cfg.bg}`}>
      <div className="flex items-start gap-2 flex-wrap">
        <SeverityBadge severity={finding.severity} />
        <span
          className="text-sm font-semibold leading-snug flex-1 min-w-0"
          data-tooltip={finding.tooltip}
        >
          {finding.title}
        </span>
      </div>

      {finding.description && (
        <p className="text-xs text-muted-foreground leading-relaxed">
          {finding.description}
        </p>
      )}

      {finding.affected_urls?.length > 0 && (
        <div className="overflow-x-auto rounded border border-border/50">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-muted/40">
                <th className="text-left px-3 py-1.5 font-medium text-muted-foreground">URL</th>
                <th className="text-left px-3 py-1.5 font-medium text-muted-foreground whitespace-nowrap">Measured</th>
              </tr>
            </thead>
            <tbody>
              {finding.affected_urls.map((u, i) => (
                <tr key={i} className="border-t border-border/30">
                  <td className="px-3 py-1.5 font-mono text-[10px] text-muted-foreground break-all max-w-[200px]">
                    {u.url}
                  </td>
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    {u.issue_value}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {finding.recommendation && (
        <p className="text-xs leading-relaxed">
          <span className="font-semibold">Fix: </span>
          {finding.recommendation}
        </p>
      )}

      {(finding.impact || finding.effort) && (
        <div className="flex items-center gap-2 flex-wrap">
          {finding.impact && (
            <span className={`px-2 py-0.5 rounded text-[10px] font-medium capitalize ${IMPACT_STYLE[finding.impact] ?? ""}`}>
              {finding.impact} impact
            </span>
          )}
          {finding.effort && (
            <span className={`px-2 py-0.5 rounded text-[10px] font-medium capitalize ${EFFORT_STYLE[finding.effort] ?? ""}`}>
              {finding.effort} effort
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Findings accordion per category
// ---------------------------------------------------------------------------

const SEVERITY_ORDER = { fail: 0, warn: 1, opportunity: 2, pass: 3 };

function CategoryAccordion({ category }) {
  const ordered  = [...(category.findings ?? [])].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4),
  );
  const hasBad   = category.fail_count > 0 || category.warn_count > 0;
  const color    = scoreBarColor(category.score);

  const summaryText = [
    category.fail_count > 0 && `${category.fail_count} Error${category.fail_count !== 1 ? "s" : ""}`,
    category.warn_count > 0 && `${category.warn_count} Warning${category.warn_count !== 1 ? "s" : ""}`,
    !hasBad && !category.opp_count && "All clear",
    !hasBad && category.opp_count > 0 && `${category.opp_count} Opportunit${category.opp_count !== 1 ? "ies" : "y"}`,
  ].filter(Boolean).join(", ");

  return (
    <details className="group border border-border rounded-xl overflow-hidden" open={hasBad || undefined}>
      <summary className="flex items-center justify-between gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="size-7 rounded flex items-center justify-center text-[10px] font-bold text-white shrink-0"
            style={{ backgroundColor: color }}
          >
            {category.score}
          </div>
          <span className="text-sm font-semibold">{category.label}</span>
          <span className="text-xs text-muted-foreground hidden sm:inline truncate">
            {summaryText}
          </span>
        </div>
        <span className="text-muted-foreground text-xs shrink-0 transition-transform duration-200 group-open:rotate-180">
          ▼
        </span>
      </summary>

      <div className="px-4 pb-4 pt-3 space-y-3 border-t border-border/40">
        {ordered.length === 0 ? (
          <p className="text-sm text-muted-foreground">No findings for this category.</p>
        ) : (
          ordered.map((f) => <FindingCard key={f.id} finding={f} />)
        )}
      </div>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Priority card
// ---------------------------------------------------------------------------

const PRIORITY_BORDER = {
  fail:        "border-l-red-500",
  warn:        "border-l-amber-500",
  opportunity: "border-l-blue-400",
};

function PriorityCard({ priority }) {
  const border = PRIORITY_BORDER[priority.severity] ?? "border-l-border";
  const severityLabel =
    priority.severity === "fail" ? "Error" :
    priority.severity === "warn" ? "Warning" :
    "Opportunity";

  return (
    <div className={`rounded-xl border border-border border-l-4 ${border} bg-card px-4 py-3 flex gap-4`}>
      <span className="text-2xl font-black text-muted-foreground/30 shrink-0 leading-none mt-1 tabular-nums">
        {priority.rank}
      </span>
      <div className="flex-1 min-w-0 space-y-1">
        <p className="text-sm font-semibold leading-snug">{priority.title}</p>
        <p className="text-xs text-muted-foreground leading-relaxed">{priority.why_it_matters}</p>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground/70 flex-wrap pt-0.5">
          <span className="capitalize">{severityLabel}</span>
          {priority.affected_url_count > 0 && (
            <>
              <span>·</span>
              <span>{priority.affected_url_count} page{priority.affected_url_count !== 1 ? "s" : ""}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AuditReportV1({ data }) {
  if (!data) return null;

  const showCoverageBanner =
    data.total_sitemap_urls > 0 &&
    data.pages_crawled / data.total_sitemap_urls < 0.3;

  const totalPassing = (data.categories ?? []).reduce(
    (acc, c) => acc + (c.pass_count ?? 0),
    0,
  );

  const dateStr = data.generated_at
    ? new Date(data.generated_at).toLocaleDateString("en-US", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "";

  return (
    <div className="min-h-full bg-background text-foreground">
      <style>{TOOLTIP_STYLE}</style>

      <div className="max-w-4xl mx-auto px-4 py-6 space-y-8">

        {/* Header */}
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="space-y-3 flex-1 min-w-0">
            <div>
              <p className="text-xs text-muted-foreground truncate">
                {data.url}{dateStr && ` · ${dateStr}`}
              </p>
              <h1 className="text-xl font-bold mt-0.5">SEO Audit Report</h1>
            </div>

            {/* Issue count pills */}
            <div className="flex items-center gap-2 flex-wrap">
              {data.total_issues > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                  <span className="size-1.5 rounded-full bg-red-500 inline-block shrink-0" />
                  {data.total_issues} Error{data.total_issues !== 1 ? "s" : ""}
                </span>
              )}
              {data.total_warnings > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                  <span className="size-1.5 rounded-full bg-amber-500 inline-block shrink-0" />
                  {data.total_warnings} Warning{data.total_warnings !== 1 ? "s" : ""}
                </span>
              )}
              {data.total_opportunities > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                  <span className="size-1.5 rounded-full bg-blue-400 inline-block shrink-0" />
                  {data.total_opportunities} Opportunit{data.total_opportunities !== 1 ? "ies" : "y"}
                </span>
              )}
              {totalPassing > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                  <span className="size-1.5 rounded-full bg-green-500 inline-block shrink-0" />
                  {totalPassing} Passing
                </span>
              )}
            </div>
          </div>

          <ScoreGauge score={data.overall_score} band={data.score_band} />
        </div>

        {/* Coverage banner */}
        {showCoverageBanner && (
          <div
            className="rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
            data-tooltip="Only a sample of your sitemap was scanned. Connect Google Search Console for a full-site analysis."
          >
            <span className="font-semibold">Limited scan: </span>
            Based on {data.pages_crawled} of {data.total_sitemap_urls} sitemap pages.
            Results may not reflect your full site — connect GSC for comprehensive coverage.
          </div>
        )}

        {/* Executive summary */}
        {data.executive_summary && (
          <p className="text-sm text-muted-foreground leading-relaxed border-l-2 border-border pl-4">
            {data.executive_summary}
          </p>
        )}

        {/* Fix these first */}
        {data.top_priorities?.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-base font-bold">Fix These First</h2>
            <div className="space-y-2">
              {data.top_priorities.map((p) => (
                <PriorityCard key={p.rank} priority={p} />
              ))}
            </div>
          </section>
        )}

        {/* Category scorecards */}
        {data.categories?.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-base font-bold">Category Scores</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {data.categories.map((cat) => (
                <CategoryCard key={cat.id} category={cat} />
              ))}
            </div>
          </section>
        )}

        {/* Findings accordion */}
        {data.categories?.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-base font-bold">Findings by Category</h2>
            <div className="space-y-2">
              {data.categories.map((cat) => (
                <CategoryAccordion key={cat.id} category={cat} />
              ))}
            </div>
          </section>
        )}

        {/* Footer */}
        <footer className="text-center text-xs text-muted-foreground/50 pt-4 border-t border-border/40">
          Generated by Duct · getduct.ai
        </footer>
      </div>
    </div>
  );
}
