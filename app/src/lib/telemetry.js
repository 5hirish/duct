/**
 * The desktop crash-reporting opt-in.
 *
 * Desktop is the only shell where this is a question. On the web the app is
 * served by us and already reports; on a laptop the bundled backend is running
 * on the user's own machine, and `local_server.py` blanks `SENTRY_DSN` by
 * default precisely because "a user's laptop is not a deployment". This is the
 * switch that lets someone opt into helping, rather than being opted in.
 *
 * Returns `available: false` where the toggle should not be offered at all —
 * the browser, an older shell without the commands, or a build compiled with no
 * DSN, where the switch would be theatre.
 */

import { isDesktopShell } from "./shell.js";

const UNAVAILABLE = { available: false, enabled: false };

export async function getTelemetrySettings() {
  if (!isDesktopShell()) return UNAVAILABLE;
  try {
    const info = await window.__TAURI__.core.invoke("get_telemetry_settings");
    return { available: Boolean(info?.available), enabled: Boolean(info?.enabled) };
  } catch {
    // A shell predating these commands. Absence of the switch is the honest
    // answer; it cannot report either way.
    return UNAVAILABLE;
  }
}

/**
 * Record the choice.
 *
 * Throws on failure — this writes a consent decision, and a silent no-op would
 * leave someone believing they had turned reporting off when they had not.
 */
export async function setTelemetryEnabled(enabled) {
  await window.__TAURI__.core.invoke("set_telemetry_enabled", { enabled });
}
