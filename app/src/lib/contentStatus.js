// Shared visual styling for content post / plan-day statuses, used by the
// Kanban columns, the Calendar dots, and the legend so colors stay consistent.

import { msg } from "@lingui/core/macro";
import { PostStatus, POST_STATUS_LABELS } from "./contentEnums";

/**
 * One status, one colour, named by meaning rather than by hue.
 *
 * This map used to reach for green-500, amber-400, rose-500 and their 700/400
 * dark partners directly, which is how the app ended up with eight hues for
 * four meanings: every file that needed "this went out fine" picked its own
 * green, and the ones picked as *text* (`text-success` at 2.22:1,
 * `text-warning` at 2.15:1) were unreadable on a light page. The status
 * tokens carry a contrast-checked pair per theme, so a caller gets dark mode
 * for free and the guard in `check-contrast.mjs` notices if that stops being
 * true.
 *
 * `badgeVariant` is the preferred way in — `<Badge variant={meta.badgeVariant}>`
 * — with `dotClass`/`softClass`/`textClass` for the places that are not a badge.
 * `solidClass` is the exception, for a chip sitting on a photograph: a 10%
 * tint over an unknown image is not a colour, so those pair the full status
 * colour with its `-foreground` partner. Those partners are exactly the three
 * utilities the theme never generated, which is why this was white-on-green
 * before and not simply the wrong token.
 *
 * `label` is a message descriptor (the table is module-level), so render it
 * with `i18n._(meta.label)`.
 */
export const STATUS_META = Object.freeze({
  [PostStatus.PENDING]: {
    label: POST_STATUS_LABELS[PostStatus.PENDING],
    badgeVariant: "secondary",
    solidClass: "bg-foreground text-background",
    dotClass: "bg-muted-foreground/50",
    softClass: "bg-muted text-muted-foreground",
    accentClass: "border-border bg-muted/30",
    textClass: "text-muted-foreground",
  },
  [PostStatus.DRAFT]: {
    label: POST_STATUS_LABELS[PostStatus.DRAFT],
    badgeVariant: "warning",
    solidClass: "bg-warning text-warning-foreground",
    dotClass: "bg-warning",
    softClass: "bg-warning/10 text-warning dark:bg-warning/20",
    accentClass: "border-warning/30 bg-warning/5",
    textClass: "text-warning",
  },
  [PostStatus.POSTED]: {
    label: POST_STATUS_LABELS[PostStatus.POSTED],
    badgeVariant: "success",
    solidClass: "bg-success text-success-foreground",
    dotClass: "bg-success",
    softClass: "bg-success/10 text-success dark:bg-success/20",
    accentClass: "border-success/30 bg-success/5",
    textClass: "text-success",
  },
  [PostStatus.DISCARDED]: {
    label: POST_STATUS_LABELS[PostStatus.DISCARDED],
    badgeVariant: "destructive",
    solidClass: "bg-destructive text-destructive-foreground",
    dotClass: "bg-destructive",
    softClass: "bg-destructive/10 text-destructive dark:bg-destructive/20",
    accentClass: "border-destructive/25 bg-destructive/5",
    textClass: "text-destructive",
  },
});

/** The scheduled state is a plan slot, not a stored status — same vocabulary. */
export const SCHEDULED_META = Object.freeze({
  label: msg`Scheduled`,
  badgeVariant: "info",
  solidClass: "bg-info text-info-foreground",
  dotClass: "bg-info",
  softClass: "bg-info/10 text-info dark:bg-info/20",
  accentClass: "border-info/30 bg-info/5",
  textClass: "text-info",
});

// Column / legend order.
export const STATUS_ORDER = Object.freeze([
  PostStatus.PENDING,
  PostStatus.DRAFT,
  PostStatus.POSTED,
  PostStatus.DISCARDED,
]);

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META[PostStatus.PENDING];
}

/**
 * Safely extract a thumbnail image src from a post's slides_html.
 * Only returns data: or http(s) URLs so we never emit a broken relative src.
 */
export function firstImageSrc(html) {
  if (typeof html !== "string" || !html) return "";
  const match = html.match(/<img[^>]+src=["']([^"']+)["']/i);
  const src = match?.[1] || "";
  return /^(data:|https?:)/i.test(src) ? src : "";
}
