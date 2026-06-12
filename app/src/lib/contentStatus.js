// Shared visual styling for content post / plan-day statuses, used by the
// Kanban columns, the Calendar dots, and the legend so colors stay consistent.

import { PostStatus, POST_STATUS_LABELS } from "./contentEnums";

export const STATUS_META = Object.freeze({
  [PostStatus.PENDING]: {
    label: POST_STATUS_LABELS[PostStatus.PENDING],
    dotClass: "bg-muted-foreground/50",
    softClass: "bg-muted text-muted-foreground",
    accentClass: "border-amber-400/40 bg-amber-50/40 dark:bg-amber-950/10",
    textClass: "text-muted-foreground",
  },
  [PostStatus.DRAFT]: {
    label: POST_STATUS_LABELS[PostStatus.DRAFT],
    dotClass: "bg-amber-400",
    softClass: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
    accentClass: "border-blue-400/40 bg-blue-50/40 dark:bg-blue-950/10",
    textClass: "text-amber-500",
  },
  [PostStatus.POSTED]: {
    label: POST_STATUS_LABELS[PostStatus.POSTED],
    dotClass: "bg-green-500",
    softClass: "bg-green-500/15 text-green-700 dark:text-green-400",
    accentClass: "border-green-400/40 bg-green-50/40 dark:bg-green-950/10",
    textClass: "text-green-500",
  },
  [PostStatus.DISCARDED]: {
    label: POST_STATUS_LABELS[PostStatus.DISCARDED],
    dotClass: "bg-rose-500",
    softClass: "bg-rose-500/15 text-rose-700 dark:text-rose-400",
    accentClass: "border-muted-foreground/30 bg-muted/40",
    textClass: "text-rose-500",
  },
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
