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
  Check,
  ChevronDown,
  ExternalLink,
  Eye,
  Heart,
  MessageCircle,
  RefreshCw,
  Share2,
  TrendingUp,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { getContentAnalytics, peekAnalytics } from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import { AccountAvatar } from "./AccountAvatar";

const fmt = (n) => (typeof n === "number" ? n.toLocaleString() : "—");
const compact = (n) =>
  typeof n === "number"
    ? Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n)
    : "—";

// Last upstream sync per project. Module-scoped so it survives the tab-switch
// remounts — we auto-revalidate in the background at most this often; the manual
// Refresh button always bypasses it.
const lastSyncAt = new Map();
const SYNC_THROTTLE_MS = 60_000;

// share_url comes from the third-party analytics provider, so treat it as untrusted:
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

function parseDate(s) {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}
function dayKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function shortDate(d) {
  return d ? d.toLocaleDateString("en", { month: "short", day: "numeric" }) : "—";
}

export default function AnalyticsView({ projectId }) {
  // Paint the last-known rows instantly (even if the cache TTL lapsed); only
  // show the loader on a true cold start with nothing cached.
  const [rows, setRows] = useState(() => peekAnalytics(projectId) || []);
  const [loading, setLoading] = useState(() => peekAnalytics(projectId) == null);
  const [updating, setUpdating] = useState(false); // background revalidate in flight
  const [error, setError] = useState("");
  const [sortKey, setSortKey] = useState("views"); // views | likes | date
  const [accountId, setAccountId] = useState(null); // null = all accounts

  // Pull fresh numbers from the source and swap them in. Surfaced as a background
  // "Updating…" state — the existing dashboard stays visible and interactive.
  const refresh = useCallback(async () => {
    setUpdating(true);
    setError("");
    try {
      const data = await getContentAnalytics(projectId, { refresh: true });
      setRows(Array.isArray(data) ? data : []);
      lastSyncAt.set(projectId, Date.now());
    } catch (e) {
      setError(e.message || "Couldn't update analytics.");
    } finally {
      setUpdating(false);
    }
  }, [projectId]);

  // Stale-while-revalidate: paint whatever we already have instantly (fast read,
  // no upstream sync), then revalidate in the background — never block the UI.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Don't force the loader here — the initial state is seeded from cache, so
      // we only block when there was nothing to seed (loading already true).
      try {
        const existing = await getContentAnalytics(projectId, { refresh: false });
        if (!cancelled) setRows(Array.isArray(existing) ? existing : []);
      } catch {
        // Ignore — the background revalidate below surfaces any real failure.
      } finally {
        if (!cancelled) setLoading(false);
      }
      if (cancelled) return;
      if (Date.now() - (lastSyncAt.get(projectId) || 0) > SYNC_THROTTLE_MS) {
        await refresh();
      }
    })();
    return () => { cancelled = true; };
  }, [projectId, refresh]);

  // Distinct accounts present in the analytics data, for the filter dropdown.
  // Derived from all rows so the menu always lists every account with data.
  const accounts = useMemo(() => {
    const map = new Map();
    for (const r of rows) {
      const id = r.social_account_id;
      if (id == null) continue;
      const cur = map.get(id) || { id, platform: r.platform, username: r.account_username || "", count: 0 };
      cur.count += 1;
      if (!cur.username && r.account_username) cur.username = r.account_username;
      map.set(id, cur);
    }
    return [...map.values()].sort((a, b) => b.count - a.count);
  }, [rows]);

  // Drop the active filter if its account is no longer present (e.g. after refresh).
  useEffect(() => {
    if (accountId != null && !accounts.some((a) => a.id === accountId)) setAccountId(null);
  }, [accounts, accountId]);

  const filteredRows = useMemo(
    () => (accountId == null ? rows : rows.filter((r) => r.social_account_id === accountId)),
    [rows, accountId],
  );

  const totals = useMemo(() => filteredRows.reduce(
    (a, r) => ({
      views: a.views + (r.view_count || 0),
      likes: a.likes + (r.like_count || 0),
      comments: a.comments + (r.comment_count || 0),
      shares: a.shares + (r.share_count || 0),
    }),
    { views: 0, likes: 0, comments: 0, shares: 0 }
  ), [filteredRows]);

  const avgViews = filteredRows.length ? Math.round(totals.views / filteredRows.length) : 0;
  const engagement = totals.likes + totals.comments + totals.shares;
  const engagementRate = totals.views ? (engagement / totals.views) * 100 : 0;

  // Views over time — aggregate by day.
  const timeline = useMemo(() => {
    const byDay = new Map();
    for (const r of filteredRows) {
      const d = parseDate(r.platform_created_at);
      if (!d) continue;
      const k = dayKey(d);
      const cur = byDay.get(k) || { key: k, date: d, views: 0 };
      cur.views += r.view_count || 0;
      byDay.set(k, cur);
    }
    return [...byDay.values()]
      .sort((a, b) => a.date - b.date)
      .map((x) => ({ label: shortDate(x.date), views: x.views }));
  }, [filteredRows]);

  // Top posts by views.
  const topPosts = useMemo(
    () => [...filteredRows]
      .sort((a, b) => (b.view_count || 0) - (a.view_count || 0))
      .slice(0, 8)
      .map((r, i) => ({ ...r, rank: i + 1, name: (r.title || platformMeta(r.platform).label).slice(0, 28) })),
    [filteredRows]
  );

  // Breakdown by pillar / format — over posts attributed to our system.
  const pillarData = useMemo(() => aggregateBy(filteredRows, "pillar", prettify), [filteredRows]);
  const formatData = useMemo(() => aggregateBy(filteredRows, "format_name", (f) => f || ""), [filteredRows]);

  const sortedRows = useMemo(() => {
    const copy = [...filteredRows];
    if (sortKey === "likes") copy.sort((a, b) => (b.like_count || 0) - (a.like_count || 0));
    else if (sortKey === "date") copy.sort((a, b) => (parseDate(b.platform_created_at)?.getTime() || 0) - (parseDate(a.platform_created_at)?.getTime() || 0));
    else copy.sort((a, b) => (b.view_count || 0) - (a.view_count || 0));
    return copy;
  }, [filteredRows, sortKey]);

  return (
    <div className="max-w-6xl space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight">Analytics</h2>
            {updating && rows.length > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                <RefreshCw className="size-3 animate-spin" /> Updating…
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Live performance across your linked accounts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {accounts.length > 0 && (
            <AccountFilter accounts={accounts} value={accountId} onChange={setAccountId} />
          )}
          <Button variant="outline" size="sm" onClick={refresh} disabled={updating || loading}>
            <RefreshCw className={`size-3.5 ${updating ? "animate-spin" : ""}`} />
            {updating ? "Updating…" : "Refresh"}
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading || (updating && rows.length === 0) ? (
        <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
          <RefreshCw className="size-4 animate-spin" /> Loading analytics…
        </div>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/70 py-20 text-center">
          <BarChart2 className="mb-3 size-10 text-muted-foreground/40" />
          <p className="text-sm font-semibold">No analytics yet</p>
          <p className="mt-1 max-w-xs text-xs text-muted-foreground">
            Publish posts and link the accounts in the Accounts tab, then hit Refresh.
          </p>
        </div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard icon={Eye} label="Views" value={fmt(totals.views)} accent="text-sky-500" />
            <StatCard icon={Heart} label="Likes" value={fmt(totals.likes)} accent="text-rose-500" />
            <StatCard icon={MessageCircle} label="Comments" value={fmt(totals.comments)} accent="text-violet-500" />
            <StatCard icon={Share2} label="Shares" value={fmt(totals.shares)} accent="text-emerald-500" />
            <StatCard icon={TrendingUp} label="Engagement" value={`${engagementRate.toFixed(1)}%`} sub={`${fmt(filteredRows.length)} posts · ${fmt(avgViews)} avg views`} accent="text-amber-500" />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard title="Views over time">
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
                    <Tooltip content={<ChartTooltip suffix=" views" />} />
                    <Area type="monotone" dataKey="views" stroke="var(--primary)" strokeWidth={2} fill="url(#viewsFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart label="Not enough dated posts to chart a trend yet." />
              )}
            </ChartCard>

            <ChartCard title="Top posts by views">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={topPosts} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
                  <XAxis type="number" tickFormatter={compact} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
                  <Tooltip content={<ChartTooltip suffix=" views" />} cursor={{ fill: "var(--muted)", opacity: 0.4 }} />
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
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard title="Views by pillar">
                {pillarData.length ? <CategoryBars data={pillarData} /> : <EmptyChart label="No pillar-attributed posts yet." />}
              </ChartCard>
              <ChartCard title="Views by format">
                {formatData.length ? <CategoryBars data={formatData} /> : <EmptyChart label="No format-attributed posts yet." />}
              </ChartCard>
            </div>
          )}

          {/* Posts table */}
          <div className="overflow-hidden rounded-2xl border border-border">
            <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
              <h3 className="text-sm font-semibold">All posts <span className="text-muted-foreground tabular-nums">· {filteredRows.length}</span></h3>
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
                    {k}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Post</th>
                    <th className="px-3 py-2 text-left font-medium">Date</th>
                    <th className="px-3 py-2 text-right font-medium">Views</th>
                    <th className="px-3 py-2 text-right font-medium">Likes</th>
                    <th className="px-3 py-2 text-right font-medium">Comments</th>
                    <th className="px-3 py-2 text-right font-medium">Shares</th>
                    <th className="px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((r) => {
                    const meta = platformMeta(r.platform);
                    const d = parseDate(r.platform_created_at);
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
                                <span className="text-[10px] uppercase tracking-wide">{meta.label}</span>
                                {r.published_via === "duct" && (
                                  <span className="rounded-full bg-primary/10 px-1.5 py-px text-[9px] font-semibold text-primary">via Duct</span>
                                )}
                                {r.pillar && (
                                  <span className="rounded-full bg-muted px-1.5 py-px text-[9px] font-medium text-muted-foreground">{prettify(r.pillar)}</span>
                                )}
                              </p>
                              <p className="line-clamp-2 text-xs text-foreground">{r.title || <span className="italic text-muted-foreground">No caption</span>}</p>
                            </div>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">{shortDate(d)}</td>
                        <td className="px-3 py-2 text-right font-medium tabular-nums">{fmt(r.view_count)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{fmt(r.like_count)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{fmt(r.comment_count)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{fmt(r.share_count)}</td>
                        <td className="px-2 py-2 text-right">
                          {safeHref(r.share_url) && (
                            <a href={safeHref(r.share_url)} target="_blank" rel="noopener noreferrer" className="inline-flex text-muted-foreground hover:text-foreground" title="Open post">
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

/**
 * Account filter — a dropdown that scopes the whole view to one social account.
 * Each option renders richly: profile avatar (badged with the platform glyph),
 * the @handle, and the platform name + post count.
 */
function AccountFilter({ accounts, value, onChange }) {
  const selected = accounts.find((a) => a.id === value) || null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="max-w-[200px]">
          {selected ? (
            <>
              <AccountAvatar account={selected} size="xs" />
              <span className="truncate">@{selected.username || selected.id}</span>
            </>
          ) : (
            <>
              <Users className="size-3.5" />
              All accounts
            </>
          )}
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-64">
        <DropdownMenuLabel>Filter by account</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => onChange(null)} className="gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Users className="size-4" />
          </span>
          <span className="min-w-0 flex-1 text-sm font-medium">All accounts</span>
          {value == null && <Check className="size-4 shrink-0 text-primary" />}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {accounts.map((a) => (
          <DropdownMenuItem key={a.id} onSelect={() => onChange(a.id)} className="gap-2.5">
            <AccountAvatar account={a} size="sm" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">@{a.username || a.id}</span>
              <span className="block truncate text-[11px] text-muted-foreground">
                {platformMeta(a.platform).label} · {a.count} {a.count === 1 ? "post" : "posts"}
              </span>
            </span>
            {value === a.id && <Check className="size-4 shrink-0 text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
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
      {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

function prettify(s) {
  return String(s || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
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
        <Tooltip content={<ChartTooltip suffix=" views" />} cursor={{ fill: "var(--muted)", opacity: 0.4 }} />
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

function ChartTooltip({ active, payload, label, suffix = "" }) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  const name = p.payload?.title || p.payload?.name || label;
  return (
    <div className="rounded-lg border border-border bg-popover px-2.5 py-1.5 text-xs shadow-md">
      {name && <p className="mb-0.5 max-w-[220px] truncate font-medium">{name}</p>}
      <p className="tabular-nums text-muted-foreground">{fmt(p.value)}{suffix}</p>
    </div>
  );
}
