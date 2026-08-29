/**
 * Is the app actually able to reach its backend, and if not, why.
 *
 * Three failures look identical to a component that just sees a rejected
 * fetch, and they need three different things from the user:
 *
 *   offline    the device has no network. Nothing will work; wait or reconnect.
 *   unreachable the network is up but the API is not answering — the hosted API
 *              is down, or on desktop the local sidecar died after boot.
 *   ok         reachable.
 *
 * Deliberately a poller against `/health` rather than a wrapper around every
 * `fetch` in `api.js`. Those call sites number in the dozens and several are
 * SSE streams with their own lifecycles; threading a status through all of them
 * would be a far larger change than the problem justifies, and would still miss
 * the case this actually catches — the backend going away while the user is
 * idle, with no request in flight to notice it.
 *
 * `navigator.onLine` is only trusted for the *negative*: false reliably means
 * no network, true means "an interface is up", which is not the same as having
 * a working connection.
 */

import { BASE, backendApiKey } from "./api.js";

export const STATUS = {
  OK: "ok",
  OFFLINE: "offline",
  UNREACHABLE: "unreachable",
};

/** Slow enough not to be chatty; fast enough that a banner is not stale news. */
const POLL_INTERVAL_MS = 30_000;
/** A health check that hangs is a failure — don't let it pin the state at "ok". */
const PROBE_TIMEOUT_MS = 8_000;

/**
 * One health check. Resolves to a STATUS; never rejects.
 *
 * A non-2xx answer still counts as reachable: the server responded, so this is
 * an application problem for the caller to surface, not a connectivity one.
 */
export async function probe({ signal } = {}) {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return STATUS.OFFLINE;
  }
  if (!BASE) return STATUS.UNREACHABLE;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  const onOuterAbort = () => controller.abort();
  signal?.addEventListener("abort", onOuterAbort);

  try {
    const key = backendApiKey();
    await fetch(`${BASE}/health`, {
      signal: controller.signal,
      headers: key ? { "X-API-Key": key } : {},
      cache: "no-store",
    });
    return STATUS.OK;
  } catch {
    // Distinguish "we gave up" from "the browser knows there's no network".
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      return STATUS.OFFLINE;
    }
    return STATUS.UNREACHABLE;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onOuterAbort);
  }
}

/**
 * Watch connection status, calling `onChange` only when it actually changes.
 *
 * Returns an unsubscribe function. Polls on an interval, and probes immediately
 * on the browser's `online` event so recovery is noticed at once rather than up
 * to a poll interval later.
 */
export function watchConnection(onChange) {
  if (typeof window === "undefined") return () => {};

  let current = STATUS.OK;
  let stopped = false;
  const controller = new AbortController();

  const check = async () => {
    if (stopped) return;
    const next = await probe({ signal: controller.signal });
    if (stopped || next === current) return;
    current = next;
    onChange(next);
  };

  const onOffline = () => {
    if (current === STATUS.OFFLINE) return;
    current = STATUS.OFFLINE;
    onChange(STATUS.OFFLINE);
  };

  window.addEventListener("offline", onOffline);
  window.addEventListener("online", check);
  const interval = setInterval(check, POLL_INTERVAL_MS);
  check();

  return () => {
    stopped = true;
    controller.abort();
    clearInterval(interval);
    clearTimeout(interval);
    window.removeEventListener("offline", onOffline);
    window.removeEventListener("online", check);
  };
}

export { POLL_INTERVAL_MS };
