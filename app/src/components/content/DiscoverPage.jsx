"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AtSign,
  BadgeCheck,
  Bookmark,
  Check,
  ChevronDown,
  ExternalLink,
  Hash,
  Heart,
  Images,
  Loader2,
  MessageCircle,
  Music2,
  Pin,
  Play,
  Plus,
  RotateCcw,
  Search,
  Share2,
  Sparkles,
  TrendingUp,
  Type,
  X,
} from "lucide-react";

import {
  getBrandContext,
  getDiscoverWatchlist,
  putDiscoverWatchlist,
  saveDiscoveredReference,
} from "../../lib/contentApi";
import { useScraperRun } from "../../hooks/useScraperRun";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const FULL_ACTOR  = "clockworks/tiktok-scraper";
const TREND_ACTOR = "clockworks/free-tiktok-scraper";

// A "mode" is a research lens. Hashtag / keyword / profile all run the full
// scraper with different inputs; the trend feed uses the lighter free actor.
const MODES = [
  { id: "hashtag", label: "By hashtag", icon: Hash,       actorId: FULL_ACTOR,  hint: "Top + recent posts for hashtags. Best for what's already working in the niche." },
  { id: "keyword", label: "By keyword", icon: Type,       actorId: FULL_ACTOR,  hint: "Search posts by phrase — catches trends that aren't a clean hashtag yet." },
  { id: "profile", label: "By profile", icon: AtSign,     actorId: FULL_ACTOR,  hint: "Scrape a competitor's posts + audience comments. Pin handles to your watchlist." },
  { id: "trend",   label: "Trend feed", icon: TrendingUp, actorId: TREND_ACTOR, hint: "Trending posts in a region — good for sound + format discovery." },
];

const SORTS = [
  { id: "engagement", label: "Best engagement", key: (p) => engagement(p) },
  { id: "plays",      label: "Top plays",       key: (p) => p.play_count || 0 },
  { id: "saves",      label: "Most saved",      key: (p) => p.collect_count || 0 },
  { id: "recent",     label: "Most recent",     key: (p) => new Date(p.create_time_iso || 0).getTime() },
];

// Recency windows. Hashtag/profile use `oldestPostDateUnified` (relative days);
// keyword search uses the actor's `videoSearchDateFilter` enum. Without this the
// scraper returns all-time top posts, so "what's working" surfaces years-old virals.
const DATE_WINDOWS = [
  { id: "1",  label: "24 hours", filter: "PAST_24_HOURS" },
  { id: "7",  label: "7 days",   filter: "PAST_WEEK" },
  { id: "30", label: "30 days",  filter: "PAST_MONTH" },
  { id: "90", label: "90 days",  filter: "LAST_3_MONTHS" },
];

// Server-side quality floor (min hearts) — drops the low-engagement long tail
// before it reaches us, which also trims Apify result cost.
const MIN_DIGGS = 1000;

const RUNNING = new Set(["running", "polling", "fetching"]);

function fmtNum(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(v % 1_000_000 ? 1 : 0)}M`;
  if (v >= 1_000)     return `${(v / 1_000).toFixed(v % 1_000 ? 1 : 0)}k`;
  return String(v);
}

function engagement(p) {
  const plays = p.play_count || 0;
  if (!plays) return 0;
  return ((p.digg_count || 0) + (p.comment_count || 0) + (p.share_count || 0) + (p.collect_count || 0)) / plays;
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function slugifyTag(s) {
  return String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function normHandle(s) {
  return String(s || "").trim().replace(/^@+/, "").toLowerCase();
}

export default function DiscoverPage({ projectId }) {
  const [mode, setMode]             = useState("hashtag");
  const [tags, setTags]             = useState([]);     // hashtag mode
  const [keywords, setKeywords]     = useState([]);     // keyword mode
  const [handle, setHandle]         = useState("");     // profile mode input
  const [watchlist, setWatchlist]   = useState([]);     // pinned competitor handles
  const [region, setRegion]         = useState("US");   // trend mode
  const [dateWindow, setDateWindow] = useState("30");
  const [profileSort, setProfileSort] = useState("popular");
  const [sort, setSort]             = useState("engagement");
  const [busy, setBusy]             = useState({}); // post.id → "saving" | "saved"

  const modeDef = useMemo(() => MODES.find((m) => m.id === mode) || MODES[0], [mode]);
  const actorId = modeDef.actorId;
  const { phase, results, error, elapsed, runId, datasetId, startRun, reset } = useScraperRun();
  const isRunning = RUNNING.has(phase);

  // Anchor discovery from Brand: pre-seed hashtag/keyword inputs from the
  // brand's content pillars, and load the saved competitor watchlist.
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    (async () => {
      const [brand, wl] = await Promise.all([
        getBrandContext(projectId).catch(() => null),
        getDiscoverWatchlist(projectId).catch(() => null),
      ]);
      if (!alive) return;
      if (Array.isArray(wl?.handles)) setWatchlist(wl.handles);
      const pillars = brand?.content_pillars?.items || [];
      if (pillars.length) {
        const tagSeeds = pillars.map((p) => slugifyTag(p.name)).filter(Boolean).slice(0, 4);
        const kwSeeds  = pillars.map((p) => (p.name || "").trim()).filter(Boolean).slice(0, 3);
        setTags((prev) => (prev.length ? prev : tagSeeds));
        setKeywords((prev) => (prev.length ? prev : kwSeeds));
      }
    })();
    return () => { alive = false; };
  }, [projectId]);

  const buildInput = useCallback(() => {
    const dw = DATE_WINDOWS.find((w) => w.id === dateWindow) || DATE_WINDOWS[2];
    if (mode === "hashtag") {
      return {
        hashtags: tags,
        resultsPerPage: 30,
        oldestPostDateUnified: dw.id,
        leastDiggs: MIN_DIGGS,
        shouldDownloadVideos: false,
        shouldDownloadCovers: false,
        shouldDownloadSubtitles: false,
      };
    }
    if (mode === "keyword") {
      return {
        searchQueries: keywords,
        searchSection: "/video",
        resultsPerPage: 30,
        videoSearchSorting: "MOST_LIKED",
        videoSearchDateFilter: dw.filter,
        leastDiggs: MIN_DIGGS,
      };
    }
    if (mode === "profile") {
      return {
        profiles: [normHandle(handle)].filter(Boolean),
        resultsPerPage: 30,
        profileScrapeSections: ["videos"],
        profileSorting: profileSort,
        excludePinnedPosts: true,
        oldestPostDateUnified: dw.id,
        commentsPerPost: 20, // audience questions/objections → hook fodder
      };
    }
    return { type: "TREND", region, resultsPerPage: 30 };
  }, [mode, tags, keywords, handle, profileSort, region, dateWindow]);

  function handleRun() {
    if (!projectId || !canRun) return;
    startRun({ projectId, actorId, inputPayload: buildInput() });
  }

  async function handleSave(post) {
    setBusy((b) => ({ ...b, [post.id]: "saving" }));
    try {
      await saveDiscoveredReference({ projectId, actorId, runId, datasetId, request: buildInput(), post });
      setBusy((b) => ({ ...b, [post.id]: "saved" }));
    } catch (e) {
      setBusy((b) => ({ ...b, [post.id]: "" }));
      console.error("save reference failed", e);
    }
  }

  async function pinHandle(h) {
    const norm = normHandle(h);
    if (!norm || watchlist.includes(norm)) return;
    const next = [...watchlist, norm];
    setWatchlist(next);
    try { await putDiscoverWatchlist(projectId, next); }
    catch (e) { setWatchlist(watchlist); console.error("pin failed", e); }
  }

  async function unpinHandle(h) {
    const next = watchlist.filter((x) => x !== h);
    setWatchlist(next);
    try { await putDiscoverWatchlist(projectId, next); }
    catch (e) { setWatchlist(watchlist); console.error("unpin failed", e); }
  }

  const sorted = useMemo(() => {
    const keyFn = (SORTS.find((s) => s.id === sort) || SORTS[0]).key;
    return [...results].sort((a, b) => keyFn(b) - keyFn(a));
  }, [results, sort]);

  // Profile header derived from the scraped author (profile mode only).
  const profileHead = useMemo(() => {
    if (mode !== "profile" || !results.length) return null;
    return results.find((p) => p.author_meta?.name)?.author_meta || null;
  }, [mode, results]);

  const canRun = !!projectId && !isRunning && (
    (mode === "hashtag" && tags.length > 0) ||
    (mode === "keyword" && keywords.length > 0) ||
    (mode === "profile" && !!normHandle(handle)) ||
    mode === "trend"
  );

  const handleNorm = normHandle(handle);

  return (
    <div className="space-y-5">
      <header>
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <Sparkles className="h-4 w-4 text-primary" /> Discover what&apos;s working
        </h2>
        <p className="mt-0.5 max-w-prose text-xs text-muted-foreground">
          Scrape real TikTok posts in your niche. Save the best ones — the planner&apos;s
          trend scout cites them when building your plan, so it&apos;s grounded in what already gets reach.
        </p>
      </header>

      {/* Control panel */}
      <section className="rounded-xl border border-border/70 bg-card p-4">
        <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
          <div className="space-y-3">
            {/* mode segmented control */}
            <Segmented
              options={MODES.map((m) => ({ id: m.id, label: m.label, icon: m.icon }))}
              value={mode}
              onChange={setMode}
            />

            {mode === "hashtag" && (
              <Labeled label="Hashtags">
                <ChipInput items={tags} setItems={setTags} prefix="#" placeholder="faceshape, colorseason…" normalize={(v) => slugifyTag(v)} />
              </Labeled>
            )}

            {mode === "keyword" && (
              <Labeled label="Keywords / phrases">
                <ChipInput items={keywords} setItems={setKeywords} placeholder="color analysis, face shape guide…" normalize={(v) => v.trim()} />
              </Labeled>
            )}

            {mode === "profile" && (
              <div className="space-y-2">
                <Labeled label="Competitor handle">
                  <div className="flex items-center gap-2">
                    <div className="flex flex-1 items-center rounded-md border border-border/70 bg-background px-2">
                      <span className="text-[11px] text-muted-foreground">@</span>
                      <input
                        value={handle}
                        onChange={(e) => setHandle(e.target.value.replace(/^@+/, ""))}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleRun(); } }}
                        placeholder="competitorhandle"
                        className="min-w-0 flex-1 bg-transparent px-1 py-1.5 text-[11px] outline-none placeholder:text-muted-foreground/60"
                      />
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => pinHandle(handle)}
                      disabled={!handleNorm || watchlist.includes(handleNorm)}
                      title="Add to watchlist"
                    >
                      <Pin className="h-3.5 w-3.5" /> Pin
                    </Button>
                  </div>
                </Labeled>

                {watchlist.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground/60">Watchlist</span>
                    {watchlist.map((h) => (
                      <span
                        key={h}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]",
                          handleNorm === h ? "border-primary/50 bg-primary/10 text-foreground" : "border-border bg-muted/50 text-muted-foreground",
                        )}
                      >
                        <button type="button" onClick={() => setHandle(h)} className="font-medium">@{h}</button>
                        <button type="button" onClick={() => unpinHandle(h)} className="text-muted-foreground hover:text-destructive">
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                <Labeled label="Sort">
                  <Segmented
                    options={[{ id: "popular", label: "Popular" }, { id: "latest", label: "Latest" }]}
                    value={profileSort}
                    onChange={setProfileSort}
                  />
                </Labeled>
              </div>
            )}

            {mode === "trend" && (
              <Labeled label="Region">
                <Input
                  value={region}
                  onChange={(e) => setRegion(e.target.value.toUpperCase())}
                  maxLength={2}
                  className="mt-1 h-9 w-20 font-mono"
                />
              </Labeled>
            )}

            {mode !== "trend" && (
              <Labeled label="Posted within">
                <Segmented
                  options={DATE_WINDOWS.map((w) => ({ id: w.id, label: w.label }))}
                  value={dateWindow}
                  onChange={setDateWindow}
                />
              </Labeled>
            )}

            <p className="text-[11px] text-muted-foreground/70">{modeDef.hint}</p>
          </div>

          <div className="flex items-center gap-2">
            {phase !== "idle" && (
              <Button variant="ghost" size="sm" onClick={reset} disabled={isRunning} title="Reset">
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}
            <Button onClick={handleRun} disabled={!canRun}>
              {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              {isRunning ? `${phase}… ${elapsed}s` : "Start discovery"}
            </Button>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Profile header (competitor mode) */}
      {profileHead && (
        <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-card p-3">
          {profileHead.avatar ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={profileHead.avatar} alt="" className="h-12 w-12 shrink-0 rounded-full object-cover" />
          ) : (
            <div className="h-12 w-12 shrink-0 rounded-full bg-muted" />
          )}
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1 text-sm font-semibold">
              @{profileHead.name}
              {profileHead.verified && <BadgeCheck className="h-3.5 w-3.5 text-sky-500" />}
            </p>
            <p className="text-[11px] text-muted-foreground">
              {fmtNum(profileHead.fans)} fans · {fmtNum(profileHead.heart)} likes
            </p>
            {profileHead.signature && (
              <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground/80">{profileHead.signature}</p>
            )}
          </div>
          {!watchlist.includes(normHandle(profileHead.name)) && (
            <Button variant="outline" size="sm" onClick={() => pinHandle(profileHead.name)}>
              <Pin className="h-3.5 w-3.5" /> Pin
            </Button>
          )}
        </div>
      )}

      {/* Running */}
      {isRunning && (
        <div className="space-y-3">
          <div className="flex items-center justify-center gap-2 rounded-lg border border-border/60 bg-muted/30 px-3 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Scraping on Apify ({elapsed}s) — polling every 3s, results appear as soon as the actor finishes.
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="aspect-[4/5] animate-pulse rounded-xl border border-border/50 bg-muted/30" />
            ))}
          </div>
        </div>
      )}

      {/* Empty after done */}
      {phase === "done" && results.length === 0 && (
        <div className="rounded-xl border border-dashed border-border/60 px-3 py-10 text-center text-sm text-muted-foreground">
          No results returned. Try a different {mode === "profile" ? "handle" : "search"} or a wider window.
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground tabular-nums">{results.length}</span> posts found
            </p>
            <div className="flex items-center gap-1.5">
              {SORTS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSort(s.id)}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                    sort === s.id ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {sorted.map((p) => (
              <ResultCard key={p.id} post={p} busy={busy[p.id]} onSave={() => handleSave(p)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Labeled({ label, children }) {
  return (
    <div>
      <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function Segmented({ options, value, onChange }) {
  return (
    <div className="inline-flex rounded-lg border border-border/70 bg-muted/40 p-0.5">
      {options.map((o) => {
        const Icon = o.icon;
        const active = value === o.id;
        return (
          <button
            key={o.id}
            type="button"
            onClick={() => onChange(o.id)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
              active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {Icon ? <Icon className="h-3.5 w-3.5" /> : null} {o.label}
          </button>
        );
      })}
    </div>
  );
}

function ChipInput({ items, setItems, prefix = "", placeholder, normalize }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = normalize ? normalize(draft) : draft.trim();
    if (v && !items.includes(v)) setItems([...items, v]);
    setDraft("");
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-border/70 bg-background p-2">
      {items.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-[11px] font-medium">
          {prefix}{t}
          <button type="button" onClick={() => setItems(items.filter((x) => x !== t))} className="text-muted-foreground hover:text-destructive">
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
          if (e.key === "Backspace" && !draft && items.length) setItems(items.slice(0, -1));
        }}
        onBlur={add}
        placeholder={items.length ? "" : placeholder}
        className="min-w-[120px] flex-1 bg-transparent px-1 py-0.5 text-[11px] outline-none placeholder:text-muted-foreground/60"
      />
    </div>
  );
}

function ResultCard({ post, busy, onSave }) {
  const author = post.author_meta?.name;
  const verified = post.author_meta?.verified;
  const music  = post.music_meta?.music_name;
  const cover  = (post.slideshow_image_links || [])[0]
    || post.video_meta?.cover_url
    || post.video_meta?.original_cover_url
    || "";
  const tags   = (post.hashtags || []).slice(0, 3);
  const eng    = engagement(post);
  const saved  = busy === "saved";

  return (
    <article className="group flex flex-col overflow-hidden rounded-xl border border-border/70 bg-card transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
      {/* Cover */}
      <a
        href={post.web_video_url}
        target="_blank"
        rel="noreferrer"
        className="relative block aspect-[4/5] w-full overflow-hidden bg-gradient-to-br from-muted/60 to-muted/20"
      >
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={cover} alt="" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" loading="lazy" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground/50">
            <Play className="h-7 w-7" />
          </div>
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/70 to-transparent" />

        {/* play count, bottom-left */}
        <span className="absolute bottom-2 left-2 inline-flex items-center gap-1 text-xs font-semibold text-white drop-shadow">
          <Play className="h-3.5 w-3.5 fill-white" /> {fmtNum(post.play_count)}
        </span>

        {/* badges top-right */}
        <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
          {post.is_slideshow && (
            <span className="inline-flex items-center gap-1 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
              <Images className="h-3 w-3" /> Slides
            </span>
          )}
          {eng > 0 && (
            <span className="rounded-full bg-primary/90 px-2 py-0.5 text-[10px] font-semibold text-primary-foreground backdrop-blur-sm">
              {(eng * 100).toFixed(1)}% eng
            </span>
          )}
        </div>
        <span className="absolute right-2 bottom-2 opacity-0 transition-opacity group-hover:opacity-100">
          <ExternalLink className="h-3.5 w-3.5 text-white drop-shadow" />
        </span>
      </a>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-2 p-3">
        <p className="line-clamp-2 text-xs leading-snug">{post.text || <span className="text-muted-foreground italic">(no caption)</span>}</p>

        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {tags.map((t) => (
              <Badge key={t} variant="secondary" className="px-1.5 py-0 text-[10px] font-normal">#{t}</Badge>
            ))}
          </div>
        )}

        {/* metrics */}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted-foreground">
          <Metric icon={Heart}         value={post.digg_count} />
          <Metric icon={MessageCircle} value={post.comment_count} />
          <Metric icon={Share2}        value={post.share_count} />
          <Metric icon={Bookmark}      value={post.collect_count} />
        </div>

        {/* author + music */}
        <div className="mt-auto space-y-1 pt-1">
          {author && (
            <p className="flex items-center gap-1 truncate text-[11px] text-muted-foreground">
              <span className="truncate font-medium text-foreground/80">@{author}</span>
              {verified && <BadgeCheck className="h-3 w-3 shrink-0 text-sky-500" />}
              {post.author_meta?.fans ? <span className="shrink-0">· {fmtNum(post.author_meta.fans)} fans</span> : null}
            </p>
          )}
          {music && (
            <p className="flex items-center gap-1 truncate text-[11px] text-muted-foreground">
              <Music2 className="h-3 w-3 shrink-0" /> <span className="truncate">{music}</span>
            </p>
          )}
        </div>

        {/* comments (profile mode) */}
        {post.comments?.length > 0 && <CommentsBlock comments={post.comments} />}

        {/* footer */}
        <div className="flex items-center justify-between gap-2 border-t border-border/40 pt-2">
          <span className="text-[10px] text-muted-foreground">{fmtDate(post.create_time_iso)}</span>
          <button
            type="button"
            onClick={onSave}
            disabled={busy === "saving" || saved}
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors",
              saved
                ? "bg-green-500/15 text-green-600 dark:text-green-400"
                : "border border-border hover:bg-muted disabled:opacity-50",
            )}
          >
            {saved ? <><Check className="h-3 w-3" /> Saved</> : busy === "saving" ? "Saving…" : <><Plus className="h-3 w-3" /> Save</>}
          </button>
        </div>
      </div>
    </article>
  );
}

function CommentsBlock({ comments }) {
  const [open, setOpen] = useState(false);
  const top = comments.slice(0, 5);
  return (
    <div className="border-t border-border/40 pt-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground hover:text-foreground"
      >
        <MessageCircle className="h-3 w-3" /> {comments.length} audience comments
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ul className="mt-1 space-y-1">
          {top.map((c, i) => (
            <li key={i} className="line-clamp-2 text-[10px] leading-snug text-muted-foreground">
              {c.author ? <span className="text-foreground/70">@{c.author} </span> : null}{c.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Metric({ icon: Icon, value }) {
  return (
    <span className="inline-flex items-center gap-1 tabular-nums">
      <Icon className="h-3.5 w-3.5" /> {fmtNum(value)}
    </span>
  );
}
