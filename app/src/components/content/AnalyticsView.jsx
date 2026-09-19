"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowUpDown,
  BarChart2,
  ExternalLink,
  Eye,
  Heart,
  MessageCircle,
  RefreshCw,
  Share2,
  TrendingUp,
} from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import EmptyState from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { getContentAnalytics } from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import { dayKey, formatDate, formatNumber, titleCase, toDate } from "@/lib/format";

// Sort keys are API-ish identifiers; these are what the buttons say.
const SORT_LABELS = {
  views: msg`Views`,
  likes: msg`Likes`,
  date: msg`Date`,
};

// share_url comes from the third-party Post-Bridge API, so treat it as untrusted:
// only render it as a link when it resolves to an http(s) URL. Blocks javascript:
// and other script-bearing schemes from reaching an href.
function safeHref(u) {
  if (typeof u !== "string" || !u) return null;
  try {
    const url = new URL(u, typeof window !== "undefined" ? window.location.origin : "https://getduct.ai");
    return /^https?:$/.test(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}


export default function AnalyticsView({ projectId, onLinkAccounts }) {
  const { t, i18n } = useLingui();
  // Axis/cell dates follow the interface language, as the labels around them do.
  const shortDate = (d) => formatDate(d, { withYear: false, locale: i18n.locale, fallback: "—" });
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [sortKey, setSortKey] = useState("views"); // views | likes | date

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true); else setLoading(true);
    setError("");
    try {
      const data = await getContentAnalytics(projectId, { refresh });
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e.message || t`Couldn't load analytics.`);
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => { load(false); }, [load]);

  const totals = useMemo(() => rows.reduce(
    (a, r) => ({
      views: a.views + (r.view_count || 0),
      likes: a.likes + (r.like_count || 0),
      comments: a.comments + (r.comment_count || 0),
      shares: a.shares + (r.share_count || 0),
    }),
    { views: 0, likes: 0, comments: 0, shares: 0 }
  ), [rows]);

  const avgViews = rows.length ? Math.round(totals.views / rows.length) : 0;
  const postCount = formatNumber(rows.length);
  const avgViewsText = formatNumber(avgViews);
  const engagement = totals.likes + totals.comments + totals.shares;
  const engagementRate = totals.views ? (engagement / totals.views) * 100 : 0;

  // Views over time — aggregate by day.
  const timeline = useMemo(() => {
    const byDay = new Map();
    for (const r of rows) {
      const d = toDate(r.platform_created_at);
      if (!d) continue;
      const k = dayKey(d);
      const cur = byDay.get(k) || { key: k, date: d, views: 0 };
      cur.views += r.view_count || 0;
      byDay.set(k, cur);
    }
    return [...byDay.values()]
      .sort((a, b) => a.date - b.date)
      .map((x) => ({ label: shortDate(x.date), views: x.views }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, i18n.locale]);

  // Top posts by views.
  const topPosts = useMemo(
    () => [...rows]
      .sort((a, b) => (b.view_count || 0) - (a.view_count || 0))
      .slice(0, 8)
      .map((r, i) => ({ ...r, rank: i + 1, name: (r.title || platformMeta(r.platform).label).slice(0, 28) })),
    [rows]
  );

  // Breakdown by pillar / format — over posts attributed to our system.
  const pillarData = useMemo(() => aggregateBy(rows, "pillar", prettify), [rows]);
  const formatData = useMemo(() => aggregateBy(rows, "format_name", (f) => f || ""), [rows]);

  const rowCount = rows.length;
  const sortedRows = useMemo(() => {
    const copy = [...rows];
    if (sortKey === "likes") copy.sort((a, b) => (b.like_count || 0) - (a.like_count || 0));
    else if (sortKey === "date") copy.sort((a, b) => (toDate(b.platform_created_at)?.getTime() || 0) - (toDate(a.platform_created_at)?.getTime() || 0));
    else copy.sort((a, b) => (b.view_count || 0) - (a.view_count || 0));
    return copy;
  }, [rows, sortKey]);

  return (
    <div className="max-w-6xl space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight"><Trans>Analytics</Trans></h2>
          <p className="text-sm text-muted-foreground">
            <Trans>Live performance from PostBridge across your linked accounts.</Trans>
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => load(true)} disabled={refreshing || loading}>
          <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? <Trans>Syncing…</Trans> : <Trans>Refresh from PostBridge</Trans>}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
          <RefreshCw className="size-4 animate-spin" /> <Trans>Fetching analytics from PostBridge…</Trans>
        </div>
      ) : rows.length === 0 ? (
        // "Link the accounts in the Accounts tab" was a correct instruction
        // with nothing to click, on the one tab where the reader has already
        // decided they want this to work. The button is that same sentence.
        <EmptyState
          icon={BarChart2}
          title={t`No analytics yet`}
          actions={
            <>
              {onLinkAccounts && (
                <Button size="sm" onClick={onLinkAccounts}>
                  <Trans>Link an account</Trans>
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => load(true)} disabled={refreshing}>
                <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" />
                {refreshing ? <Trans>Syncing…</Trans> : <Trans>Refresh from PostBridge</Trans>}
              </Button>
            </>
          }
        >
          <Trans>Numbers arrive once posts go out through PostBridge and the accounts are linked.</Trans>
        </EmptyState>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-3 @4xl:grid-cols-5">
            <StatCard icon={Eye} label={t`Views`} value={formatNumber(totals.views)} accent="text-info" />
            <StatCard icon={Heart} label={t`Likes`} value={formatNumber(totals.likes)} accent="text-destructive" />
            <StatCard icon={MessageCircle} label={t`Comments`} value={formatNumber(totals.comments)} accent="text-primary" />
            <StatCard icon={Share2} label={t`Shares`} value={formatNumber(totals.shares)} accent="text-success" />
            <StatCard icon={TrendingUp} label={t`Engagement`} value={`${engagementRate.toFixed(1)}%`} sub={t`${postCount} posts · ${avgViewsText} avg views`} accent="text-warning" />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 gap-4 @2xl:grid-cols-2">
            <ChartCard title={t`Views over time`}>
              {timeline.length > 1 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={timeline} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <defs>
                      <linearGradient id="viewsFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
                    <YAxis tickFormatter={compact} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={44} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="views" stroke="var(--primary)" strokeWidth={2} fill="url(#viewsFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart label={t`Not enough dated posts to chart a trend yet.`} />
              )}
            </ChartCard>

            <ChartCard title={t`Top posts by views`}>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={topPosts} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
                  <XAxis type="number" tickFormatter={compact} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--muted)", opacity: 0.4 }} />
                  <Bar dataKey="view_count" radius={[0, 4, 4, 0]}>
                    {topPosts.map((p) => (
                      <Cell key={p.id} fill={platformMeta(p.platform).color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          {/* Breakdown by pillar / format (attributed posts) */}
          {(pillarData.length > 0 || formatData.length > 0) && (
            <div className="grid grid-cols-1 gap-4 @2xl:grid-cols-2">
              <ChartCard title={t`Views by pillar`}>
                {pillarData.length ? <CategoryBars data={pillarData} /> : <EmptyChart label={t`No pillar-attributed posts yet.`} />}
              </ChartCard>
              <ChartCard title={t`Views by format`}>
                {formatData.length ? <CategoryBars data={formatData} /> : <EmptyChart label={t`No format-attributed posts yet.`} />}
              </ChartCard>
            </div>
          )}

          {/* Posts table */}
          <div className="overflow-hidden rounded-2xl border border-border">
            <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
              <h3 className="text-sm font-semibold"><Trans>All posts <span className="text-muted-foreground tabular-nums">· {rowCount}</span></Trans></h3>
              <div className="flex items-center gap-1.5">
                <ArrowUpDown className="size-3 text-muted-foreground" />
                {["views", "likes", "date"].map((k) => (
                  <button
                    key={k}
                    onClick={() => setSortKey(k)}
                    className={`rounded px-2 py-0.5 text-xs font-medium capitalize transition-colors ${
                      sortKey === k ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    {i18n._(SORT_LABELS[k])}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium"><Trans>Post</Trans></th>
                    <th className="px-3 py-2 text-left font-medium"><Trans>Date</Trans></th>
                    <th className="px-3 py-2 text-right font-medium"><Trans>Views</Trans></th>
                    <th className="px-3 py-2 text-right font-medium"><Trans>Likes</Trans></th>
                    <th className="px-3 py-2 text-right font-medium"><Trans>Comments</Trans></th>
                    <th className="px-3 py-2 text-right font-medium"><Trans>Shares</Trans></th>
                    <th className="px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((r) => {
                    const meta = platformMeta(r.platform);
                    const d = toDate(r.platform_created_at);
                    return (
                      <tr key={r.id} className="border-t border-border/60 hover:bg-muted/20">
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2.5">
                            {r.cover_image_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={r.cover_image_url} alt="" className="h-12 w-8 shrink-0 rounded object-cover border border-border/60" />
                            ) : (
                              <span className="flex h-12 w-8 shrink-0 items-center justify-center rounded text-white" style={{ backgroundColor: meta.color }}>
                                <PlatformGlyph platform={r.platform} className="size-3.5" />
                              </span>
                            )}
                            <div className="min-w-0 max-w-[320px]">
                              <p className="flex items-center gap-1.5 text-muted-foreground">
                                <PlatformGlyph platform={r.platform} className="size-3 shrink-0" />
                                <span className="text-2xs uppercase tracking-wide">{meta.label}</span>
                                {r.published_via === "duct" && (
                                  <span className="rounded-full bg-primary/10 px-1.5 py-px text-2xs font-semibold text-primary"><Trans>via Duct</Trans></span>
                                )}
                                {r.pillar && (
                                  <span className="rounded-full bg-muted px-1.5 py-px text-2xs font-medium text-muted-foreground">{titleCase(r.pillar)}</span>
                                )}
                              </p>
                              <p className="line-clamp-2 text-xs text-foreground">{r.title || <span className="italic text-muted-foreground"><Trans>No caption</Trans></span>}</p>
                            </div>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">{shortDate(d)}</td>
                        <td className="px-3 py-2 text-right font-medium numeric">{formatNumber(r.view_count)}</td>
                        <td className="px-3 py-2 text-right numeric">{formatNumber(r.like_count)}</td>
                        <td className="px-3 py-2 text-right numeric">{formatNumber(r.comment_count)}</td>
                        <td className="px-3 py-2 text-right numeric">{formatNumber(r.share_count)}</td>
                        <td className="px-2 py-2 text-right">
                          {safeHref(r.share_url) && (
                            <a href={safeHref(r.share_url)} target="_blank" rel="noopener noreferrer" className="inline-flex text-muted-foreground hover:text-foreground" title={t`Open post`}>
                              <ExternalLink className="size-3.5" />
                            </a>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, accent = "text-foreground" }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="flex items-center gap-1.5">
        <Icon className={`size-3.5 ${accent}`} />
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
      </div>
      <p className="mt-1.5 text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-2xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

/** Sum views grouped by a row key, over attributed rows only. Sorted desc. */
function aggregateBy(rows, key, label) {
  const map = new Map();
  for (const r of rows) {
    const raw = r[key];
    if (!raw) continue;
    const name = label(raw);
    map.set(name, (map.get(name) || 0) + (r.view_count || 0));
  }
  return [...map.entries()]
    .map(([name, views]) => ({ name, views }))
    .sort((a, b) => b.views - a.views);
}

function CategoryBars({ data }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
        <XAxis type="number" tickFormatter={compact} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--muted)", opacity: 0.4 }} />
        <Bar dataKey="views" fill="var(--primary)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function ChartCard({ title, children }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </div>
  );
}

function EmptyChart({ label }) {
  return (
    <div className="flex h-[220px] items-center justify-center text-center text-xs text-muted-foreground">
      {label}
    </div>
  );
}

// Every chart here counts views, so the tooltip owns that word instead of
// taking a " views" suffix to splice onto a number a translator cannot reorder.
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  const name = p.payload?.title || p.payload?.name || label;
  const views = p.value ?? 0;
  return (
    <div className="rounded-lg border border-border bg-popover px-2.5 py-1.5 text-xs shadow-md">
      {name && <p className="mb-0.5 max-w-[220px] truncate font-medium">{name}</p>}
      <p className="tabular-nums text-muted-foreground">
        <Plural value={views} one="# view" other="# views" />
      </p>
    </div>
  );
}
