/**
 * Mirrors of backend enums in agents/models.py.
 * Keep in sync — these drive checkbox/radio groups in publish modals,
 * image-gen forms, and plan day editors.
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

export const PostStatus = Object.freeze({
  PENDING:   "pending",
  DRAFT:     "draft",
  POSTED:    "posted",
  DISCARDED: "discarded",
});

export const POST_STATUS_LABELS = Object.freeze({
  [PostStatus.PENDING]:   "Pending",
  [PostStatus.DRAFT]:     "Draft",
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

export const ImageModel = Object.freeze({
  GEMINI_3_1_FLASH_IMAGE_PREVIEW: "gemini-3.1-flash-image-preview",
  GEMINI_3_PRO_IMAGE_PREVIEW:     "gemini-3-pro-image-preview",
  GEMINI_2_5_FLASH_IMAGE:         "gemini-2.5-flash-image",
  IMAGEN_4_GENERATE_001:          "imagen-4.0-generate-001",
  IMAGEN_4_ULTRA_GENERATE_001:    "imagen-4.0-ultra-generate-001",
  IMAGEN_4_FAST_GENERATE_001:     "imagen-4.0-fast-generate-001",
});

export const DEFAULT_IMAGE_MODEL = ImageModel.GEMINI_3_1_FLASH_IMAGE_PREVIEW;
