/**
 * The desktop shell's one data switch: usage events and crash reports, from
 * the window (`lib/analytics/posthog.js`), the shell itself and, in a
 * self-host build, the bundled backend.
 *
 * Desktop is the only shell where this is a question. On the web the cookie
 * choice decides analytics; on a laptop there is no banner, and the bundled
 * backend runs on the user's own machine, where `local_server.py` blanks
 * `POSTHOG_API_KEY` by default because "a user's laptop is not a deployment".
 *
 * Returns `available: false` where the toggle should not be offered at all —
 * the browser, an older shell without the commands, or a build compiled with
 * no PostHog token, where the switch would be theatre.
 */

import { isDesktopShell } from "./shell.js";

const UNAVAILABLE = { available: false, enabled: false, defaultOn: false };

export async function getTelemetrySettings() {
  if (!isDesktopShell()) return UNAVAILABLE;
  try {
    const info = await window.__TAURI__.core.invoke("get_telemetry_settings");
    return {
      available: Boolean(info?.available),
      enabled: Boolean(info?.enabled),
      // Builds we distribute report by default; a self-host build does not. The
      // card says which, rather than asserting one and being wrong in the other.
      defaultOn: Boolean(info?.default_on),
    };
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
