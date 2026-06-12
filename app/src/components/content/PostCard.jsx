"use client";

import Link from "next/link";
import {
  Bookmark,
  Calendar,
  Eye,
  Heart,
  ImageOff,
  MessageCircle,
  Share2,
} from "lucide-react";
import { mediaUrl } from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_STYLE = {
  posted:    "bg-green-500/90 text-white",
  scheduled: "bg-sky-500/90 text-white",
  draft:     "bg-amber-500/90 text-white",
  discarded: "bg-rose-500/90 text-white",
  pending:   "bg-zinc-500/90 text-white",
};

function fmtNum(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(v % 1_000_000 ? 1 : 0)}M`;
  if (v >= 1_000)     return `${(v / 1_000).toFixed(v % 1_000 ? 1 : 0)}k`;
  return String(v);
}

function pick(perf, ...keys) {
  for (const k of keys) {
    const v = perf?.[k];
    if (typeof v === "number") return v;
  }
  return null;
}

function metricsOf(perf = {}) {
  return {
    views:    pick(perf, "view_count", "play_count", "views"),
    likes:    pick(perf, "like_count", "digg_count", "likes"),
    comments: pick(perf, "comment_count", "comments"),
    shares:   pick(perf, "share_count", "shares"),
    saves:    pick(perf, "save_count", "collect_count", "saves"),
  };
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function titleCase(s) {
  return (s || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).trim();
}

// ---------------------------------------------------------------------------
// Post card
// ---------------------------------------------------------------------------

export default function PostCard({ post }) {
  const thumb = mediaUrl(post.thumbnail_url);
  const platforms = Array.isArray(post.platforms) ? post.platforms : [];
  const m = metricsOf(post.perf);
  const hasMetrics = Object.values(m).some((v) => v != null);
  const status = post.status || "pending";
  const formatLabel = post.format_name || post.format_slug || "";
  const published = post.posted_at;

  return (
    <Link
      href={`/content/posts/${post.id}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-border/70 bg-card transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
    >
      {/* Thumbnail */}
      <div className="relative aspect-[4/5] w-full overflow-hidden bg-gradient-to-br from-muted/60 to-muted/20">
        {thumb ? (
          <img
            src={thumb}
            alt={post.topic || "post preview"}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground/60">
            <ImageOff className="h-7 w-7" />
            <span className="text-[11px]">No preview yet</span>
          </div>
        )}

        {/* top gradient for legibility */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-black/40 to-transparent" />

        {/* status pill */}
        <span className={`absolute left-2.5 top-2.5 rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize shadow-sm backdrop-blur-sm ${STATUS_STYLE[status] || STATUS_STYLE.pending}`}>
          {status}
        </span>

        {/* day badge */}
        {post.day_index != null && (
          <span className="absolute right-2.5 top-2.5 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
            Day {post.day_index}
          </span>
        )}

        {/* platform glyphs */}
        {platforms.length > 0 && (
          <div className="absolute bottom-2.5 left-2.5 flex items-center gap-1.5">
            {platforms.slice(0, 5).map((p) => (
              <span
                key={p}
                title={platformMeta(p).label}
                className="flex h-6 w-6 items-center justify-center rounded-full bg-white/95 text-black shadow-sm"
              >
                <PlatformGlyph platform={p} className="size-3.5" title={platformMeta(p).label} />
              </span>
            ))}
          </div>
        )}

        {post.published_via === "duct" && (
          <span className="absolute bottom-2.5 right-2.5 rounded-full bg-primary/90 px-2 py-0.5 text-[9px] font-semibold text-primary-foreground shadow-sm">
            via Duct
          </span>
        )}
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-2.5 p-3.5">
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug group-hover:text-primary">
          {post.topic || post.post_dir_slug || "Untitled post"}
        </h3>

        <div className="flex flex-wrap items-center gap-1.5">
          {post.pillar && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
              {titleCase(post.pillar)}
            </span>
          )}
          {formatLabel && (
            <span className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] text-muted-foreground">
              {formatLabel}
            </span>
          )}
        </div>

        {/* Metrics */}
        {hasMetrics ? (
          <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-[11px] text-muted-foreground">
            <Metric icon={Eye}           value={m.views} />
            <Metric icon={Heart}         value={m.likes} />
            <Metric icon={MessageCircle} value={m.comments} />
            <Metric icon={Share2}        value={m.shares} />
            <Metric icon={Bookmark}      value={m.saves} />
          </div>
        ) : (
          <p className="mt-auto pt-1 text-[11px] text-muted-foreground/70">No metrics yet</p>
        )}

        {/* Footer */}
        <div className="flex items-center gap-1.5 border-t border-border/40 pt-2 text-[11px] text-muted-foreground">
          <Calendar className="h-3 w-3" />
          {published ? <span>Published {fmtDate(published)}</span> : <span className="italic">Not published</span>}
        </div>
      </div>
    </Link>
  );
}

function Metric({ icon: Icon, value }) {
  if (value == null) return null;
  return (
    <span className="inline-flex items-center gap-1 tabular-nums">
      <Icon className="h-3.5 w-3.5" />
      {fmtNum(value)}
    </span>
  );
}
