"use client";

import Link from "next/link";
import { Images, Video, Image as ImageIcon, Clock } from "lucide-react";
import { mediaUrl } from "@/lib/contentApi";
import { firstImageSrc } from "@/lib/contentStatus";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";

const TYPE_ICON = { slideshow: Images, video: Video, image: ImageIcon };

const KIND_BADGE = {
  published: "bg-green-500/15 text-green-600 dark:text-green-400",
  scheduled: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  proposed: "bg-muted text-muted-foreground",
};

function prettify(s) {
  return String(s || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Compact post card shared by the Kanban lanes and the Week calendar column.
 *
 * Props:
 *   - day      : plan.days[] entry (topic, pillar, post_type, platforms, ...)
 *   - post     : linked full post (or null)
 *   - schedule : effectiveSchedule(...) result ({ kind, label, time, ... })
 *   - onRevise : () => void  — drafting affordance when there's no post yet
 *   - showThumb: include the leading thumbnail (default true)
 */
export default function PostMiniCard({ day, post, schedule, onRevise, showThumb = true }) {
  const postId = post?.id || day?.post_id || null;
  const postType = post?.post_type || day?.post_type || "slideshow";
  const TypeIcon = TYPE_ICON[postType] || Images;
  const title = post?.hook_text || day?.hook_text || day?.topic || post?.topic || "(untitled)";
  const pillar = day?.pillar || post?.pillar || "";
  const format = post?.format_name || prettify(day?.format_slug || "");
  const platforms = (Array.isArray(post?.platforms) && post.platforms.length
    ? post.platforms
    : Array.isArray(day?.platforms) ? day.platforms : []);
  const thumb = mediaUrl(post?.thumbnail_url) || firstImageSrc(post?.slides_html);
  const viaDuct = post?.published_via === "duct";
  const kind = schedule?.kind || "proposed";

  const inner = (
    <article className="group flex gap-2.5 rounded-lg border border-border bg-card p-2 transition-colors hover:border-primary/40 hover:bg-muted/30">
      {showThumb && (
        <div className="relative size-12 shrink-0 overflow-hidden rounded-md border border-border/60 bg-muted/40">
          {thumb ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={thumb} alt="" className="size-full object-cover" />
          ) : (
            <div className="flex size-full items-center justify-center text-muted-foreground/70">
              <TypeIcon className="size-5" />
            </div>
          )}
        </div>
      )}

      <div className="min-w-0 flex-1 space-y-1">
        {/* meta row */}
        <div className="flex items-center gap-1.5">
          <span className={`inline-flex items-center gap-1 rounded px-1.5 py-px text-[10px] font-medium ${KIND_BADGE[kind]}`}>
            {schedule?.time && <Clock className="size-2.5" />}
            {schedule?.label || prettify(kind)}
          </span>
          {viaDuct && (
            <span className="rounded bg-primary/10 px-1.5 py-px text-[9px] font-semibold text-primary">via Duct</span>
          )}
          <TypeIcon className="ml-auto size-3 shrink-0 text-muted-foreground" />
        </div>

        <p className="line-clamp-2 text-xs font-medium leading-snug">{title}</p>

        {/* chips */}
        <div className="flex flex-wrap items-center gap-1">
          {pillar && (
            <span className="rounded-full bg-primary/10 px-1.5 py-px text-[9px] font-medium text-primary">{prettify(pillar)}</span>
          )}
          {format && (
            <span className="rounded-full border border-border/70 px-1.5 py-px text-[9px] text-muted-foreground">{format}</span>
          )}
          <span className="ml-auto flex items-center gap-1">
            {platforms.slice(0, 4).map((p) => {
              const meta = platformMeta(p);
              return (
                <span
                  key={p}
                  title={meta.label}
                  className="flex size-4 items-center justify-center rounded text-white"
                  style={{ backgroundColor: meta.color }}
                >
                  <PlatformGlyph platform={p} className="size-2.5" />
                </span>
              );
            })}
          </span>
        </div>
      </div>
    </article>
  );

  if (postId) {
    return <Link href={`/content/posts/${postId}`} className="block">{inner}</Link>;
  }
  if (onRevise) {
    return (
      <button type="button" onClick={onRevise} className="block w-full text-left">
        {inner}
      </button>
    );
  }
  return inner;
}
