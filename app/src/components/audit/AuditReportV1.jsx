"use client";
import React from 'react';
import { BarChart, Bar, XAxis, YAxis, Cell, ResponsiveContainer, LabelList } from 'recharts';
import { AlertTriangle, CheckCircle2, Calendar, Activity, Target, BarChart2, Zap, Clock, TrendingUp } from 'lucide-react';

// ---------------------------------------------------------------------------
// Global styles — tooltips + entrance animations
// ---------------------------------------------------------------------------

const GLOBAL_STYLE = `
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

body { line-height: 1.65; }
@keyframes rise {
  from { opacity: 0; transform: translateY(18px); }
  to   { opacity: 1; transform: translateY(0); }
}
.rise-0 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.00s; }
.rise-1 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.07s; }
.rise-2 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.14s; }
.rise-3 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.21s; }
.rise-4 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.28s; }
.rise-5 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.35s; }
.rise-6 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.42s; }
.rise-7 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.49s; }
.rise-8 { animation: rise .5s cubic-bezier(.2,.6,.2,1) both 0.56s; }
`;

// ---------------------------------------------------------------------------
// Design tokens
// ---------------------------------------------------------------------------

const DUCT_ORANGE = '#ff5c00';
const DUCT_NAVY   = '#0d0f1a';
const DUCT_CREAM  = '#f4ece2';

// ---------------------------------------------------------------------------
// Score gauge — animated full-circle SVG
// ---------------------------------------------------------------------------

const CIRCLE_R    = 72;
const CIRCLE_CIRC = 2 * Math.PI * CIRCLE_R;

function gaugeColor(score) {
  if (score >= 85) return '#10b981';
  if (score >= 70) return '#f59e0b';
  if (score >= 55) return '#f97316';
  return '#ef4444';
}

const BAND_LABEL = {
  healthy:    'Healthy',
  good:       'Good',
  needs_work: 'Needs Work',
  critical:   'Critical',
};

function ScoreGauge({ score, band, dark }) {
  const [on, setOn] = React.useState(false);
  React.useEffect(() => {
    const t = setTimeout(() => setOn(true), 120);
    return () => clearTimeout(t);
  }, []);

  const filled      = on ? (score / 100) * CIRCLE_CIRC : 0;
  const color       = gaugeColor(score);
  const label       = BAND_LABEL[band] ?? band;
  const textFill    = dark ? DUCT_CREAM : 'currentColor';
  const trackStroke = dark ? 'rgba(255,255,255,0.08)' : 'currentColor';

  return (
    <div
      className="flex flex-col items-center shrink-0"
      data-tooltip={`${score}/100 — ${label}. Weighted average across all 9 SEO categories.`}
    >
      <svg viewBox="0 0 180 180" width="180" height="180" role="img"
        aria-label={`Score ${score} out of 100, ${label}`}>
        <circle cx="90" cy="90" r={CIRCLE_R} fill="none"
          stroke={trackStroke} strokeOpacity={dark ? 1 : 0.08} strokeWidth="12" />
        <circle cx="90" cy="90" r={CIRCLE_R} fill="none"
          stroke={color} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={`${filled} ${CIRCLE_CIRC}`}
          transform="rotate(-90 90 90)"
          style={{ transition: 'stroke-dasharray 1.4s cubic-bezier(0.4,0,0.2,1)' }} />
        <text x="90" y="100" textAnchor="middle" fontSize="42" fontWeight="400"
          fill={textFill} fontFamily='Georgia, "Times New Roman", serif'>{score}</text>
      </svg>
      <span className="text-xs font-semibold mt-1" style={{ color }}>{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Issue distribution pill — stacked horizontal bar in hero
// ---------------------------------------------------------------------------

function IssuePill({ issues, warnings, opportunities, categories }) {
  const passCount = (categories ?? []).reduce((s, c) => s + (c.pass_count ?? 0), 0);
  const total = issues + warnings + opportunities + passCount;
  if (total === 0) return null;

  const segs = [
    { count: issues,        color: '#ef4444', label: 'errors' },
    { count: warnings,      color: '#f59e0b', label: 'warnings' },
    { count: opportunities, color: '#f97316', label: 'opportunities' },
    { count: passCount,     color: '#10b981', label: 'passing' },
  ].filter(s => s.count > 0);

  return (
    <div className="flex items-center gap-2 mt-2" data-tooltip="Issue distribution across all findings">
      <div className="flex h-1.5 rounded-full overflow-hidden" style={{ width: 120 }}>
        {segs.map(({ count, color, label }) => (
          <div key={label} style={{ width: `${(count / total) * 100}%`, background: color }} />
        ))}
      </div>
      <span className="text-[10px] tabular-nums" style={{ color: 'rgba(244,236,226,0.4)' }}>
        {segs.map(s => `${s.count} ${s.label}`).join(' · ')}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats strip — mono number grid
// ---------------------------------------------------------------------------

function StatsStrip({ data, dateStr, dark }) {
  const valStyle  = dark ? { color: 'rgba(244,236,226,0.9)' }  : {};
  const lblStyle  = dark ? { color: 'rgba(244,236,226,0.38)' } : {};
  const borderClr = dark ? 'rgba(255,255,255,0.1)'             : 'rgba(0,0,0,0.08)';

  const stats = [
    { value: data.pages_crawled,       label: 'pages crawled' },
    { value: data.total_issues,        label: 'errors',        color: dark ? (data.total_issues > 0 ? '#f87171' : '#34d399') : (data.total_issues > 0 ? '#ef4444' : '#10b981') },
    { value: data.total_warnings,      label: 'warnings',      color: dark ? (data.total_warnings > 0 ? '#fbbf24' : 'rgba(244,236,226,0.4)') : (data.total_warnings > 0 ? '#f59e0b' : undefined) },
    { value: data.total_opportunities, label: 'opportunities', color: dark ? (data.total_opportunities > 0 ? '#fb923c' : 'rgba(244,236,226,0.4)') : (data.total_opportunities > 0 ? DUCT_ORANGE : undefined) },
    { value: dateStr,                  label: 'audit date' },
  ];

  return (
    <div style={{ paddingTop: 12, borderTop: `1px solid ${borderClr}` }}>
      <div className="flex items-center gap-6 flex-wrap">
        {stats.map(({ value, label, color }) => (
          <div key={label}>
            <div className="font-mono text-xl font-bold leading-none tabular-nums"
              style={{ ...(color ? { color } : valStyle) }}>{value}</div>
            <div className="text-xs uppercase tracking-wide mt-0.5" style={lblStyle}>{label}</div>
          </div>
        ))}
      </div>
      {dark && (
        <IssuePill
          issues={data.total_issues}
          warnings={data.total_warnings}
          opportunities={data.total_opportunities}
          categories={data.categories}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Key signals strip — 3-column coach's brief (replaces executive_summary)
// ---------------------------------------------------------------------------

const SIGNAL_ICONS  = [AlertTriangle, TrendingUp, CheckCircle2];
const SIGNAL_COLORS = [DUCT_ORANGE, '#6366f1', '#10b981'];

function KeySignals({ signals }) {
  if (!signals?.length) return null;
  return (
    <div className="rise-1 grid grid-cols-1 sm:grid-cols-3 gap-3">
      {signals.slice(0, 3).map((text, i) => {
        const Icon  = SIGNAL_ICONS[i];
        const color = SIGNAL_COLORS[i];
        return (
          <div key={i} className="flex items-start gap-3 rounded-xl px-4 py-4"
            style={{ background: color + '0d', border: `1px solid ${color}22`, transition: 'transform 0.15s, box-shadow 0.15s' }}
            onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'; }}
            onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = ''; }}>
            {Icon && <Icon size={15} style={{ color, flexShrink: 0, marginTop: 2 }} strokeWidth={2} />}
            <p className="text-[14px] leading-snug" style={{ color: 'var(--foreground)' }}>{text}</p>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section header — orange accent bar + Lucide icon
// ---------------------------------------------------------------------------

function SectionHeader({ icon: Icon, children }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div className="w-1 h-6 rounded-full shrink-0" style={{ background: DUCT_ORANGE }} />
      {Icon && <Icon size={16} color={DUCT_ORANGE} strokeWidth={2} />}
      <h2 className="text-xl font-semibold tracking-tight">{children}</h2>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Severity badge config
// ---------------------------------------------------------------------------

const SEVERITY_CFG = {
  fail:        { label: 'FAIL', accent: '#ef4444', pill: 'bg-red-500/15 text-red-700 dark:text-red-400 border border-red-500/30',             headerCls: 'bg-red-500/10'     },
  warn:        { label: 'WARN', accent: '#f59e0b', pill: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30',       headerCls: 'bg-amber-500/10'   },
  pass:        { label: 'PASS', accent: '#10b981', pill: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30', headerCls: 'bg-emerald-500/10' },
  opportunity: { label: 'OPP',  accent: '#f97316', pill: 'bg-orange-500/15 text-orange-700 dark:text-orange-400 border border-orange-500/30',    headerCls: 'bg-orange-500/10'  },
};

// ---------------------------------------------------------------------------
// Impact / effort icon chips
// ---------------------------------------------------------------------------

const IMPACT_COLOR = { critical: '#ef4444', high: '#f97316', medium: '#f59e0b', low: '#94a3b8' };
const EFFORT_COLOR = { low: '#10b981', medium: '#f59e0b', high: '#ef4444' };

const EFFORT_ESTIMATE_LABEL = {
  under_1hr:     '< 1 hr',
  '2_to_4hrs':   '2–4 hrs',
  '1_to_3_days': '1–3 days',
  '1_to_2_wks':  '1–2 wks',
  ongoing:       'Ongoing',
};

function ImpactEffortChips({ impact, effort }) {
  if (!impact && !effort) return null;
  return (
    <div className="flex gap-2 flex-wrap mt-2">
      {impact && (
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md"
          style={{ background: IMPACT_COLOR[impact] + '18', color: IMPACT_COLOR[impact] }}>
          <Zap size={10} strokeWidth={2.5} />
          {impact.charAt(0).toUpperCase() + impact.slice(1)} impact
        </span>
      )}
      {effort && (
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md"
          style={{ background: EFFORT_COLOR[effort] + '18', color: EFFORT_COLOR[effort] }}>
          <Clock size={10} strokeWidth={2.5} />
          {effort.charAt(0).toUpperCase() + effort.slice(1)} effort
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Category bar chart
// ---------------------------------------------------------------------------

function scoreBarColor(score) {
  if (score >= 85) return '#10b981';
  if (score >= 70) return '#f59e0b';
  if (score >= 55) return '#f97316';
  return '#ef4444';
}

function CategoryBarChartCSS({ categories }) {
  const [animated, setAnimated] = React.useState(false);
  React.useEffect(() => { const t = setTimeout(() => setAnimated(true), 150); return () => clearTimeout(t); }, []);

  const sorted = [...categories].sort((a, b) => b.score - a.score);
  return (
    <div className="space-y-3 py-1">
      {sorted.map((cat, i) => {
        const color = scoreBarColor(cat.score);
        return (
          <div key={cat.id} className="flex items-center gap-3" data-tooltip={cat.tooltip}>
            <span className="text-sm text-right shrink-0 w-44 text-muted-foreground truncate">{cat.label}</span>
            <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.07)' }}>
              <div className="h-full rounded-full"
                style={{
                  width: animated ? `${Math.max(cat.score, 3)}%` : '0%',
                  background: `linear-gradient(90deg, ${color}77, ${color})`,
                  transition: `width 0.9s cubic-bezier(0.4,0,0.2,1) ${i * 55}ms`,
                }} />
            </div>
            <span className="text-xs font-semibold tabular-nums shrink-0 w-6 text-right"
              style={{ color }}>{cat.score}</span>
          </div>
        );
      })}
    </div>
  );
}

function CategoryBarChart({ categories }) {
  if (typeof ResponsiveContainer === 'undefined' || typeof BarChart === 'undefined') {
    return <CategoryBarChartCSS categories={categories} />;
  }

  const sorted = [...categories].sort((a, b) => b.score - a.score);
  const chartData = sorted.map(c => ({ name: c.label, score: c.score, color: scoreBarColor(c.score) }));
  const chartHeight = Math.max(categories.length * 36, 180);

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 36, top: 2, bottom: 2 }}>
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis type="category" dataKey="name" width={152}
          tick={{ fontSize: 13, fill: 'currentColor', opacity: 0.65 }}
          axisLine={false} tickLine={false} />
        <Bar dataKey="score" radius={[0, 3, 3, 0]} barSize={8}
          background={{ fill: 'rgba(0,0,0,0.06)', radius: [0, 3, 3, 0] }}
          isAnimationActive animationDuration={900} animationEasing="ease-out">
          {chartData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
          <LabelList dataKey="score" position="right"
            style={{ fontSize: 12, fontWeight: 600, fill: 'currentColor', opacity: 0.7 }}
            formatter={v => `${v}`} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Strategic narrative — competitive landscape + content opportunity analysis
// ---------------------------------------------------------------------------

function StrategicNarrative({ narrative }) {
  if (!narrative) return null;
  const paragraphs = narrative.split(/\n\n+/).filter(Boolean);
  return (
    <section className="space-y-3">
      <SectionHeader icon={Target}>Competitive Landscape</SectionHeader>
      <div className="rounded-xl border border-slate-700 bg-slate-950 px-6 py-5 space-y-4">
        {paragraphs.map((p, i) => (
          <p key={i} className="text-sm leading-relaxed text-slate-300"
            style={{ lineHeight: '1.75' }}>{p}</p>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Impact × Effort matrix — 2×2 quadrant
// ---------------------------------------------------------------------------

const IMPACT_RANK = { critical: 3, high: 2, medium: 1, low: 0 };
const EFFORT_RANK = { low: 0, medium: 1, high: 2 };

function ImpactEffortMatrix({ categories }) {
  const findings = (categories ?? []).flatMap(c =>
    (c.findings ?? []).filter(f => f.severity !== 'pass' && f.impact && f.effort)
  );
  if (findings.length === 0) return null;

  const quadrants = [
    { key: 'qwin',  label: 'Quick Wins',  sub: 'High impact · Low effort',   bg: 'rgba(16,185,129,0.06)', border: 'rgba(16,185,129,0.2)',   textColor: '#065f46' },
    { key: 'qbet',  label: 'Big Bets',    sub: 'High impact · More effort',  bg: 'rgba(99,102,241,0.05)', border: 'rgba(99,102,241,0.18)',  textColor: '#3730a3' },
    { key: 'qfil',  label: 'Fill-In',     sub: 'Lower impact · Low effort',  bg: 'rgba(245,158,11,0.05)', border: 'rgba(245,158,11,0.18)', textColor: '#92400e' },
    { key: 'qskip', label: 'Later',       sub: 'Lower impact · More effort', bg: 'rgba(148,163,184,0.05)', border: 'rgba(148,163,184,0.15)', textColor: '#475569' },
  ];

  function assignQuadrant(f) {
    const ir = IMPACT_RANK[f.impact] ?? 1;
    const er = EFFORT_RANK[f.effort] ?? 1;
    if (ir >= 2 && er === 0) return 'qwin';
    if (ir >= 2)             return 'qbet';
    if (er === 0)            return 'qfil';
    return 'qskip';
  }

  const groups = {};
  quadrants.forEach(q => { groups[q.key] = []; });
  findings.forEach(f => { groups[assignQuadrant(f)].push(f); });

  const SEVERITY_DOT = { fail: '#ef4444', warn: '#f59e0b', opportunity: '#f97316' };

  return (
    <section className="rise-5 space-y-3">
      <SectionHeader icon={Target}>Impact × Effort</SectionHeader>
      <div className="grid grid-cols-2 gap-3">
        {quadrants.map(q => (
          <div key={q.key} className="rounded-xl p-4 space-y-2.5"
            style={{ background: q.bg, border: `1px solid ${q.border}` }}>
            <div>
              <p className="text-[13px] font-bold" style={{ color: q.textColor }}>{q.label}</p>
              <p className="text-[10px] text-muted-foreground/70">{q.sub}</p>
            </div>
            {groups[q.key].length === 0
              ? <p className="text-[11px] text-muted-foreground/50 italic">Nothing here</p>
              : (
                <ul className="space-y-1.5">
                  {groups[q.key].map(f => (
                    <li key={f.id} className="flex items-start gap-2" data-tooltip={f.description || f.title}>
                      <span className="shrink-0 mt-1.5 size-1.5 rounded-full"
                        style={{ background: SEVERITY_DOT[f.severity] ?? '#94a3b8' }} />
                      <span className="text-[12px] leading-snug text-foreground/80 line-clamp-2">{f.title}</span>
                    </li>
                  ))}
                </ul>
              )
            }
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// PASS row — compact checkmark, no description card
// ---------------------------------------------------------------------------

function PassRow({ finding }) {
  return (
    <div className="flex items-center gap-3 py-2.5 px-4 rounded-lg"
      style={{ background: 'rgba(16,185,129,0.04)', border: '1px solid rgba(16,185,129,0.14)' }}>
      <CheckCircle2 size={13} color="#10b981" strokeWidth={2} className="shrink-0" />
      <span className="text-[14px] text-foreground/80 leading-snug flex-1 min-w-0">{finding.title}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Finding card — compact: 1-sentence description, → Fix: callout
// ---------------------------------------------------------------------------

function FindingCard({ finding }) {
  const cfg = SEVERITY_CFG[finding.severity] ?? SEVERITY_CFG.pass;

  if (finding.severity === 'pass') return <PassRow finding={finding} />;

  return (
    <div className="rounded-xl overflow-hidden"
      style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.07)', border: '1px solid ' + cfg.accent + '22', transition: 'box-shadow 0.15s, transform 0.15s' }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 14px rgba(0,0,0,0.10)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.07)'; e.currentTarget.style.transform = ''; }}>

      {/* 3px top stripe */}
      <div style={{ height: 3, background: cfg.accent }} />

      {/* Colored header row: badge + title */}
      <div className={`flex items-start gap-3 px-5 pt-3 pb-3 ${cfg.headerCls}`}>
        <span className={`text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md shrink-0 mt-0.5 ${cfg.pill}`}>
          {cfg.label}
        </span>
        <p className="text-[15px] font-semibold leading-snug text-foreground flex-1 min-w-0">
          {finding.title}
        </p>
      </div>

      {/* Body */}
      <div className="px-5 pt-3 pb-4 space-y-3 bg-card">

        {finding.description && (
          <p className="text-sm text-muted-foreground leading-relaxed">
            {finding.description}
          </p>
        )}

        {finding.affected_urls?.length > 0 && (
          <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--border)' }}>
            <div className="flex px-4 py-2 bg-muted/40 border-b border-border/60">
              <span className="flex-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">URL</span>
              <span className="w-48 shrink-0 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">Measured</span>
            </div>
            {finding.affected_urls.map((u, i) => (
              <div key={i} className={`flex items-start px-4 py-2.5 bg-card${i > 0 ? ' border-t border-border/40' : ''}`}>
                <code className="flex-1 text-xs font-mono text-muted-foreground/70 break-all pr-3">{u.url}</code>
                <span className="w-48 shrink-0 text-sm font-semibold text-foreground/80">{u.issue_value}</span>
              </div>
            ))}
          </div>
        )}

        {finding.recommendation && (
          <div className="rounded-lg px-4 py-3 bg-blue-500/10">
            <p className="text-sm leading-relaxed text-foreground/80">
              <span className="font-semibold text-blue-600 dark:text-blue-400">Fix: </span>
              {finding.recommendation}
            </p>
          </div>
        )}

        <ImpactEffortChips impact={finding.impact} effort={finding.effort} />

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Findings accordion per category
// ---------------------------------------------------------------------------

const SEVERITY_ORDER = { fail: 0, warn: 1, opportunity: 2, pass: 3 };

function CategoryAccordion({ category, isLast }) {
  const ordered = [...(category.findings ?? [])].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4),
  );
  const hasBad         = category.fail_count > 0 || category.warn_count > 0;
  const color          = scoreBarColor(category.score);
  const passFindings   = ordered.filter(f => f.severity === 'pass');
  const nonPassFindings = ordered.filter(f => f.severity !== 'pass');

  return (
    <details className={`group${!isLast ? ' border-b border-border/60' : ''}`} open={hasBad || undefined}>
      <summary className="flex items-center justify-between gap-3 px-5 py-4 cursor-pointer hover:bg-muted/40 transition-colors select-none">
        <div className="flex items-center gap-3 min-w-0 flex-wrap">
          <div className="size-8 rounded-lg flex items-center justify-center text-xs font-bold shrink-0"
            style={{ background: color + '1a', color }}>{category.score}</div>
          <span className="text-[15px] font-semibold">{category.label}</span>
          <div className="flex items-center gap-1.5 flex-wrap">
            {category.fail_count > 0 && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-500/15 text-red-700 dark:text-red-400">
                {category.fail_count} Error{category.fail_count !== 1 ? 's' : ''}
              </span>
            )}
            {category.warn_count > 0 && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-400">
                {category.warn_count} Warning{category.warn_count !== 1 ? 's' : ''}
              </span>
            )}
            {!hasBad && category.opp_count > 0 && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-orange-500/15 text-orange-700 dark:text-orange-400">
                {category.opp_count} Opp
              </span>
            )}
            {!hasBad && !category.opp_count && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-green-500/15 text-green-700 dark:text-green-400 hidden sm:inline">
                All clear
              </span>
            )}
          </div>
        </div>
        <span className="text-muted-foreground text-xs shrink-0 transition-transform duration-200 group-open:rotate-180">▼</span>
      </summary>
      <div className="px-5 pb-4 pt-3 space-y-3" style={{ background: 'rgba(0,0,0,0.02)' }}>
        {ordered.length === 0 && (
          <p className="text-sm text-muted-foreground py-2">No findings for this category.</p>
        )}

        {/* Non-pass findings rendered as full cards */}
        {nonPassFindings.map(f => <FindingCard key={f.id} finding={f} />)}

        {/* PASS findings collapsed into a single expandable summary row */}
        {passFindings.length > 0 && (
          <details className="group/pass">
            <summary className="flex items-center gap-2 cursor-pointer select-none py-1.5">
              <CheckCircle2 size={13} color="#10b981" strokeWidth={2} className="shrink-0" />
              <span className="text-[13px] text-emerald-700 dark:text-emerald-400 font-medium">
                {passFindings.length} check{passFindings.length !== 1 ? 's' : ''} passing
              </span>
              <span className="text-muted-foreground text-[10px] ml-1 transition-transform group-open/pass:rotate-180">▼</span>
            </summary>
            <div className="ml-5 mt-2 space-y-1.5">
              {passFindings.map(f => <PassRow key={f.id} finding={f} />)}
            </div>
          </details>
        )}
      </div>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Priority card — compact: rank + title + effort chip (no why_it_matters)
// ---------------------------------------------------------------------------

const PRIORITY_STYLE = {
  fail:        { accent: '#ef4444', rankBg: 'rgba(239,68,68,0.1)',   rankColor: '#ef4444', badgeCls: 'bg-red-500/15 text-red-700 dark:text-red-400 border border-red-500/30',         label: 'Error'       },
  warn:        { accent: '#f59e0b', rankBg: 'rgba(245,158,11,0.1)',  rankColor: '#b45309', badgeCls: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30',   label: 'Warning'     },
  opportunity: { accent: '#f97316', rankBg: 'rgba(249,115,22,0.1)',  rankColor: '#c2410c', badgeCls: 'bg-orange-500/15 text-orange-700 dark:text-orange-400 border border-orange-500/30', label: 'Opportunity' },
};

function PriorityCard({ priority }) {
  const s = PRIORITY_STYLE[priority.severity] ?? { accent: '#94a3b8', rankBg: 'rgba(148,163,184,0.1)', rankColor: '#64748b', badgeCls: 'bg-slate-100 text-slate-600 border border-slate-200', label: 'Note' };
  const effortLabel = priority.effort_estimate
    ? (EFFORT_ESTIMATE_LABEL[priority.effort_estimate] ?? priority.effort_estimate)
    : null;

  return (
    <div className="rounded-xl overflow-hidden bg-card"
      style={{ border: '1px solid var(--border)', boxShadow: '0 1px 3px rgba(0,0,0,0.07)', transition: 'box-shadow 0.15s, transform 0.15s' }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.07)'; e.currentTarget.style.transform = ''; }}>
      <div style={{ height: 3, background: s.accent }} />
      <div className="flex items-center gap-4 px-5 py-4">
        <div className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold tabular-nums"
          style={{ background: s.rankBg, color: s.rankColor }}>
          {String(priority.rank).padStart(2, '0')}
        </div>
        <p className="flex-1 min-w-0 text-[15px] font-semibold leading-snug text-foreground">
          {priority.title}
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-[10px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-md ${s.badgeCls}`}>
            {s.label}
          </span>
          {effortLabel && (
            <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-md border border-border bg-muted/40 text-muted-foreground">
              <Clock size={10} strokeWidth={2} />
              {effortLabel}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Crawl health summary strip
// ---------------------------------------------------------------------------

function statColor(value, thresholds) {
  if (thresholds.fail != null && value >= thresholds.fail) return { text: 'text-red-600 dark:text-red-400' };
  if (thresholds.warn != null && value >= thresholds.warn) return { text: 'text-amber-600 dark:text-amber-400' };
  return { text: 'text-green-600 dark:text-green-400' };
}

const NEUTRAL_COLOR = { text: 'text-muted-foreground' };

const CRAWL_STATS = [
  { key: 'avg_ttfb_ms',          label: 'Avg TTFB',  format: v => `${Math.round(v)}ms`, thresholds: { warn: 800, fail: 2000 }, tooltip: 'Time to first byte. Google de-prioritises slow sites for recrawl.' },
  { key: 'pages_with_redirects', label: 'Redirects', format: v => String(v),            thresholds: { warn: 1, fail: null },   tooltip: 'Each redirect hop bleeds crawl budget and PageRank.' },
  { key: 'spa_pages_count',      label: 'SPA pages', format: v => String(v),            thresholds: { warn: 1, fail: null },   tooltip: 'Client-rendered pages — Google Wave 1 may see empty content.' },
  { key: 'pages_noindex',        label: 'Noindex',   format: v => String(v),            thresholds: null,                      tooltip: 'Pages excluded from the index. Verify these are intentional.' },
  { key: 'pages_missing_title',  label: 'No title',  format: v => String(v),            thresholds: { warn: 1, fail: 1 },      tooltip: 'Missing title tags are a direct ranking signal failure.' },
  { key: 'pages_missing_h1',     label: 'No H1',     format: v => String(v),            thresholds: { warn: 1, fail: null },   tooltip: 'Pages without an H1 miss the primary on-page relevance signal.' },
];

function CrawlSummaryStrip({ summary }) {
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
      {CRAWL_STATS.map(({ key, label, format, thresholds, tooltip }) => {
        const value = summary[key] ?? 0;
        const color = thresholds ? statColor(value, thresholds) : NEUTRAL_COLOR;
        const isFail  = thresholds?.fail != null && value >= thresholds.fail;
        const isWarn  = !isFail && thresholds?.warn != null && value >= thresholds.warn;
        const isGood  = thresholds && !isFail && !isWarn;
        const cellBg  = isFail ? 'rgba(239,68,68,0.05)' : isWarn ? 'rgba(245,158,11,0.05)' : isGood ? 'rgba(16,185,129,0.05)' : 'white';
        const cellBdr = isFail ? 'rgba(239,68,68,0.25)' : isWarn ? 'rgba(245,158,11,0.22)' : isGood ? 'rgba(16,185,129,0.22)' : undefined;
        return (
          <div key={key}
            className="rounded-xl px-4 py-4 flex flex-col gap-1"
            style={{ background: cellBg, border: `1px solid ${cellBdr ?? 'var(--border)'}`, boxShadow: '0 1px 2px rgba(13,15,26,0.04)' }}
            data-tooltip={tooltip}>
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wide leading-none">{label}</span>
            <span className={`text-xl font-bold tabular-nums leading-tight ${color.text}`}>{format(value)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Wins strip — 2-col compact cards
// ---------------------------------------------------------------------------

function WinsStrip({ wins }) {
  return (
    <section className="rise-4 rounded-xl overflow-hidden"
      style={{ background: 'rgba(16,185,129,0.04)', border: '1px solid rgba(16,185,129,0.18)' }}>
      <div className="px-5 py-5 sm:px-6 sm:py-5">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-1 h-6 rounded-full shrink-0" style={{ background: '#16a34a' }} />
          <CheckCircle2 size={16} color="#16a34a" strokeWidth={2} />
          <h2 className="text-xl font-semibold tracking-tight">What&apos;s Going Right</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {wins.map((w, i) => (
            <div key={i} className="flex items-center gap-2.5 rounded-lg border border-green-100 bg-card px-4 py-2.5"
              style={{ transition: 'box-shadow 0.15s' }}
              onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 2px 8px rgba(16,185,129,0.12)'; }}
              onMouseLeave={e => { e.currentTarget.style.boxShadow = ''; }}>
              <CheckCircle2 size={13} color="#16a34a" className="shrink-0" />
              <span className="text-[14px] leading-snug">{w}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Roadmap section — effort_estimate chips instead of verbose notes
// ---------------------------------------------------------------------------

const PHASE_THEME_COLOR = {
  'Unblock':  { text: DUCT_ORANGE, bg: 'rgba(255,92,0,0.08)',    border: 'rgba(255,92,0,0.2)' },
  'Structure': { text: '#b45309',  bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.25)' },
  'Compound':  { text: '#166534',  bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.2)' },
};

function RoadmapSection({ roadmap }) {
  return (
    <section className="rise-8 space-y-3">
      <SectionHeader icon={Calendar}>Action Plan</SectionHeader>
      <div className="space-y-3">
        {roadmap.map((phase, i) => {
          const cfg = PHASE_THEME_COLOR[phase.theme] ?? { text: '#6b7280', bg: 'rgba(107,114,128,0.08)', border: 'rgba(107,114,128,0.2)' };
          return (
            <div key={i} className="rounded-xl bg-card p-5 sm:p-6 space-y-3"
              style={{ border: '1px solid var(--border)', boxShadow: '0 1px 2px rgba(13,15,26,0.04)' }}>
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded-full border"
                  style={{ color: cfg.text, background: cfg.bg, borderColor: cfg.border }}>
                  {phase.label}
                </span>
                <span className="text-base font-semibold" style={{ color: cfg.text }}>{phase.theme}</span>
              </div>
              <ul className="space-y-0 divide-y divide-border/20">
                {phase.tasks.map((t, j) => {
                  const effortLabel = t.effort_estimate
                    ? (EFFORT_ESTIMATE_LABEL[t.effort_estimate] ?? t.effort_estimate)
                    : t.note || null;
                  return (
                    <li key={j} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                      <span className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold tabular-nums"
                        style={{ background: cfg.text + '18', color: cfg.text }}>
                        {String(j + 1).padStart(2, '0')}
                      </span>
                      <p className="flex-1 text-[15px] leading-relaxed min-w-0">{t.task}</p>
                      {effortLabel && (
                        <span className="shrink-0 inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md border border-border bg-muted/40 text-muted-foreground">
                          <Clock size={10} strokeWidth={2} />
                          {effortLabel}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
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

  const dateStr = data.generated_at
    ? new Date(data.generated_at).toLocaleDateString('en-US', {
        day: 'numeric', month: 'short', year: 'numeric',
      })
    : '';

  // Support both new key_signals (array) and old executive_summary (string fallback)
  const keySignals = Array.isArray(data.key_signals) && data.key_signals.length
    ? data.key_signals
    : data.executive_summary
      ? [data.executive_summary.slice(0, 120)]
      : [];

  return (
    <div
      className="min-h-full text-foreground"
      style={{
        // Neutral chrome adapts to the app theme via CSS vars; the orange radial
        // accents and the dark hero/accent palette stay fixed (they read on both).
        background: `
          radial-gradient(900px 500px at 90% 0%, rgba(255,92,0,0.07), transparent 60%),
          radial-gradient(700px 600px at -5% 30%, rgba(255,92,0,0.04), transparent 55%),
          var(--background)
        `,
      }}
    >
      <style>{GLOBAL_STYLE}</style>

      <div className="max-w-4xl mx-auto px-4 py-10 sm:py-14 space-y-8">

        {/* ── Dark hero card ───────────────────────────────────────────── */}
        <div className="rise-0 rounded-2xl overflow-hidden shadow-xl"
          style={{ background: DUCT_NAVY }}>
          <div className="px-8 pt-8 pb-7 flex items-start justify-between gap-6 flex-wrap">
            <div className="flex-1 min-w-0 space-y-4">
              <p className="text-xs font-medium tracking-wide truncate"
                style={{ color: DUCT_ORANGE }}>{data.url}</p>
              <h1 style={{
                fontFamily: 'Georgia, "Times New Roman", serif',
                color: DUCT_CREAM,
                fontSize: 'clamp(1.7rem, 4vw, 2.5rem)',
                fontWeight: 700,
                lineHeight: 1.2,
                letterSpacing: '-0.02em',
                margin: 0,
              }}>
                {data.headline || 'SEO Audit Report'}
              </h1>
              <StatsStrip data={data} dateStr={dateStr} dark />
            </div>
            <ScoreGauge score={data.overall_score} band={data.score_band} dark />
          </div>
          <div style={{ height: 3, background: 'linear-gradient(90deg, #ff5c00, #ff8c42 60%, transparent)' }} />
        </div>

        {/* ── Key signals — 3-column brief (replaces paragraph summary) ─ */}
        {keySignals.length > 0 && <KeySignals signals={keySignals} />}

        {/* ── Coverage banner ──────────────────────────────────────────── */}
        {showCoverageBanner && (
          <div className="rise-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
            data-tooltip="Only a sample of your sitemap was scanned.">
            <span className="font-semibold">Limited scan: </span>
            Based on {data.pages_crawled} of {data.total_sitemap_urls} sitemap pages.
          </div>
        )}

        {/* ── Crawl health ─────────────────────────────────────────────── */}
        {data.crawl_summary && (
          <section className="rise-3 space-y-3">
            <SectionHeader icon={Activity}>Crawl Health</SectionHeader>
            <CrawlSummaryStrip summary={data.crawl_summary} />
          </section>
        )}

        {/* ── What's going right ───────────────────────────────────────── */}
        {data.wins?.length > 0 && <WinsStrip wins={data.wins} />}

        {/* ── Competitive landscape / strategic narrative ───────────────── */}
        {data.strategic_narrative && <StrategicNarrative narrative={data.strategic_narrative} />}

        {/* ── Fix these first ──────────────────────────────────────────── */}
        {data.top_priorities?.length > 0 && (
          <section className="rise-5 space-y-3">
            <SectionHeader icon={AlertTriangle}>Fix These First</SectionHeader>
            <div className="space-y-2">
              {data.top_priorities.map(p => <PriorityCard key={p.rank} priority={p} />)}
            </div>
          </section>
        )}

        {/* ── Impact × Effort matrix ───────────────────────────────────── */}
        {data.categories?.length > 0 && (
          <ImpactEffortMatrix categories={data.categories} />
        )}

        {/* ── Category scores ──────────────────────────────────────────── */}
        {data.categories?.length > 0 && (
          <section className="rise-6 space-y-3">
            <SectionHeader icon={BarChart2}>Category Scores</SectionHeader>
            <div className="rounded-xl bg-card px-5 py-5"
              style={{ border: '1px solid var(--border)', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
              <CategoryBarChart categories={data.categories} />
            </div>
          </section>
        )}

        {/* ── Findings accordion ───────────────────────────────────────── */}
        {data.categories?.length > 0 && (
          <section className="rise-7 space-y-3">
            <SectionHeader icon={Target}>Findings by Category</SectionHeader>
            <div className="rounded-xl overflow-hidden bg-card"
              style={{ border: '1px solid var(--border)', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
              {data.categories.map((cat, i) => (
                <CategoryAccordion
                  key={cat.id}
                  category={cat}
                  isLast={i === data.categories.length - 1}
                />
              ))}
            </div>
          </section>
        )}

        {/* ── Action plan roadmap ──────────────────────────────────────── */}
        {data.roadmap?.length > 0 && <RoadmapSection roadmap={data.roadmap} />}

        {/* ── Footer ───────────────────────────────────────────────────── */}
        <footer className="text-center text-xs pt-4 border-t border-border/40"
          style={{ color: 'rgba(13,15,26,0.3)' }}>
          Generated by{' '}
          <span style={{ color: DUCT_ORANGE, fontWeight: 600 }}>Duct</span>
          {' '}· getduct.ai
        </footer>

      </div>
    </div>
  );
}
