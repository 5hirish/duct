/**
 * Polling that stops when nobody is looking.
 *
 * The desktop window is often left open all day behind other apps, and a
 * browser tab sits in the background for hours. A poller that keeps firing
 * there spends battery and wakes the backend (on a self-host build, the
 * sidecar on the same laptop) to refresh a screen no one can see. Each
 * poller here re-checks the moment the page is visible again, so skipping
 * the hidden ticks loses nothing the user could have noticed.
 */

/** True when the page is in a background tab or a minimised/occluded window. */
export function pageHidden() {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

/**
 * Call `tick` every `intervalMs` while the page is visible, and once on
 * becoming visible again. Returns the stop function.
 */
export function pollWhileVisible(tick, intervalMs) {
  if (typeof document === "undefined") return () => {};
  const timer = setInterval(() => {
    if (!pageHidden()) tick();
  }, intervalMs);
  const onVisibility = () => {
    if (!pageHidden()) tick();
  };
  document.addEventListener("visibilitychange", onVisibility);
  return () => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
