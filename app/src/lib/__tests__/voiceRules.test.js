import { describe, expect, it } from "vitest";
import {
  MAX_BANNED_WORDS,
  MAX_SAMPLE_CHARS,
  MAX_SAMPLES,
  addBannedWord,
  cleanSamples,
} from "../voiceRules.js";

describe("the banned-word list", () => {
  it("adds a word once, whatever its case or spacing", () => {
    expect(addBannedWord(["hot take"], "  Hot   TAKE ")).toEqual(["hot take"]);
    expect(addBannedWord(["hot take"], "synergy")).toEqual(["hot take", "synergy"]);
    expect(addBannedWord([], "   ")).toEqual([]);
  });

  it("stops at the cap the server holds", () => {
    const full = Array.from({ length: MAX_BANNED_WORDS }, (_, i) => `word ${i}`);
    expect(addBannedWord(full, "one more")).toBe(full);
  });
});

describe("writing samples", () => {
  it("drops blanks and keeps to the caps", () => {
    const out = cleanSamples(["  ", "x".repeat(MAX_SAMPLE_CHARS + 10), ...Array(9).fill("a post")]);
    expect(out[0]).toHaveLength(MAX_SAMPLE_CHARS);
    expect(out).toHaveLength(MAX_SAMPLES);
  });
});
