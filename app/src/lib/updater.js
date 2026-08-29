/**
 * Desktop self-update, driven from the web app.
 *
 * The shell owns the mechanism (`tauri-plugin-updater`); this module owns *when*
 * to ask and what the page does with the answer. It goes through `invoke`
 * rather than `@tauri-apps/plugin-updater` because the window loads a remote
 * origin, which cannot import the plugin's JS bindings — the same constraint
 * that shapes `providerKeys.js`.
 *
 * Gated on the `autoUpdate` capability, never on the shell version: builds
 * without the updater (the Mac App Store variant, where self-update is grounds
 * for rejection) report the flag false and never see the prompt.
 */

import { getShellInfo, isDesktopShell } from "./shell.js";

/** Give the sidecar and the first render the machine to themselves for a moment. */
const INITIAL_DELAY_MS = 20_000;
/** Long-running windows are normal for this app; re-check daily. */
const RECHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
/** Dismissing an update hides it until the next launch, per version. */
const DISMISSED_KEY = "duct_update_dismissed_version";

/**
 * Look for a newer release.
 *
 * Resolves to `{ version, currentVersion, notes, date }` or `null` — including
 * on failure. A missed update check is not something to interrupt anyone about;
 * the next one is a day away at most.
 */
export async function checkForUpdate() {
  if (!isDesktopShell()) return null;
  const shell = await getShellInfo();
  if (!shell?.capabilities?.autoUpdate) return null;
  try {
    return await window.__TAURI__.core.invoke("check_for_update");
  } catch {
    return null;
  }
}

/**
 * Download, install, and relaunch into the new version.
 *
 * Does not resolve on success: the shell replaces the running process. Callers
 * should show progress until either this throws or the window goes away.
 */
export async function installUpdate() {
  await window.__TAURI__.core.invoke("install_update");
}

/** Whether this exact version was already dismissed in this install. */
export function isDismissed(version) {
  try {
    return window.localStorage.getItem(DISMISSED_KEY) === version;
  } catch {
    return false;
  }
}

/** Remember a dismissal so the same version does not nag on every check. */
export function dismiss(version) {
  try {
    window.localStorage.setItem(DISMISSED_KEY, version);
  } catch {
    // Private mode or blocked storage: the prompt reappears next check. Fine.
  }
}

export { INITIAL_DELAY_MS, RECHECK_INTERVAL_MS };
