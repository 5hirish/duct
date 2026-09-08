/**
 * The three calls `/start` makes that nothing else does: read a site ahead
 * of the audit, verify a provider key by spending it, and mint the code that
 * links a guest to the account a sign-in is about to create.
 *
 * Errors carry the backend's `reason` where it gave one, so the URL screen
 * can tell "not a public address" from "no answer" without matching prose.
 */

import { BASE, backendAuthedHeaders } from "./api";
import { providerKeyHeaders } from "./providerKeys";

export class OnboardingError extends Error {
  constructor(message, { reason = "", status = 0, retryAfter = 0 } = {}) {
    super(message);
    this.name = "OnboardingError";
    this.reason = reason;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

async function failure(res) {
  let detail = null;
  try {
    detail = (await res.json())?.detail ?? null;
  } catch {
    detail = null;
  }
  const structured = detail && typeof detail === "object" ? detail : null;
  const message =
    structured?.message ||
    (typeof detail === "string" ? detail : "") ||
    (res.status === 429 ? "That is a lot of sites in a row — try again in a few minutes." : `Request failed (${res.status}).`);
  return new OnboardingError(message, {
    reason: structured?.reason || "",
    status: res.status,
    retryAfter: Number(res.headers.get("Retry-After") || 0),
  });
}

/**
 * Read the root page now and crawl the rest in the background.
 * Resolves to the prefetch status: `{ crawl_id, state, pages, site, draft }`.
 */
export async function prefetchSite(url, { light = false } = {}) {
  const res = await fetch(`${BASE}/api/audit/prefetch`, {
    method: "POST",
    headers: backendAuthedHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ url, light }),
  });
  if (!res.ok) throw await failure(res);
  return res.json();
}

export async function prefetchStatus(crawlId) {
  const res = await fetch(`${BASE}/api/audit/prefetch/${encodeURIComponent(crawlId)}`, {
    headers: backendAuthedHeaders(),
  });
  if (!res.ok) throw await failure(res);
  return res.json();
}

/**
 * One minimal completion on the provider's cheapest model, with whatever key
 * this browser holds for it. Resolves to `{ ok, model, latency_ms }` or
 * `{ ok: false, code, detail }` — the code is the thing to render.
 */
export async function verifyProvider(providerStatusId) {
  const res = await fetch(`${BASE}/api/providers/${encodeURIComponent(providerStatusId)}/verify`, {
    method: "POST",
    headers: { ...backendAuthedHeaders(), ...(await providerKeyHeaders()) },
  });
  if (!res.ok) throw await failure(res);
  return res.json();
}

/** A five-minute code naming this guest, for the sign-in authorize URL. */
export async function guestLinkCode() {
  const res = await fetch(`${BASE}/auth/guest/link-code`, {
    method: "POST",
    headers: backendAuthedHeaders(),
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()).code;
}
