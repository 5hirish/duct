// Environment helpers.

// True in local development, or when the app is served from a localhost-style
// host. Used to surface developer-only affordances — e.g. the agent's raw
// reasoning / "thinking" tokens in the chat UIs — that we deliberately keep
// hidden in production (a polished, non-technical product surface).
export function isDevEnv() {
  // Build-time signal: `next dev` sets NODE_ENV to "development"; the Cloudflare
  // production build sets it to "production". This is inlined identically on the
  // server and client, so it never causes a hydration mismatch.
  if (process.env.NODE_ENV !== "production") return true;
  // Runtime signal: a production build opened from localhost (e.g. previewing an
  // OpenNext build locally) should still expose dev affordances.
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  return (
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "0.0.0.0" ||
    host.endsWith(".local")
  );
}
