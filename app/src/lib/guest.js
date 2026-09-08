/**
 * A guest: a real account for someone who has not signed in.
 *
 * Onboarding runs an audit before anyone signs in, and everything the audit
 * makes — the project, the report, the conversation — needs an owner. So the
 * first "Audit my site" mints a guest on the backend (`POST /auth/guest`), a
 * real user row keyed on this install, and the token it returns is an
 * ordinary session token: `AuthGuard`, the project store and every agent
 * route treat a guest like anyone else. The only thing that knows the
 * difference is the `guest` claim, which is how the app says "save your
 * work" instead of showing an account nobody asked for.
 *
 * The install id is a uuid kept in storage. On the desktop the webview's
 * storage persists across launches, so a relaunch resumes the same guest and
 * the drafted project is still theirs; a cleared cache loses it, which the
 * account drawer says once.
 */

import { BASE } from "./api";
import { analytics } from "./analytics";
import { authToken, clearAuthToken, decodeJwtPayload, isTokenValid, setAuthToken } from "./authFetch";

export const INSTALL_ID_KEY = "duct_install_id";

function freshId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}

/** Stable per install, minted once. */
export function installId() {
  try {
    const existing = localStorage.getItem(INSTALL_ID_KEY);
    if (existing) return existing;
    const id = freshId();
    localStorage.setItem(INSTALL_ID_KEY, id);
    return id;
  } catch {
    return freshId();
  }
}

/** Whether `token` (the stored one by default) belongs to a guest. */
export function isGuestToken(token = authToken()) {
  if (!isTokenValid(token)) return false;
  return decodeJwtPayload(token)?.guest === true;
}

/** A valid token that is not a guest's — someone who actually signed in. */
export function isSignedInUser() {
  const token = authToken();
  return isTokenValid(token) && !isGuestToken(token);
}

/**
 * Make sure this browser holds a usable token, minting a guest if it holds
 * none. Idempotent: a signed-in user or an existing guest is returned as-is.
 */
export async function ensureGuest({ fresh = false } = {}) {
  const existing = authToken();
  if (!fresh && isTokenValid(existing)) {
    return { token: existing, guest: isGuestToken(existing), created: false };
  }
  // `fresh`: the token looked valid and the backend refused it anyway — a
  // secret rotated, a database reset. Keeping it would leave the person
  // stuck on "Invalid token" with nothing to click.
  if (fresh) clearAuthToken();
  const res = await fetch(`${BASE}/auth/guest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ install_id: installId() }),
  });
  if (!res.ok) {
    const retryAfter = Number(res.headers.get("Retry-After") || 0);
    const error = new Error(
      res.status === 429
        ? "Too many new sessions from this address — try again in a minute."
        : "Duct couldn't start a session. Check your connection and try again.",
    );
    error.status = res.status;
    error.retryAfter = retryAfter;
    throw error;
  }
  const { token, created } = await res.json();
  setAuthToken(token);
  // Same id the account will keep after sign-in (a link keeps the row), so
  // the funnel from first launch to first finding is one person.
  const uid = decodeJwtPayload(token)?.uid;
  if (uid) analytics.identify(uid);
  return { token, guest: true, created: Boolean(created) };
}
