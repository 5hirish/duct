"use client";

import Link from "next/link";
import { Images, Video, Image as ImageIcon, Clock, Type, ChevronRight, Target } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { mediaUrl } from "@/lib/contentApi";
import { POST_TYPE_LABELS, PostStatus } from "@/lib/contentEnums";
import { SCHEDULED_META, firstImageSrc, statusMeta } from "@/lib/contentStatus";
import { KIND_LABEL } from "@/lib/contentSchedule";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";
import { ClipStill } from "@/components/content/PostVideo";
import { Badge } from "@/components/ui/badge";
import { titleCase } from "@/lib/format";

// Shared with PlanStrategy, so a post type has one icon wherever it appears.
export const TYPE_ICON = { slideshow: Images, video: Video, image: ImageIcon, text: Type };

const KIND_BADGE = {
  published: "bg-success/15 text-success",
  scheduled: "bg-info/15 text-info",
  proposed: "bg-muted text-muted-foreground",
};

/**
 * One modular post card, shared by every plan view via `variant`:
 *   - "full"    : thumbnail banner with overlaid type/via-Duct/platforms, plus
 *                 schedule + title + pillar/format below. Used by the Kanban
 *                 lanes (the lane already encodes status, so no status marker).
 *   - "compact" : no thumbnail; a status dot + inline meta/chips. Used by the
 *                 Week calendar where a single day mixes statuses.
 *   - "chip"    : a single status-tinted line (type icon + title + primary
 *                 platform). Used by the Month calendar cells.
 *   - "row"     : one agenda line — weekday and date, a cover tile, title,
 *                 type · pillar · goal, then the status. Used by PlanList.
 *                 A pending row carries no badge: on a fresh plan that would
 *                 be thirty identical pills, so only the rows that moved say
 *                 so and the rest offer to be drafted.
 *
 * Props:
 *   - day      : plan.days[] entry (topic, pillar, post_type, platforms, ...)
 *   - post     : linked full post (or null)
 *   - schedule : effectiveSchedule(...) result ({ kind, label, time, ... })
 *   - onRevise : () => void  — drafting affordance when there's no post yet
 *   - variant  : "full" | "compact" | "chip" | "row" (default "full")
 */
export default function PostMiniCard({ day, post, schedule, onRevise, variant = "full" }) {
  const { t, i18n } = useLingui();
  const postId = post?.id || day?.post_id || null;
  const postType = post?.post_type || day?.post_type || "slideshow";
  const TypeIcon = TYPE_ICON[postType] || Images;
  const title = post?.hook_text || day?.hook_text || day?.topic || post?.topic || t`(untitled)`;
  const pillar = day?.pillar || post?.pillar || "";
  const format = post?.format_name || titleCase(day?.format_slug || "");
  const platforms = (Array.isArray(post?.platforms) && post.platforms.length
    ? post.platforms
    : Array.isArray(day?.platforms) ? day.platforms : []);
  const thumb = mediaUrl(post?.thumbnail_url) || firstImageSrc(post?.slides_html);
  const viaDuct = post?.published_via === "duct";
  const kind = schedule?.kind || "proposed";
  const status = post?.status || day?.status || "pending";
  const sMeta = statusMeta(status);

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
  if (variant === "row") {
    const date = schedule?.date || null;
    const typeLabel = POST_TYPE_LABELS[postType];
    const objective = day?.objective || "";
    const badge = schedule?.kind === "scheduled" ? SCHEDULED_META : sMeta;
    inner = (
      <div className="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors group-hover/row:bg-muted/60">
        {/* The agenda's spine: weekday over day number, the way a calendar's
            schedule view reads. The week header above carries the month. */}
        <div className="w-9 shrink-0 text-center leading-none">
          {date && (
            <>
              <p className="text-2xs font-medium uppercase tracking-wide text-muted-foreground">
                {date.toLocaleDateString(i18n.locale, { weekday: "short" })}
              </p>
              <p className="mt-1 text-base font-semibold tabular-nums">{date.getDate()}</p>
            </>
          )}
        </div>

        {/* The cover once there is one; the post type until then. */}
        <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted/40 text-muted-foreground">
          {thumb ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={thumb} alt="" className="size-full object-cover" />
          ) : (
            <TypeIcon className="size-4" aria-hidden />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm font-medium leading-snug">{title}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-2xs text-muted-foreground">
            <span>{typeLabel ? i18n._(typeLabel) : titleCase(postType)}</span>
            {pillar && <><span aria-hidden>·</span><span>{titleCase(pillar)}</span></>}
            {objective && (
              <>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1">
                  <Target className="size-2.5" aria-hidden />
                  <span className="sr-only"><Trans>Goal:</Trans></span>
                  {titleCase(objective)}
                </span>
              </>
            )}
            {schedule?.time && (
              <>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1"><Clock className="size-2.5" aria-hidden />{schedule.time}</span>
              </>
            )}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {/* Platforms only where there is room; the title outranks them. */}
          {platformBadges.length > 0 && (
            <span className="hidden items-center gap-1 @md:flex">{platformBadges}</span>
          )}
          {status === PostStatus.PENDING ? (
            (postId || onRevise) && (
              <span className="flex items-center gap-0.5 text-xs text-muted-foreground group-hover/row:text-foreground group-focus-visible/row:text-foreground">
                <span className="opacity-0 transition-opacity group-hover/row:opacity-100 group-focus-visible/row:opacity-100">
                  <Trans>Draft post</Trans>
                </span>
                <ChevronRight className="size-4" aria-hidden />
              </span>
            )
          ) : (
            <Badge variant={badge.badgeVariant}>{i18n._(badge.label)}</Badge>
          )}
        </div>
      </div>
    );
  } else if (variant === "chip") {
    // Single-line month chip: status carried by the tinted background; the
    // leading type icon and trailing primary-platform glyph add format + reach.
    const primary = platforms[0] || null;
    const pMeta = primary ? platformMeta(primary) : null;
    inner = (
      <span
        className={`flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-2xs leading-tight transition-opacity hover:opacity-80 ${sMeta.softClass}`}
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
              ) : post?.video?.url ? (
                <ClipStill url={post.video.url} className="size-full object-cover" />
              ) : postType === "text" && post?.caption ? (
                // A text post's preview is its opening words.
                <p className="line-clamp-4 size-full whitespace-pre-line px-3 py-2 text-2xs leading-snug">{post.caption}</p>
              ) : (
                <div className="flex size-full items-center justify-center text-muted-foreground">
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
                  className="absolute bottom-2 left-2 rounded-md px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide text-white shadow-sm backdrop-blur-sm"
                  style={{ backgroundColor: "color-mix(in srgb, var(--orange) 45%, rgba(0,0,0,0.65))" }}
                >
                  <Trans>via Duct</Trans>
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
              <span className={`rounded-md px-1.5 py-0.5 text-2xs font-medium ${KIND_BADGE[kind]}`}>
                {KIND_LABEL[kind] ? i18n._(KIND_LABEL[kind]) : titleCase(kind)}
              </span>
              {dateText && (
                <span className="inline-flex items-center gap-1 text-2xs text-muted-foreground">
                  {schedule?.time && <Clock className="size-2.5" />}
                  {dateText}
                </span>
              )}
              {/* without a thumbnail (Week view) these stay inline */}
              {!showThumb && viaDuct && (
                <span
                  className="rounded-md px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide"
                  style={{ backgroundColor: "color-mix(in oklch, var(--orange) 15%, transparent)", color: "var(--orange)" }}
                >
                  <Trans>via Duct</Trans>
                </span>
              )}
              {!showThumb && <TypeIcon className="ml-auto size-3.5 shrink-0 text-muted-foreground" />}
            </div>

            <p className="line-clamp-2 text-sm font-medium leading-snug text-foreground">{title}</p>

            {/* chips */}
            <div className="flex flex-wrap items-center gap-1 pt-0.5">
              {pillar && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-medium text-primary">{titleCase(pillar)}</span>
              )}
              {format && (
                <span className="rounded-full border border-border/70 px-2 py-0.5 text-2xs text-muted-foreground">{format}</span>
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
  // `group/row` is what the row variant's hover and focus styles key off.
  if (postId) {
    const href = status === "draft" ? `/content/posts/${postId}?revise=1` : `/content/posts/${postId}`;
    return (
      <Link
        href={href}
        title={variant === "chip" ? title : undefined}
        className="group/row block rounded-lg"
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
        className="group/row block w-full rounded-lg text-left"
      >
        {inner}
      </button>
    );
  }
  return inner;
}
