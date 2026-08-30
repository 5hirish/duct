/**
 * Starting a connector's OAuth, from a browser or from the desktop shell.
 *
 * Everywhere else in this app "sign in with Google" is a plain navigation. In
 * the desktop shell it cannot be: Google refuses OAuth inside an embedded
 * webview (`disallowed_useragent`), and even where a provider allows it the
 * user arrives without their browser session, password manager, or passkeys.
 * Every desktop app that connects third-party accounts — Claude and ChatGPT
 * included — therefore hands the dance to the system browser and takes the
 * result back through a custom-scheme deep link. This is that, for connectors;
 * `(auth)/page.js` already does it for Duct's own sign-in.
 *
 * Gated on the `browserConnectors` capability, never on the shell version: a
 * shell built before the deep-link route existed reports no flag and correctly
 * keeps the in-window navigation, which is all it can do.
 */

import { BASE, backendApiKey } from "./api.js";
import { getShellInfo, isDesktopShell, openExternal } from "./shell.js";

/** connector_type -> the sessionStorage key the rest of the app reads it from. */
export const CONNECTOR_TOKEN_KEYS = {
  google_ads: "gads_refresh_token",
  ga4: "ga4_refresh_token",
  gsc: "gsc_refresh_token",
  gtm: "gtm_refresh_token",
};

/**
 * Begin OAuth for one connector.
 *
 * Returns "browser" when the system browser took over — the caller should show
 * a waiting state, because the result arrives later through the deep link — or
 * "redirect" when this window is navigating away, in which case nothing the
 * caller does afterwards runs.
 */
export async function startConnectorOAuth(authorizeUrl) {
  if (isDesktopShell()) {
    const info = await getShellInfo();
    if (info?.capabilities?.browserConnectors) {
      const separator = authorizeUrl.includes("?") ? "&" : "?";
      try {
        await openExternal(`${authorizeUrl}${separator}client=desktop`);
        return "browser";
      } catch {
        // The shell refused to open it — fall through to the in-window
        // navigation rather than leaving the button dead.
      }
    }
  }
  window.location.href = authorizeUrl;
  return "redirect";
}

/**
 * Redeem the one-time code the shell's deep link carried back.
 *
 * The refresh token never travels in that URL — the backend keeps it behind a
 * single-use, 60-second code (`/auth/connectors/exchange`), the same shape as
 * `/auth/exchange` for the sign-in JWT. Resolves to
 * `{ connector_type, refresh_token }`.
 */
export async function exchangeConnectorCode(code) {
  const headers = {};
  const key = backendApiKey();
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(`${BASE}/auth/connectors/exchange?code=${encodeURIComponent(code)}`, {
    headers,
  });
  if (!res.ok) {
    throw new Error(`connector exchange failed (${res.status})`);
  }
  return res.json();
}
