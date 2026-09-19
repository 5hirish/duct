"use client";

import { useCallback, useMemo, useState } from "react";
import {
  BadgeCheck,
  Bookmark,
  Check,
  ExternalLink,
  Hash,
  Heart,
  Images,
  MessageCircle,
  Music2,
  Play,
  Plus,
  RotateCcw,
  Search,
  Share2,
  Sparkles,
  TrendingUp,
  X,
} from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Spinner } from "@/components/ui/spinner";
import { Skeleton } from "@/components/ui/skeleton";

import { saveDiscoveredReference } from "../../lib/contentApi";
import { useScraperRun } from "../../hooks/useScraperRun";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { compactNumber, formatDate } from "@/lib/format";

// Labels and hints are message descriptors (module-level tables): render
// them with `i18n._(...)`.
const ACTORS = [
  {
    id:    "clockworks/tiktok-scraper",
    label: msg`By hashtag`,
    icon:  Hash,
    hint:  msg`Top + recent posts for hashtags you care about. Best for finding what's actually working in the niche.`,
  },
  {
    id:    "clockworks/free-tiktok-scraper",
    label: msg`Trend feed`,
    icon:  TrendingUp,
    hint:  msg`Trending posts in a region — good for sound + format discovery.`,
  },
];

const SORTS = [
  { id: "plays",      label: msg`Top plays`,       key: (p) => p.play_count || 0 },
  { id: "saves",      label: msg`Most saved`,      key: (p) => p.collect_count || 0 },
  { id: "engagement", label: msg`Best engagement`, key: (p) => engagement(p) },
  { id: "recent",     label: msg`Most recent`,     key: (p) => new Date(p.create_time_iso || 0).getTime() },
];

const RUNNING = new Set(["running", "polling", "fetching"]);

function engagement(p) {
  const plays = p.play_count || 0;
  if (!plays) return 0;
  return ((p.digg_count || 0) + (p.comment_count || 0) + (p.share_count || 0) + (p.collect_count || 0)) / plays;
}

export default function DiscoverPage({ projectId }) {
  const { t, i18n } = useLingui();
  const [actorId, setActorId]       = useState(ACTORS[0].id);
  const [tags, setTags]             = useState(["faceshape", "colorseason"]);
  const [tagDraft, setTagDraft]     = useState("");
  const [region, setRegion]         = useState("US");
  const [sort, setSort]             = useState("plays");
  const [busy, setBusy]             = useState({}); // post.id → "saving" | "saved"

  const actor = useMemo(() => ACTORS.find((a) => a.id === actorId), [actorId]);
  const { phase, results, error, elapsed, runId, datasetId, startRun, reset } = useScraperRun();
  const isRunning = RUNNING.has(phase);

  const buildInput = useCallback(() => {
    if (actorId === "clockworks/tiktok-scraper") {
      return {
        hashtags: tags,
        resultsPerPage: 30,
        shouldDownloadVideos: false,
        shouldDownloadCovers: false,
        shouldDownloadSubtitles: false,
      };
    }
    return { type: "TREND", region, resultsPerPage: 30 };
  }, [actorId, tags, region]);

  function addTag() {
    const v = tagDraft.trim().replace(/^#/, "").toLowerCase();
    if (v && !tags.includes(v)) setTags([...tags, v]);
    setTagDraft("");
  }

  function handleRun() {
    if (!projectId) return;
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

  const resultCount = results.length;
  const sorted = useMemo(() => {
    const keyFn = (SORTS.find((s) => s.id === sort) || SORTS[0]).key;
    return [...results].sort((a, b) => keyFn(b) - keyFn(a));
  }, [results, sort]);

  const canRun = !!projectId && !isRunning &&
    (actorId !== "clockworks/tiktok-scraper" || tags.length > 0);

  // Apify identifiers for support, not copy: `run=` / `dataset=` are the field
  // names someone would paste into a ticket, so they stay as they are.
  const runIds = [
    runId && `run=${runId.slice(0, 12)}`,
    datasetId && `dataset=${datasetId.slice(0, 12)}`,
  ].filter(Boolean).join(" · ");

  return (
    <div className="space-y-5">
      <header>
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <Sparkles className="h-4 w-4 text-primary" /> <Trans>Discover what&apos;s working</Trans>
        </h2>
        <p className="mt-0.5 max-w-prose text-xs text-muted-foreground">
          <Trans>
            Scrape real posts in your niche. What you save, the research agent cites when it
            proposes topics.
          </Trans>
        </p>
      </header>

      {/* Control panel */}
      <section className="rounded-xl border border-border/70 bg-card p-4">
        <div className="grid gap-4 @2xl:grid-cols-[1fr_auto] @2xl:items-end">
          <div className="space-y-3">
            {/* source segmented control */}
            <div className="inline-flex rounded-lg border border-border/70 bg-muted/40 p-0.5">
              {ACTORS.map((a) => {
                const Icon = a.icon;
                const active = actorId === a.id;
                return (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => setActorId(a.id)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                      active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" /> {i18n._(a.label)}
                  </button>
                );
              })}
            </div>

            {actorId === "clockworks/tiktok-scraper" ? (
              <div>
                <label className="text-2xs font-medium text-muted-foreground"><Trans>Hashtags</Trans></label>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 rounded-md border border-border/70 bg-background p-2">
                  {tags.map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-2xs font-medium">
                      #{t}
                      <button type="button" onClick={() => setTags(tags.filter((x) => x !== t))} className="text-muted-foreground hover:text-destructive">
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  <input
                    value={tagDraft}
                    aria-label={t`Add a tag`}
                    onChange={(e) => setTagDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addTag(); }
                      if (e.key === "Backspace" && !tagDraft && tags.length) setTags(tags.slice(0, -1));
                    }}
                    onBlur={addTag}
                    placeholder={tags.length ? "" : t`faceshape, colorseason…`}
                    className="min-w-[120px] flex-1 rounded-sm bg-transparent px-1 py-0.5 text-2xs outline-none placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/30"
                  />
                </div>
              </div>
            ) : (
              <div>
                <label className="text-2xs font-medium text-muted-foreground"><Trans>Region</Trans></label>
                <Input
                  value={region}
                  onChange={(e) => setRegion(e.target.value.toUpperCase())}
                  maxLength={2}
                  className="mt-1 h-9 w-20 font-mono"
                />
              </div>
            )}
            <p className="text-2xs text-muted-foreground">{actor ? i18n._(actor.hint) : ""}</p>
          </div>

          <div className="flex items-center gap-2">
            {phase !== "idle" && (
              <Button variant="ghost" size="sm" onClick={reset} disabled={isRunning} title={t`Reset`}>
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}
            <Button onClick={handleRun} disabled={!canRun}>
              {isRunning ? <Spinner className="size-4" /> : <Search className="h-4 w-4" />}
              {isRunning ? t`${phase}… ${elapsed}s` : <Trans>Start discovery</Trans>}
            </Button>
          </div>
        </div>

        {runIds && (
          <p className="mt-2 font-mono text-2xs text-muted-foreground">{runIds}</p>
        )}
      </section>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Running */}
      {isRunning && (
        <div className="space-y-3">
          <div className="flex items-center justify-center gap-2 rounded-lg border border-border/60 bg-muted/30 px-3 py-3 text-xs text-muted-foreground">
            <Spinner className="size-3.5" />
            <Trans>Scraping on Apify ({elapsed}s) — polling every 3s, results appear as soon as the actor finishes.</Trans>
          </div>
          <div className="grid grid-cols-2 gap-4 @2xl:grid-cols-3 @4xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="aspect-[3/4] rounded-xl" />
            ))}
          </div>
        </div>
      )}

      {/* Empty after done */}
      {phase === "done" && results.length === 0 && (
        <div className="rounded-xl border border-dashed border-border/60 px-3 py-10 text-center text-sm text-muted-foreground">
          <Trans>No results returned. Try different hashtags or a wider niche.</Trans>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              <Trans>
                <span className="font-medium text-foreground tabular-nums">{resultCount}</span>{" "}
                <Plural value={resultCount} one="post found" other="posts found" />
              </Trans>
            </p>
            <div className="flex items-center gap-1.5">
              {SORTS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSort(s.id)}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-2xs font-medium transition-colors",
                    sort === s.id ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70",
                  )}
                >
                  {i18n._(s.label)}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 @2xl:grid-cols-3 @4xl:grid-cols-4">
            {sorted.map((p) => (
              <ResultCard key={p.id} post={p} busy={busy[p.id]} onSave={() => handleSave(p)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ResultCard({ post, busy, onSave }) {
  const { i18n } = useLingui();
  const author = post.author_meta?.name;
  const verified = post.author_meta?.verified;
  const music  = post.music_meta?.music_name;
  const cover  = (post.slideshow_image_links || [])[0];
  const tags   = (post.hashtags || []).slice(0, 3);
  const eng    = engagement(post);
  const engRate = (eng * 100).toFixed(1);
  const fans   = post.author_meta?.fans ? compactNumber(post.author_meta.fans) : "";
  const saved  = busy === "saved";

  return (
    <article className="group flex flex-col overflow-hidden rounded-xl border border-border/70 bg-card transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
      {/* Cover */}
      <a
        href={post.web_video_url}
        target="_blank"
        rel="noreferrer"
        className="relative block aspect-[3/4] w-full overflow-hidden bg-gradient-to-br from-muted/60 to-muted/20"
      >
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={cover} alt="" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" loading="lazy" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            <Play className="h-7 w-7" />
          </div>
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/70 to-transparent" />

        {/* play count, bottom-left */}
        <span className="absolute bottom-2 left-2 inline-flex items-center gap-1 text-xs font-semibold text-white drop-shadow">
          <Play className="h-3.5 w-3.5 fill-white" /> {compactNumber(post.play_count)}
        </span>

        {/* badges top-right */}
        <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
          {post.is_slideshow && (
            <span className="inline-flex items-center gap-1 rounded-full bg-black/55 px-2 py-0.5 text-2xs font-medium text-white backdrop-blur-sm">
              <Images className="h-3 w-3" /> <Trans>Slides</Trans>
            </span>
          )}
          {eng > 0 && (
            <span className="rounded-full bg-primary/90 px-2 py-0.5 text-2xs font-semibold text-primary-foreground backdrop-blur-sm">
              <Trans>{engRate}% eng</Trans>
            </span>
          )}
        </div>
        <span className="absolute right-2 bottom-2 opacity-0 transition-opacity group-hover:opacity-100">
          <ExternalLink className="h-3.5 w-3.5 text-white drop-shadow" />
        </span>
      </a>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-2 p-3">
        <p className="line-clamp-2 text-xs leading-snug">{post.text || <span className="text-muted-foreground italic"><Trans>(no caption)</Trans></span>}</p>

        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {tags.map((t) => (
              <Badge key={t} variant="secondary" className="px-1.5 py-0 text-2xs font-normal">#{t}</Badge>
            ))}
          </div>
        )}

        {/* metrics */}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-2xs text-muted-foreground">
          <Metric icon={Heart}         value={post.digg_count} />
          <Metric icon={MessageCircle} value={post.comment_count} />
          <Metric icon={Share2}        value={post.share_count} />
          <Metric icon={Bookmark}      value={post.collect_count} />
        </div>

        {/* author + music */}
        <div className="mt-auto space-y-1 pt-1">
          {author && (
            <p className="flex items-center gap-1 truncate text-2xs text-muted-foreground">
              <span className="truncate font-medium text-foreground/80">@{author}</span>
              {verified && <BadgeCheck className="h-3 w-3 shrink-0 text-info" />}
              {fans ? <span className="shrink-0"><Trans>· {fans} fans</Trans></span> : null}
            </p>
          )}
          {music && (
            <p className="flex items-center gap-1 truncate text-2xs text-muted-foreground">
              <Music2 className="h-3 w-3 shrink-0" /> <span className="truncate">{music}</span>
            </p>
          )}
        </div>

        {/* footer */}
        <div className="flex items-center justify-between gap-2 border-t border-border/40 pt-2">
          <span className="text-2xs text-muted-foreground">{formatDate(post.create_time_iso, { locale: i18n.locale })}</span>
          <button
            type="button"
            onClick={onSave}
            disabled={busy === "saving" || saved}
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-2 py-1 text-2xs font-medium transition-colors",
              saved
                ? "bg-success/15 text-success"
                : "border border-border hover:bg-muted disabled:opacity-50",
            )}
          >
            {saved ? <><Check className="h-3 w-3" /> <Trans>Saved</Trans></> : busy === "saving" ? <Trans>Saving…</Trans> : <><Plus className="h-3 w-3" /> <Trans>Save</Trans></>}
          </button>
        </div>
      </div>
    </article>
  );
}

function Metric({ icon: Icon, value }) {
  return (
    <span className="inline-flex items-center gap-1 tabular-nums">
      <Icon className="h-3.5 w-3.5" /> {compactNumber(value)}
    </span>
  );
}
