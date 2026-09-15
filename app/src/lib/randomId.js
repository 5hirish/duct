/**
 * One unguessable id, from the platform's CSPRNG.
 *
 * Two modules were minting identifiers the same way — a local project id and
 * the install id that identifies a guest to the backend — and both fell back
 * to `Math.random()` when `crypto.randomUUID` was missing. `randomUUID` is
 * secure-context-only, so that fallback was not dead code: it is the path a
 * plain-http dev host takes. Math.random is seeded, predictable and shared
 * with every other caller in the page, which makes a guessable id for two
 * values that stand in for a user's identity. Code scanning flagged it as
 * insecure randomness, and it was right.
 *
 * `getRandomValues` closes it: same CSPRNG, no secure-context requirement, so
 * the fallback is as strong as the happy path instead of a quiet downgrade.
 */
export function randomId() {
  const c = typeof crypto !== "undefined" ? crypto : null;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  if (c && typeof c.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    c.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  // No Web Crypto at all means a browser older than every one we support, or a
  // stripped runtime. Failing loudly beats handing back a predictable id that
  // then identifies someone.
  throw new Error("randomId: this runtime has no Web Crypto");
}

export default randomId;
