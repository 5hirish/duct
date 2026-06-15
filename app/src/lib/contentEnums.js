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

export const POST_STATUS_LABELS = Object.freeze({
  [PostStatus.PENDING]:   "Pending",
  [PostStatus.DRAFT]:     "Draft",
  [PostStatus.SCHEDULED]: "Scheduled",
  [PostStatus.POSTED]:    "Posted",
  [PostStatus.DISCARDED]: "Discarded",
});

export const AspectRatio = Object.freeze({
  SQUARE_1_1:     "1:1",
  PORTRAIT_9_16:  "9:16",
  LANDSCAPE_16_9: "16:9",
  PORTRAIT_3_4:   "3:4",
  LANDSCAPE_4_3:  "4:3",
  PORTRAIT_4_5:   "4:5",
});
