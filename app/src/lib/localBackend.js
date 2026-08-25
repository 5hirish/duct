/**
 * Point the app at the desktop shell's bundled backend ("sidecar").
 *
 * On the web this is a no-op and the app keeps talking to the hosted API. In
 * the desktop shell the backend runs on this machine on a loopback port the OS
 * picked at launch, so the base URL cannot be known at build time the way
 * `NEXT_PUBLIC_API_BASE` is — it has to be read from the shell at boot.
 *
 * Gated on the `localSidecar` capability, never on the shell version: shells
 * built before the sidecar existed report no flag and correctly keep using the
 * hosted API. See `desktop/src-tauri/src/sidecar.rs` for the other end.
 */

import { useLocalBackend } from "./api.js";
import { getShellInfo, isDesktopShell } from "./shell.js";

/** A frozen Python app takes ~20s to boot on first run; allow generous headroom. */
const BOOT_TIMEOUT_MS = 90_000;
const POLL_INTERVAL_MS = 250;

/** Resolved once per page load — every caller awaits the same promise. */
let pending = null;
/** Last resolved result, for synchronous reads after the gate has run. */
let resolved = null;

/**
 * Whether requests are going to a local sidecar rather than the hosted API.
 *
 * Synchronous, so it can be read during render. Only meaningful *after*
 * `initLocalBackend()` has settled — `LocalBackendGate` guarantees that for
 * everything it wraps, which is why this is safe to call from a page inside it.
 */
export function isLocalBackendActive() {
  return Boolean(resolved?.active);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Resolve which backend to use, repointing the API layer when it is local.
 *
 * Resolves to `{ active, url?, error? }`. `active: false` means the hosted API
 * is in use (plain browser, or a shell without the capability). It never
 * rejects — a sidecar that fails to start should surface as a message in the
 * UI, not an unhandled rejection during boot.
 */
export function initLocalBackend() {
  if (!pending) pending = resolve().then((result) => (resolved = result));
  return pending;
}

async function resolve() {
  if (!isDesktopShell()) return { active: false };

  const shell = await getShellInfo();
  if (!shell?.capabilities?.localSidecar) return { active: false };

  const deadline = Date.now() + BOOT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    let info;
    try {
      info = await window.__TAURI__.core.invoke("get_sidecar_info");
    } catch (err) {
      // The shell reports startup failures as a command error, and they are
      // terminal — retrying cannot fix a missing or crashed binary.
      return { active: false, error: String(err) };
    }
    if (info?.url) {
      useLocalBackend({ url: info.url, apiKey: info.api_key });
      return { active: true, url: info.url, dataDir: info.data_dir };
    }
    await sleep(POLL_INTERVAL_MS);
  }

  return {
    active: false,
    error: `local backend did not start within ${Math.round(BOOT_TIMEOUT_MS / 1000)}s`,
  };
}
