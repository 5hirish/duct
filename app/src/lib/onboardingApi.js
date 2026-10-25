/**
 * The calls `/start` makes that nothing else does: read a site ahead of the
 * audit, read the documents the user adds beside it, verify a provider key by
 * spending it, and mint the code that links a guest to the account a sign-in
 * is about to create.
 *
 * Errors carry the backend's `reason` where it gave one, so the URL screen
 * can tell "not a public address" from "no answer" without matching prose.
 */

import { i18n } from "@lingui/core";
import { msg } from "@lingui/core/macro";

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
  const status = res.status;
  const message =
    structured?.message ||
    (typeof detail === "string" ? detail : "") ||
    (status === 429
      ? i18n._(msg`That is a lot of sites in a row — try again in a few minutes.`)
      : i18n._(msg`Request failed (${status}).`));
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

// The backend's limits (service/documents.py), mirrored so a file that will
// be refused says so on its tile before it is uploaded. The server still
// checks every one; these only save the round trip.
export const DOCUMENT_MAX_FILES = 5;
export const DOCUMENT_MAX_BYTES = 10 * 1024 * 1024;
export const DOCUMENT_EXTENSIONS = Object.freeze(["pdf", "docx", "pptx", "md", "markdown", "txt"]);

/** Why a document gave no text: the backend's `Unreadable` codes, plus the
 *  one only the browser can see. The tile words each one. */
export const DocumentError = Object.freeze({
  UNSUPPORTED: "unsupported",
  TOO_LARGE: "too_large",
  ENCRYPTED: "encrypted",
  NO_TEXT: "no_text",
  DAMAGED: "damaged",
  UPLOAD_FAILED: "upload_failed",
});

/** The refusal the backend would give `file`, when the browser can already
 *  tell; null when only the server can say. */
export function localDocumentError(file) {
  const name = file?.name || "";
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : "";
  if (!DOCUMENT_EXTENSIONS.includes(ext)) return DocumentError.UNSUPPORTED;
  if ((file?.size || 0) > DOCUMENT_MAX_BYTES) return DocumentError.TOO_LARGE;
  return null;
}

/**
 * Read up to five files now. Resolves to one result per file, in order:
 * `{ id, name, kind, pages, chars, truncated }` for a file that was read, or
 * `{ name, error }` with a `DocumentError` code for one that was not.
 */
export async function uploadDocuments(files) {
  const body = new FormData();
  for (const file of files) body.append("files", file, file.name);
  // No Content-Type: the browser writes the multipart boundary into it.
  const res = await fetch(`${BASE}/api/audit/documents`, {
    method: "POST",
    headers: backendAuthedHeaders(),
    body,
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()).documents;
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
