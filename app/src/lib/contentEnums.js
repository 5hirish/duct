/**
 * Mirrors of backend enums in agents/models.py.
 * Keep in sync — these drive checkbox/radio groups in publish modals and
 * plan day editors.
 *
 * Model selection is NOT mirrored here: the backend owns it end-to-end (the
 * image-gen tool defaults to DEFAULT_IMAGE_MODEL server-side and validates any
 * model string against the ImageModel enum), so the frontend never sends a
 * model id.
 */

import { msg } from "@lingui/core/macro";

export const Platform = Object.freeze({
  TIKTOK:          "tiktok",
  INSTAGRAM:       "instagram",
  YOUTUBE:         "youtube",
  LINKEDIN:        "linkedin",
  TWITTER:         "twitter",
  FACEBOOK:        "facebook",
  THREADS:         "threads",
  BLUESKY:         "bluesky",
  PINTEREST:       "pinterest",
  GOOGLE_BUSINESS: "google_business",
});

export const PLATFORM_LABELS = Object.freeze({
  [Platform.TIKTOK]:          "TikTok",
  [Platform.INSTAGRAM]:       "Instagram",
  [Platform.YOUTUBE]:         "YouTube",
  [Platform.LINKEDIN]:        "LinkedIn",
  [Platform.TWITTER]:         "Twitter / X",
  [Platform.FACEBOOK]:        "Facebook",
  [Platform.THREADS]:         "Threads",
  [Platform.BLUESKY]:         "Bluesky",
  [Platform.PINTEREST]:       "Pinterest",
  [Platform.GOOGLE_BUSINESS]: "Google Business",
});

// Mirrors ContentStatus in backend/agents/content/schema.py.
export const PostStatus = Object.freeze({
  PENDING:   "pending",   // agent-drafted, not yet saved by the user
  DRAFT:     "draft",     // saved/kept
  SCHEDULED: "scheduled",
  POSTED:    "posted",
  DISCARDED: "discarded",
});

// Message descriptors, not strings: this table is module-level, so it is
// rendered with `i18n._(POST_STATUS_LABELS[status])` in the component that
// shows it. PLATFORM_LABELS above stays plain — those are brand names.
export const POST_STATUS_LABELS = Object.freeze({
  [PostStatus.PENDING]:   msg`Pending`,
  [PostStatus.DRAFT]:     msg`Draft`,
  [PostStatus.SCHEDULED]: msg`Scheduled`,
  [PostStatus.POSTED]:    msg`Posted`,
  [PostStatus.DISCARDED]: msg`Discarded`,
});

// Mirrors POST_TYPES in backend/agents/content/schema.py (Day.post_type).
export const PostType = Object.freeze({
  SLIDESHOW: "slideshow",
  VIDEO:     "video",
  IMAGE:     "image",
});

// Descriptors, rendered with `i18n._(POST_TYPE_LABELS[type])`.
export const POST_TYPE_LABELS = Object.freeze({
  [PostType.SLIDESHOW]: msg`Slideshow`,
  [PostType.VIDEO]:     msg`Video`,
  [PostType.IMAGE]:     msg`Image`,
});

// Mirrors CloneApproach in backend/agents/content/schema.py: how closely a
// cloned post copies its reference, derived there from FIT × PROOF.
export const CloneApproach = Object.freeze({
  CLOSE:          "close",
  ADAPT:          "adapt",
  STRUCTURE_ONLY: "structure_only",
});

export const CLONE_APPROACH_LABELS = Object.freeze({
  [CloneApproach.CLOSE]:          msg`Copied closely`,
  [CloneApproach.ADAPT]:          msg`Adapted`,
  [CloneApproach.STRUCTURE_ONLY]: msg`Structure only`,
});

export const AspectRatio = Object.freeze({
  SQUARE_1_1:     "1:1",
  PORTRAIT_9_16:  "9:16",
  LANDSCAPE_16_9: "16:9",
  PORTRAIT_3_4:   "3:4",
  LANDSCAPE_4_3:  "4:3",
  PORTRAIT_4_5:   "4:5",
});
