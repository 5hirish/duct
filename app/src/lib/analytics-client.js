"use client";

/**
 * Google Tag Manager only. GA4 and other tags are configured in the GTM container
 * (same pattern as site/assets/duct.js: deferred load).
 *
 * Optional env: NEXT_PUBLIC_GTM_ID (e.g. GTM-PKL589SW). Omit in dev/staging if unused.
 */

/** Deferred GTM load after first interaction or idle (matches marketing site). */
export function bootGtmDeferred(gtmId) {
  if (typeof window === "undefined" || !gtmId) return;

  const w = window;
  const d = document;
  const tag = "script";
  const dlName = "dataLayer";
  let loaded = false;

  function loadGtm() {
    if (loaded) return;
    loaded = true;
    w[dlName] = w[dlName] || [];
    w[dlName].push({ "gtm.start": Date.now(), event: "gtm.js" });
    const first = d.getElementsByTagName(tag)[0];
    const j = d.createElement(tag);
    const dlParam = dlName !== "dataLayer" ? `&l=${dlName}` : "";
    j.async = true;
    j.src = `https://www.googletagmanager.com/gtm.js?id=${gtmId}${dlParam}`;
    first.parentNode.insertBefore(j, first);
  }

  for (const evt of ["pointerdown", "keydown", "scroll", "touchstart"]) {
    w.addEventListener(evt, loadGtm, { once: true, passive: true });
  }

  if ("requestIdleCallback" in w) {
    w.requestIdleCallback(loadGtm, { timeout: 3000 });
  } else {
    w.setTimeout(loadGtm, 3000);
  }
}
