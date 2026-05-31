"use client";

import { useCallback, useMemo, useState } from "react";

import { saveDiscoveredReference } from "../../lib/contentApi";
import { useScraperRun } from "../../hooks/useScraperRun";

const ACTORS = [
  {
    id:        "clockworks/tiktok-scraper",
    label:     "TikTok posts by hashtag",
    hint:      "Top + recent posts for hashtags you care about. Best for finding what's actually working in the niche.",
    defaultInput: () => ({
      hashtags: ["faceshape", "colorseason"],
      resultsPerPage: 30,
      shouldDownloadVideos:    false,
      shouldDownloadCovers:    false,
      shouldDownloadSubtitles: false,
    }),
  },
  {
    id:        "clockworks/free-tiktok-scraper",
    label:     "TikTok trend feed",
    hint:      "Trending posts in a region — good for sound + format discovery.",
    defaultInput: () => ({
      type:    "TREND",
      region:  "US",
      resultsPerPage: 30,
    }),
  },
];


export default function DiscoverPage({ projectId }) {
  const [actorId,     setActorId]     = useState(ACTORS[0].id);
  const [hashtagsRaw, setHashtagsRaw] = useState("faceshape, colorseason");
  const [region,      setRegion]      = useState("US");
  const [busy,        setBusy]        = useState({});  // post.id → "saving" | "saved"

  const actor = useMemo(() => ACTORS.find(a => a.id === actorId), [actorId]);

  const { phase, results, error, elapsed, runId, datasetId, startRun, reset } = useScraperRun();

  const buildInput = useCallback(() => {
    if (actorId === "clockworks/tiktok-scraper") {
      const hashtags = hashtagsRaw
        .split(/[,\s]+/)
        .map(t => t.trim().replace(/^#/, ""))
        .filter(Boolean);
      return {
        hashtags,
        resultsPerPage: 30,
        shouldDownloadVideos:    false,
        shouldDownloadCovers:    false,
        shouldDownloadSubtitles: false,
      };
    }
    return { type: "TREND", region, resultsPerPage: 30 };
  }, [actorId, hashtagsRaw, region]);

  function handleRun() {
    if (!projectId) return;
    startRun({ projectId, actorId, inputPayload: buildInput() });
  }

  async function handleSave(post) {
    setBusy(b => ({ ...b, [post.id]: "saving" }));
    try {
      await saveDiscoveredReference({
        projectId,
        actorId,
        runId,
        datasetId,
        request: buildInput(),
        post,
      });
      setBusy(b => ({ ...b, [post.id]: "saved" }));
    } catch (e) {
      setBusy(b => ({ ...b, [post.id]: "" }));
      console.error("save reference failed", e);
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-base font-semibold">Discover what's working</h2>
          <p className="text-xs text-muted-foreground max-w-prose mt-0.5">
            Scrape real TikTok posts in your niche. Save the best ones — the
            research sub-agent cites them when proposing topics for the next
            plan, so your posts are grounded in what already gets reach.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {(phase !== "idle") && (
            <button
              type="button"
              onClick={reset}
              className="text-muted-foreground hover:text-foreground"
            >
              reset
            </button>
          )}
          <button
            type="button"
            onClick={handleRun}
            disabled={phase === "running" || phase === "polling" || phase === "fetching" || !projectId}
            className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
          >
            {(phase === "running" || phase === "polling" || phase === "fetching")
              ? `${phase}… ${elapsed}s`
              : "Start discovery"}
          </button>
        </div>
      </header>

      <section className="rounded-lg border border-border bg-background p-3 space-y-2 text-xs">
        <div className="flex items-center gap-2">
          <label className="text-muted-foreground">Source</label>
          <select
            value={actorId}
            onChange={(e) => setActorId(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {ACTORS.map(a => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
        </div>
        <p className="text-[10px] text-muted-foreground/70">{actor?.hint}</p>

        {actorId === "clockworks/tiktok-scraper" ? (
          <div className="flex items-center gap-2">
            <label className="text-muted-foreground">Hashtags</label>
            <input
              value={hashtagsRaw}
              onChange={(e) => setHashtagsRaw(e.target.value)}
              placeholder="faceshape, colorseason"
              className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <label className="text-muted-foreground">Region</label>
            <input
              value={region}
              onChange={(e) => setRegion(e.target.value.toUpperCase())}
              maxLength={2}
              className="w-16 rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        )}

        {(runId || datasetId) && (
          <p className="text-[10px] text-muted-foreground/60">
            {runId && <>run={runId.slice(0, 12)} · </>}
            {datasetId && <>dataset={datasetId.slice(0, 12)}</>}
          </p>
        )}
      </section>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {(phase === "running" || phase === "polling" || phase === "fetching") && (
        <div className="rounded-md border border-border bg-muted/30 px-3 py-6 text-xs text-muted-foreground text-center">
          Scraping is running on Apify ({elapsed}s). Polling every 3s — results appear as soon as the actor finishes.
        </div>
      )}

      {phase === "done" && results.length === 0 && (
        <div className="rounded-md border border-border bg-muted/30 px-3 py-4 text-xs text-muted-foreground text-center">
          No results returned. Try different hashtags or a wider niche.
        </div>
      )}

      {results.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {results.map(p => (
            <ResultCard
              key={p.id}
              post={p}
              busy={busy[p.id]}
              onSave={() => handleSave(p)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ResultCard({ post, busy, onSave }) {
  const author = post.author_meta?.name || "—";
  const music  = post.music_meta?.music_name;
  const cover  = (post.slideshow_image_links || [])[0];
  const fmt = (n) => (n == null ? "—" : n.toLocaleString());

  return (
    <article className="rounded-lg border border-border bg-background overflow-hidden flex flex-col">
      {cover && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={cover} alt="" className="w-full h-48 object-cover" loading="lazy" />
      )}
      <div className="p-3 space-y-2 flex-1 flex flex-col">
        <p className="text-xs line-clamp-3">{post.text || "(no caption)"}</p>
        <div className="grid grid-cols-3 gap-1 text-[10px] text-muted-foreground">
          <span title="plays">▶ {fmt(post.play_count)}</span>
          <span title="likes">♥ {fmt(post.digg_count)}</span>
          <span title="saves">⊕ {fmt(post.collect_count)}</span>
          <span title="comments">💬 {fmt(post.comment_count)}</span>
          <span title="shares">↗ {fmt(post.share_count)}</span>
          {post.is_slideshow && <span className="text-foreground">slideshow</span>}
        </div>
        <p className="text-[10px] text-muted-foreground truncate">
          @{author}{music ? ` · ♪ ${music}` : ""}
        </p>
        <div className="flex-1" />
        <div className="flex items-center justify-between gap-2 pt-1">
          <a
            href={post.web_video_url}
            target="_blank"
            rel="noreferrer"
            className="text-[10px] text-muted-foreground hover:text-foreground underline truncate"
          >
            open on TikTok
          </a>
          <button
            type="button"
            onClick={onSave}
            disabled={busy === "saving" || busy === "saved"}
            className="text-[10px] rounded-md border border-input px-2 py-0.5 hover:bg-muted disabled:opacity-50"
          >
            {busy === "saved" ? "saved ✓" : busy === "saving" ? "saving…" : "save as reference"}
          </button>
        </div>
      </div>
    </article>
  );
}
