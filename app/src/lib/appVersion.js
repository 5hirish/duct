// "A new version of Duct is available" — for the web app, where there is no
// installer to run and the fix is a reload.
//
// The problem this solves is specific to how the app is deployed. Sessions here
// are long: someone opens an agent workspace, leaves the tab for a day, and
// comes back to a page whose JavaScript is from last week. Meanwhile the deploy
// on merge to main has replaced the worker. The stale tab keeps working until
// it asks for a chunk that no longer exists, and then it fails in a way that
// looks like a bug rather than like an old tab.
//
// So: compare the build this tab loaded against the build currently deployed,
// and if they differ, say so and offer a reload. Never reload for them —
// see RELOAD IS THE USER'S below.

const BUILD_HEADER = "x-duct-build";

/**
 * The build this tab is running, baked in at `next build` time.
 *
 * Read as a whole `process.env.X` expression, never destructured or computed:
 * Next inlines these at build by textual substitution, so `process.env[name]`
 * silently becomes undefined in the browser bundle.
 *
 * Empty in local dev and in any build that did not set it, which is the signal
 * to disable the check entirely — see `versionCheckAvailable`.
 */
export const BUILD_ID = process.env.NEXT_PUBLIC_BUILD_ID || "";

/** How often to ask, while the tab is visible. */
export const POLL_INTERVAL_MS = 15 * 60 * 1000;

/**
 * Wait before the first check. A tab that has just loaded is by definition on
 * the build it just fetched, and the first paint has better things to do.
 */
export const INITIAL_DELAY_MS = 60 * 1000;

const DISMISS_KEY = "duct_reload_dismissed_build";

/**
 * Whether this build can detect a new one.
 *
 * Without a baked id every comparison would be `"" !== "abc"` and the notice
 * would show permanently on the first check — worse than not having it. Dev
 * runs on `next dev`, which never bakes one, so the check is simply off there.
 */
export function versionCheckAvailable() {
  return Boolean(BUILD_ID);
}

/**
 * The build currently deployed, or "" when it cannot be determined.
 *
 * Never throws: this runs on a timer behind the user's real work, and a failed
 * poll (offline, a worker cold start, a 500) must be indistinguishable from
 * "no new version" — an error toast about a *version check* would be a strictly
 * worse interruption than the staleness it is reporting on.
 */
export async function fetchDeployedBuild(fetchImpl = fetch) {
  try {
    const res = await fetchImpl("/api/version", {
      // Both are needed and they are not the same instruction: `cache` governs
      // this fetch, the header governs the CDN in front of it. A cached 200 is
      // exactly the failure mode that makes this check silently useless.
      cache: "no-store",
      headers: { "cache-control": "no-cache" },
    });
    if (!res?.ok) return "";
    // The header is the cheap path; the body is the readable one. Either is
    // authoritative, so a proxy that strips unknown headers does not break it.
    const header = res.headers?.get?.(BUILD_HEADER);
    if (header) return header;
    const body = await res.json();
    return typeof body?.build === "string" ? body.build : "";
  } catch {
    return "";
  }
}

/**
 * Is `deployed` a different build from the one we are running?
 *
 * An empty `deployed` is "we could not tell", never "it changed" — the whole
 * failure surface of this feature is false positives, and a notice that asks
 * someone to reload for no reason teaches them to ignore the one that matters.
 */
export function isStale(deployed, current = BUILD_ID) {
  if (!current || !deployed) return false;
  return deployed !== current;
}

/**
 * Dismissal is per build, not a boolean.
 *
 * "Not now" means "not for this version". The next deploy asks again, because
 * by then it is a different question — and a permanent dismissal would leave a
 * tab silently stale forever, which is the bug this feature exists to fix.
 */
export function isDismissed(build) {
  if (!build) return false;
  try {
    return window.localStorage.getItem(DISMISS_KEY) === build;
  } catch {
    // Private mode or blocked storage: showing the notice again is the safe
    // side of this failure.
    return false;
  }
}

export function dismiss(build) {
  try {
    window.localStorage.setItem(DISMISS_KEY, build);
  } catch {
    /* nothing to do — the notice reappears next check, which is harmless */
  }
}

/**
 * RELOAD IS THE USER'S.
 *
 * Never call this on a timer or on detection. This app holds long agent runs
 * and unsent chat input; a reload the user did not ask for loses both, and the
 * cost lands on exactly the people who use the product most. The notice waits
 * in the corner for as long as it takes.
 */
export function reload() {
  window.location.reload();
}
