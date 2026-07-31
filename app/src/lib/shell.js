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
