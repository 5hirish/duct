/**
 * The pre-publish review's vocabulary, mirrored from
 * backend/agents/content/schema.py (ReviewMarker, SanityCheckId, ReviewBand,
 * PersonaVerdict, PanelFit).
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

// What an audience persona says it would do with the post. Three words, not a
// score: the reviewer reads them off the persona's own reaction.
export const PersonaVerdict = Object.freeze({
  YES:   "yes",
  MAYBE: "maybe",
  NO:    "no",
});

// What a persona is asked, in the order a feed meets a post: does it stop,
// start a conversation, keep it, pass it to someone in its circle, go and see
// who made it. A review from before comment and share has neither, and its
// chips simply leave them out.
export const PERSONA_ACTIONS = Object.freeze([
  { key: "stop",    label: msg`Stops` },
  { key: "comment", label: msg`Comments` },
  { key: "save",    label: msg`Saves` },
  { key: "share",   label: msg`Shares` },
  { key: "click",   label: msg`Visits profile` },
]);

// How closely the panel's order of the brand's past posts matched what those
// posts really earned: the share of pairs it put the right way round, where a
// coin gets half. Decides how sure the panel's words may sound.
export const PanelFit = Object.freeze({
  TRACKS: "tracks",
  LOOSE:  "loose",
  CHANCE: "chance",
});

// The goal measure a panel check ranked on (backend agents/content/performance.py).
export const PANEL_METRIC_LABELS = Object.freeze({
  intent:     msg`saves and shares`,
  engagement: msg`comments, shares and saves`,
  reached:    msg`reach`,
});

// The openings the panel chose between, by place: the post's own, then two rewrites.
export const HOOK_LABELS = Object.freeze([msg`Your opening`, msg`Opening B`, msg`Opening C`]);

/** Whether the yes/maybe/no chips earn a place: only once the panel has
 *  ranked the brand's own past posts better than a coin. A twin's verdict on
 *  one post leans kind, so untested it is words only. */
export function panelTrusted(assessment) {
  const fit = assessment?.panel_check?.fit;
  return fit === PanelFit.TRACKS || fit === PanelFit.LOOSE;
}

/** How many personas picked each opening, by its index in `hooks`. */
export function hookVotes(assessment) {
  const votes = (assessment?.hooks || []).map(() => 0);
  for (const r of assessment?.personas || []) {
    if (Number.isInteger(r.pick) && r.pick < votes.length) votes[r.pick] += 1;
  }
  return votes;
}

/** True when every persona reacted exactly as someone matching none of them
 *  did: then the panel is the model's average reader, not the audience. */
export function panelEchoesBaseline(assessment) {
  const base = assessment?.baseline;
  const personas = assessment?.personas || [];
  if (!base || personas.length === 0) return false;
  return personas.every((r) => PERSONA_ACTIONS.every(({ key }) => r[key] === base[key]) && r.pick === base.pick);
}

export const VERDICT_META = Object.freeze({
  [PersonaVerdict.YES]:   { label: msg`Yes`,   tone: "yes" },
  [PersonaVerdict.MAYBE]: { label: msg`Maybe`, tone: "maybe" },
  [PersonaVerdict.NO]:    { label: msg`No`,    tone: "no" },
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

/** How a 0-100 score reads, on the bar the draft check holds a new draft to
 *  (backend agents/content/assessment.DRAFT_BAR): good from 70, mixed from 50. */
export function scoreTone(score) {
  return score >= 70 ? "good" : score >= 50 ? "mixed" : "weak";
}

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

/** "reply-2" → 2: a text post's reply, as agents/content/assessment.reply_id
 *  names it. Null for anything else. */
export function replyNumber(id) {
  const match = /^reply-(\d+)$/.exec(String(id || ""));
  return match ? Number(match[1]) : null;
}
