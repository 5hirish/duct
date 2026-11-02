/**
 * Server-rendering errors, reported to PostHog from `instrumentation.ts`.
 *
 * The browser reporter (`./posthog.js`) only sees what reaches the browser; a
 * render that throws on the server reaches it as a generic error page. This
 * is the server half, and the only server code that names the vendor.
 *
 * Sent straight to PostHog rather than through the `/ingest` proxy, which
 * exists for ad blockers and no server has one. Off outside production builds
 * and without the project key, as the browser half is.
 */

import { PostHog } from "posthog-node";

import { scrubPath } from "./scrub.js";

const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY || "";
const HOST = process.env.POSTHOG_SERVER_HOST || "https://us.i.posthog.com";

let client = null;

function serverClient() {
  if (!KEY || process.env.NODE_ENV !== "production") return null;
  // One event per request at most, and a Worker may not outlive the response
  // by much: send at once instead of batching.
  if (!client) client = new PostHog(KEY, { host: HOST, flushAt: 1, flushInterval: 0 });
  return client;
}

/** The browser's PostHog id, if it has consented to the cookie that carries it. */
function distinctIdFrom(cookieHeader) {
  const match = new RegExp(`(?:^|;\\s*)ph_${KEY}_posthog=([^;]+)`).exec(cookieHeader || "");
  if (!match) return undefined;
  try {
    return JSON.parse(decodeURIComponent(match[1]))?.distinct_id || undefined;
  } catch {
    return undefined;
  }
}

/** Next.js `onRequestError`: the route that failed and what kind of render it was. */
export async function reportRequestError(error, request, context) {
  const posthog = serverClient();
  if (!posthog) return;
  const headers = request?.headers || {};
  const cookie = typeof headers.get === "function" ? headers.get("cookie") : headers.cookie;
  const distinctId = distinctIdFrom(cookie);
  try {
    await posthog.captureExceptionImmediate(error, distinctId, {
      surface: "app-server",
      $pathname: scrubPath(request?.path || ""),
      request_method: request?.method,
      route_path: context?.routePath,
      route_type: context?.routeType,
      router_kind: context?.routerKind,
      render_source: context?.renderSource,
      build_id: process.env.NEXT_PUBLIC_BUILD_ID || "dev",
      // An anonymous request has no person to attach to; do not invent one.
      ...(distinctId ? {} : { $process_person_profile: false }),
    });
  } catch {
    // Reporting a failure must never become a second one.
  }
}
