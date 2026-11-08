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
 *
 * Nothing here ever holds a provider token. The connect starts from a link
 * naming the signed-in user, the provider's grant is parked on the server, and
 * the Connections page claims it with the same session (issue #456). What
 * comes back to this app, in the browser or through the shell, is a code.
 */

import { BASE } from "./api.js";
import { startConnectLink } from "./connectorsApi.js";
import { getShellInfo, isDesktopShell, openExternal } from "./shell.js";

/**
 * Where the connect should land once the grant is claimed, and which connector
 * just arrived. Both the browser flow (a redirect to
 * /connections?connector=&auth_code=) and the desktop flow (a deep link the
 * shell turns into the same URL) end on the Connections page, which
 * is the wrong place when the connect was asked for mid-conversation: the
 * user was answering the agent, and came back to a settings screen with the
 * agent's question a navigation away. So the page that started the connect
 * parks where to return, and the Connections page — the one place every flow
 * passes through — sends them back and flags which connector it adopted, so
 * the pause card that asked can answer itself.
 *
 * Session storage, same-origin paths only: the return is a UI convenience,
 * never an auth decision.
 */
const CONNECTOR_RETURN_KEY = "duct_connector_return";
const CONNECTOR_CONNECTED_KEY = "duct_connector_connected";

function samePath(path) {
  return typeof path === "string" && path.startsWith("/") && !path.startsWith("//");
}

/** The path parked by the page that started the last connect, consumed once. */
export function consumeConnectorReturn() {
  try {
    const path = sessionStorage.getItem(CONNECTOR_RETURN_KEY) || "";
    sessionStorage.removeItem(CONNECTOR_RETURN_KEY);
    return samePath(path) ? path : "";
  } catch {
    return "";
  }
}

/** Record that `connectorType` just came home, for the card that asked. */
export function markConnectorConnected(connectorType) {
  try {
    sessionStorage.setItem(CONNECTOR_CONNECTED_KEY, connectorType);
  } catch {
    /* the card keeps its manual "I've connected it" button */
  }
}

/** True once, if `connectorType` is the connector that just came home. */
export function consumeConnectorConnected(connectorType) {
  try {
    if (sessionStorage.getItem(CONNECTOR_CONNECTED_KEY) !== connectorType) return false;
    sessionStorage.removeItem(CONNECTOR_CONNECTED_KEY);
    return true;
  } catch {
    return false;
  }
}

/**
 * Begin OAuth for one connector (`google_ads`, `ga4`, `gsc`, `gtm`, `github`).
 *
 * Mints the single-use link naming this session's user first: the authorize
 * route is a bare navigation with no bearer token, and refuses to start
 * without one. A dead session therefore fails here, before Google, rather
 * than after the user has approved access nobody can claim — so this rejects
 * when the link cannot be minted, and the caller resets its button.
 *
 * Resolves to "browser" when the system browser took over — the caller should
 * show a waiting state, because the result arrives later through the deep
 * link — or "redirect" when this window is navigating away, in which case
 * nothing the caller does afterwards runs.
 *
 * `returnTo` is where the Connections page should send the user once the
 * grant is claimed; omit it to stay on the Connections page.
 */
export async function startConnectorOAuth(connectorType, { returnTo = "" } = {}) {
  const link = await startConnectLink(connectorType);
  const authorizeUrl =
    `${BASE}/auth/connectors/${encodeURIComponent(connectorType)}/oauth/authorize` +
    `?link=${encodeURIComponent(link)}`;
  try {
    if (samePath(returnTo)) sessionStorage.setItem(CONNECTOR_RETURN_KEY, returnTo);
    else sessionStorage.removeItem(CONNECTOR_RETURN_KEY);
  } catch {
    /* they land on the Connections page instead */
  }
  if (await usesSystemBrowser()) {
    try {
      await openExternal(`${authorizeUrl}&client=desktop`);
      return "browser";
    } catch {
      // The shell refused to open it — fall through to the in-window
      // navigation rather than leaving the button dead.
    }
  }
  window.location.href = authorizeUrl;
  return "redirect";
}

/** True when a sign-in belongs in the system browser: a desktop shell new
 *  enough to have the deep link that brings the result back. */
export async function usesSystemBrowser() {
  if (!isDesktopShell()) return false;
  const info = await getShellInfo();
  return Boolean(info?.capabilities?.browserConnectors);
}

/**
 * Send the person to a vendor's own sign-in page, for a flow whose return
 * address was fixed before this URL existed (an MCP server's authorize URL
 * names its callback inside it, so nothing can be appended here the way
 * `startConnectorOAuth` appends `client=desktop`). Same answers: "browser"
 * when the shell's system browser took it, "redirect" when this window left.
 *
 * No in-window fallback on the shell: that sign-in was promised to the
 * desktop relay page, and opening it inside the webview would land the relay
 * in the very window it exists to hand back to. Failing says so instead.
 */
export async function openVendorSignIn(authorizeUrl, { systemBrowser = false } = {}) {
  if (systemBrowser) {
    await openExternal(authorizeUrl);
    return "browser";
  }
  window.location.href = authorizeUrl;
  return "redirect";
}
