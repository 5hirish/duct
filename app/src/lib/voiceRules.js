// A project's own voice for its text posts (issue #271): the caps and the
// banned-word list's editing rules. Mirrors backend/agents/content/voice_rules.py,
// whose route refuses anything past these caps, so the Brand tab stops a
// person before the server has to.

export const SAMPLES_KEY = "writing_samples";
export const RULES_KEY = "voice_rules";

export const MAX_SAMPLES = 5;
export const MAX_SAMPLE_CHARS = 1500;
export const MAX_BANNED_WORDS = 50;
export const MAX_BANNED_WORD_CHARS = 60;

/**
 * The list with `word` added: spaces collapsed, held to the length cap, and
 * left alone when it is blank, already there (in any case) or full.
 */
export function addBannedWord(list, word) {
  const clean = String(word || "").split(/\s+/).filter(Boolean).join(" ").slice(0, MAX_BANNED_WORD_CHARS);
  const words = Array.isArray(list) ? list : [];
  if (!clean || words.length >= MAX_BANNED_WORDS) return words;
  if (words.some((w) => w.toLowerCase() === clean.toLowerCase())) return words;
  return [...words, clean];
}

/** Samples worth saving: trimmed, blanks dropped, within the caps. */
export function cleanSamples(samples) {
  return (Array.isArray(samples) ? samples : [])
    .map((s) => String(s || "").trim().slice(0, MAX_SAMPLE_CHARS))
    .filter(Boolean)
    .slice(0, MAX_SAMPLES);
}
