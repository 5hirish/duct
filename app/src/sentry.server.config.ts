import * as Sentry from "@sentry/nextjs";

const appEnv = process.env.APP_ENV ?? process.env.NODE_ENV;

/**
 * Secrets that must never reach Sentry, even with `sendDefaultPii` on. Mirrors
 * `_SENSITIVE_HEADERS` in `backend/server.py` — the app's route handlers proxy
 * the same bring-your-own provider keys the backend receives, so scrubbing on
 * one side only leaves the other side publishing them.
 */
const SENSITIVE_HEADERS = new Set([
  "x-api-key",
  "x-provider-anthropic",
  "x-provider-openai",
  "x-provider-gemini",
  "x-provider-openrouter",
  "x-provider-xai",
  "x-openai-account-id",
  "authorization",
  "cookie",
]);

if (appEnv !== "local" && process.env.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    environment: appEnv,
    sendDefaultPii: true,
    tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.5,
    enableLogs: true,
    // No profiling here, deliberately. Node profiling needs
    // `@sentry/profiling-node`, which is a native V8 addon, and this app
    // deploys to Cloudflare Workers via OpenNext — workerd cannot load one.
    // `profileSessionSampleRate` / `profileLifecycle` used to sit here and were
    // inert for exactly that reason; server-side timing comes from tracing
    // above and from the `observability.traces` block in `wrangler.jsonc`.
    beforeSend(event) {
      const headers = event.request?.headers;
      if (headers) {
        for (const key of Object.keys(headers)) {
          if (SENSITIVE_HEADERS.has(key.toLowerCase())) headers[key] = "[Filtered]";
        }
      }
      return event;
    },
  });
}
