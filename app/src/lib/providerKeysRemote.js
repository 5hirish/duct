/**
 * The remembered half of bring-your-own-key.
 *
 * `providerKeys.js` holds a key in this browser session (or the desktop
 * keychain) and sends it as a header. That covers a person clicking through the
 * app and nothing else: the key is gone on refresh, and a run with no browser
 * attached — a scheduled brief, memory consolidation, artifact extraction — has
 * no header to read. Those are precisely the runs that would otherwise fall
 * back to Duct's own provider key, so remembering is what makes BYOK true for
 * the whole product rather than for the foreground of it.
 *
 * Stored server-side encrypted (`service/provider_keys.py`), decrypted only to
 * be spent, and never read back — there is deliberately no GET here. The card
 * learns a key exists from `/api/providers/status`, which reports presence.
 *
 * Its own module rather than a few functions in `providerKeys.js`: that one is
 * imported by `api.js`, so reaching back for `BASE` would close an import cycle.
 */

import { BASE, backendAuthedHeaders } from "./api";

/**
 * Remember `key` for `providerId` (a backend provider id — `google_genai`, not
 * `gemini`; that is what `PROVIDERS[].statusId` holds).
 *
 * Throws with the server's message on failure. Callers show it: a key the user
 * believes is saved and is not looks identical to success until a run fails.
 */
export async function rememberProviderKey(providerId, key) {
  const res = await fetch(`${BASE}/api/providers/${encodeURIComponent(providerId)}/key`, {
    method: "PUT",
    headers: backendAuthedHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ api_key: key }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Could not save the key (${res.status})`);
  }
  return res.json();
}

/** Forget the saved key for `providerId`. Idempotent; the row is deleted. */
export async function forgetProviderKey(providerId) {
  const res = await fetch(`${BASE}/api/providers/${encodeURIComponent(providerId)}/key`, {
    method: "DELETE",
    headers: backendAuthedHeaders(),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Could not remove the key (${res.status})`);
  }
  return res.json();
}
