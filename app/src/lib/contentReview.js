/**
 * The pre-publish review's vocabulary, mirrored from
 * backend/agents/content/schema.py (ReviewMarker, SanityCheckId, ReviewBand).
 *
 * The backend sends ids and never words, so every label a reader sees lives
 * here in a `msg` table and is translated. The marker weights are deliberately
 * not mirrored: the server owns them, and the panel only shows scores it has
 * already weighed — a second copy here is the copy that would drift.
 */

import { msg } from "@lingui/core/macro";

export const ReviewMarker = Object.freeze({
  HOOK_STRENGTH:          "hook_strength",
  NARRATIVE_MOMENTUM:     "narrative_momentum",
  SAVE_WORTHINESS:        "save_worthiness",
  SHAREABILITY_RESONANCE: "shareability_resonance",
  VISUAL_QUALITY:         "visual_quality",
  CTA_CAPTION_FIT:        "cta_caption_fit",
});

export const SanityCheckId = Object.freeze({
  SLIDES_HAVE_IMAGES:    "slides_have_images",
  IMAGES_FRESH:          "images_fresh",
  SLIDES_HAVE_HEADLINES: "slides_have_headlines",
  CAPTION_PRESENT:       "caption_present",
  CAPTION_LENGTH:        "caption_length",
  NO_PLACEHOLDER_TEXT:   "no_placeholder_text",
  HASHTAGS_PRESENT:      "hashtags_present",
  HASHTAGS_UNIQUE:       "hashtags_unique",
});

export const ReviewBand = Object.freeze({
  STRONG:     "strong",
  GOOD:       "good",
  NEEDS_WORK: "needs_work",
  NOT_READY:  "not_ready",
});

// Front-loaded and short: these sit in a narrow column beside a score bar.
export const MARKER_LABELS = Object.freeze({
  [ReviewMarker.HOOK_STRENGTH]:          msg`Hook`,
  [ReviewMarker.NARRATIVE_MOMENTUM]:     msg`Momentum`,
  [ReviewMarker.SAVE_WORTHINESS]:        msg`Save-worthiness`,
  [ReviewMarker.SHAREABILITY_RESONANCE]: msg`Shareability`,
  [ReviewMarker.VISUAL_QUALITY]:         msg`Visuals`,
  [ReviewMarker.CTA_CAPTION_FIT]:        msg`Call to action`,
});

export const BAND_META = Object.freeze({
  [ReviewBand.STRONG]:     { label: msg`Strong`,     badgeVariant: "success" },
  [ReviewBand.GOOD]:       { label: msg`Good`,       badgeVariant: "info" },
  [ReviewBand.NEEDS_WORK]: { label: msg`Needs work`, badgeVariant: "warning" },
  [ReviewBand.NOT_READY]:  { label: msg`Not ready`,  badgeVariant: "destructive" },
});

/** Whether the agent has scored this post (the checks exist either way). */
export function isScored(assessment) {
  return typeof assessment?.overall === "number";
}

/** The failed checks, hard before soft: what would ship broken comes first. */
export function failedChecks(assessment) {
  const failed = (assessment?.checks || []).filter((c) => !c.passed);
  return [...failed.filter((c) => c.severity !== "soft"), ...failed.filter((c) => c.severity === "soft")];
}

/** The `n` lowest-scored markers — the fixes worth reading first. Ties keep
 *  the server's canonical order, so the list does not reshuffle on a re-read. */
export function weakestMarkers(assessment, n) {
  return (assessment?.markers || [])
    .map((m, i) => ({ m, i }))
    .sort((a, b) => a.m.score - b.m.score || a.i - b.i)
    .slice(0, n)
    .map(({ m }) => m);
}

/** "slide-04" → 4. Null for anything that is not a slide ("caption", "#tag"). */
export function slideNumber(id) {
  const match = /^slide-(\d+)$/.exec(String(id || ""));
  return match ? Number(match[1]) : null;
}
