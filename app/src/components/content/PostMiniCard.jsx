"use client";

import Link from "next/link";
import { Images, Video, Image as ImageIcon, Clock } from "lucide-react";
import { mediaUrl } from "@/lib/contentApi";
import { firstImageSrc, statusMeta } from "@/lib/contentStatus";
import { PostType } from "@/lib/contentEnums";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";

const TYPE_ICON = { [PostType.SLIDESHOW]: Images, [PostType.VIDEO]: Video, [PostType.IMAGE]: ImageIcon };

const KIND_BADGE = {
  published: "bg-green-500/15 text-green-600 dark:text-green-400",
  scheduled: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  proposed: "bg-muted text-muted-foreground",
};

const KIND_LABEL = { published: "Published", scheduled: "Scheduled", proposed: "Planned" };

function prettify(s) {
  return String(s || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * One modular post card, shared by every plan view via `variant`:
 *   - "full"    : thumbnail banner with overlaid type/via-Duct/platforms, plus
 *                 schedule + title + pillar/format below. Used by the Kanban
 *                 lanes (the lane already encodes status, so no status marker).
 *   - "compact" : no thumbnail; a status dot + inline meta/chips. Used by the
 *                 Week calendar where a single day mixes statuses.
 *   - "chip"    : a single status-tinted line (type icon + title + primary
 *                 platform). Used by the Month calendar cells.
 *
 * Props:
 *   - day      : plan.days[] entry (topic, pillar, post_type, platforms, ...)
 *   - post     : linked full post (or null)
 *   - schedule : effectiveSchedule(...) result ({ kind, label, time, ... })
 *   - onRevise : () => void  — drafting affordance when there's no post yet
 *   - variant  : "full" | "compact" | "chip" (default "full")
 */
export default function PostMiniCard({ day, post, schedule, onRevise, variant = "full" }) {
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
  const status = post?.status || day?.status || "pending";
  const sMeta = statusMeta(status);
  const cloneKind = post?.clone_source?.kind;
  const isClone = cloneKind === "url" || cloneKind === "reference";

  const showThumb = variant === "full";
  // In Week/Month the card sits under its day column, so the date is redundant —
  // show only the time. The Kanban has no date context, so show the full date.
  const dateText = showThumb ? (schedule?.dateLabel || "") : (schedule?.time || "");

  const platformBadges = platforms.slice(0, 4).map((p) => {
    const meta = platformMeta(p);
    return (
      <span
        key={p}
        title={meta.label}
        className="flex size-[18px] items-center justify-center rounded-md text-white shadow-sm"
        style={{ backgroundColor: meta.color }}
      >
        <PlatformGlyph platform={p} className="size-2.5" />
      </span>
    );
  });

  let inner;
  if (variant === "chip") {
    // Single-line month chip: status carried by the tinted background; the
    // leading type icon and trailing primary-platform glyph add format + reach.
    const primary = platforms[0] || null;
    const pMeta = primary ? platformMeta(primary) : null;
    inner = (
      <span
        className={`flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-[11px] leading-tight transition-opacity hover:opacity-80 ${sMeta.softClass}`}
      >
        <TypeIcon className="size-3 shrink-0 opacity-80" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-medium">{title}</span>
        {pMeta && (
          <span
            title={pMeta.label}
            className="flex size-3.5 shrink-0 items-center justify-center rounded-sm text-white"
            style={{ backgroundColor: pMeta.color }}
          >
            <PlatformGlyph platform={primary} className="size-2" />
          </span>
        )}
      </span>
    );
  } else {
    inner = (
      <article className="group relative flex overflow-hidden rounded-xl border border-border bg-card shadow-xs transition-all hover:-translate-y-px hover:border-primary/40 hover:shadow-sm">
        <div className="flex min-w-0 flex-1 flex-col">
          {showThumb && (
            <div className="relative aspect-video w-full overflow-hidden border-b border-border/60 bg-muted/40">
              {thumb ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={thumb} alt="" className="size-full object-cover" />
              ) : (
                <div className="flex size-full items-center justify-center text-muted-foreground/30">
                  <ImageIcon className="size-7" />
                </div>
              )}

              {/* top-left: content type */}
              <span className="absolute left-2 top-2 flex items-center justify-center rounded-md bg-black/55 p-1 text-white backdrop-blur-sm">
                <TypeIcon className="size-3.5" />
              </span>

              {/* bottom-left: via Duct — subtle brand-orange glass */}
              {viaDuct && (
                <span
                  className="absolute bottom-2 left-2 rounded-md px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-white shadow-sm backdrop-blur-sm"
                  style={{ backgroundColor: "color-mix(in srgb, var(--orange) 45%, rgba(0,0,0,0.65))" }}
                >
                  via Duct
                </span>
              )}

              {/* bottom-right: platforms */}
              {platformBadges.length > 0 && (
                <span className="absolute bottom-2 right-2 flex items-center gap-1">{platformBadges}</span>
              )}
            </div>
          )}

          <div className="min-w-0 flex-1 space-y-1.5 p-2.5">
            {/* meta row — color-coded kind pill carries the state; muted date keeps the title the hero */}
            <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
              <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${KIND_BADGE[kind]}`}>
                {KIND_LABEL[kind] || prettify(kind)}
              </span>
              {isClone && (
                <span className="rounded-md bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-medium text-violet-600 dark:text-violet-400">
                  Clone
                </span>
              )}
              {dateText && (
                <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                  {schedule?.time && <Clock className="size-2.5" />}
                  {dateText}
                </span>
              )}
              {/* without a thumbnail (Week view) these stay inline */}
              {!showThumb && viaDuct && (
                <span
                  className="rounded-md px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide"
                  style={{ backgroundColor: "color-mix(in oklch, var(--orange) 15%, transparent)", color: "var(--orange)" }}
                >
                  via Duct
                </span>
              )}
              {!showThumb && <TypeIcon className="ml-auto size-3.5 shrink-0 text-muted-foreground/70" />}
            </div>

            <p className="line-clamp-2 text-[13px] font-medium leading-snug text-foreground">{title}</p>

            {/* chips */}
            <div className="flex flex-wrap items-center gap-1 pt-0.5">
              {pillar && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">{prettify(pillar)}</span>
              )}
              {format && (
                <span className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] text-muted-foreground">{format}</span>
              )}
              {!showThumb && platformBadges.length > 0 && (
                <span className="ml-auto flex items-center gap-1">{platformBadges}</span>
              )}
            </div>
          </div>
        </div>
      </article>
    );
  }

  // Shared interaction: link to the post (status-aware) or the create flow.
  // stopPropagation keeps a Month chip's click from also firing the day cell.
  // Pending entries (manual or not-yet-ingested clones) prefer the drafting
  // affordance (onRevise) over a detail link — they aren't real drafts yet.
  const draftablePending = status === "pending" && onRevise;
  if (postId && !draftablePending) {
    const href = status === "draft" ? `/content/posts/${postId}?revise=1` : `/content/posts/${postId}`;
    return (
      <Link
        href={href}
        title={variant === "chip" ? title : undefined}
        className="block"
        onClick={(e) => e.stopPropagation()}
      >
        {inner}
      </Link>
    );
  }
  if (onRevise) {
    return (
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onRevise(); }}
        title={variant === "chip" ? title : undefined}
        className="block w-full text-left"
      >
        {inner}
      </button>
    );
  }
  return inner;
}
