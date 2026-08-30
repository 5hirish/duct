/**
 * Duct desktop shell (Tauri) detection and invoke helpers.
 *
 * The shell exposes commands on `window.__TAURI__.core.invoke` (same channel
 * as `providerKeys.js`). Anything shell-dependent must be gated on
 * `getShellInfo()` capabilities — not on shell version, and never on
 * `isDesktopShell()` alone — so that older installed shells (which predate a
 * given command) gracefully keep the plain web behaviour.
 */

export function isDesktopShell() {
  return typeof window !== "undefined" && Boolean(window.__TAURI__);
}

/**
 * Shell version + feature flags, e.g. { version, capabilities: { browserAuth } }.
 * Returns null in browsers and in shells too old to have the command.
 */
export async function getShellInfo() {
  if (!isDesktopShell()) return null;
  try {
    return await window.__TAURI__.core.invoke("get_shell_info");
  } catch {
    return null;
  }
}

/** Open an http(s) URL in the system's default browser (shell-validated). */
export async function openExternal(url) {
  await window.__TAURI__.core.invoke("open_external", { url });
}

/**
 * Make `target="_blank"` links work inside the desktop shell.
 *
 * The webview has no tabs and no window-opening behaviour, so a new-tab link is
 * simply *dead* there: nothing happens, with no error. That silently strands
 * every "go set this up in your provider's console" link — which is most of how
 * a manual connector gets connected, and the same journey the OAuth connectors
 * now take through the system browser.
 *
 * Deliberately narrow: only anchors that already asked for a new tab. A link
 * that meant to navigate this window still does, because rerouting those would
 * change navigation the app relies on.
 *
 * Returns a cleanup function; a no-op outside the shell.
 */
export function installExternalLinkHandler() {
  if (!isDesktopShell() || typeof document === "undefined") return () => {};

  const onClick = (event) => {
    if (event.defaultPrevented || event.button !== 0) return;
    // Let the OS-level modifiers keep whatever the webview does with them.
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target?.closest?.('a[href][target="_blank"]');
    if (!anchor) return;
    let url;
    try {
      url = new URL(anchor.getAttribute("href"), window.location.href);
    } catch {
      return;
    }
    // `open_external` rejects anything else anyway; bail before preventDefault
    // so a scheme we don't handle keeps its default behaviour.
    if (url.protocol !== "http:" && url.protocol !== "https:") return;
    event.preventDefault();
    openExternal(url.href).catch(() => {});
  };

  document.addEventListener("click", onClick);
  return () => document.removeEventListener("click", onClick);
}
