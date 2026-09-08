"use client";

/**
 * Google Tag Manager, and everything that knows Google's name.
 *
 * GA4 and every other tag are configured in the container, not here — this
 * loads the container, declares the storage posture Consent Mode reads, and
 * pushes events onto `dataLayer`.
 *
 * Configured by `NEXT_PUBLIC_GTM_ID`. Absent means unconfigured, which the seam
 * treats as "no analytics" rather than an error.
 */

const GRANTED = "granted";
const DENIED = "denied";

/** What the container's tags write, so a withdrawal can remove it. */
const COOKIE_PREFIXES = ["_ga", "_gid", "_gcl", "_gac"];

let running = false;

function gtag() {
  window.dataLayer = window.dataLayer || [];
  // GTM reads the `arguments` object itself; a spread array is not equivalent.
  // eslint-disable-next-line prefer-rest-params
  window.dataLayer.push(arguments);
}

function containerId() {
  return process.env.NEXT_PUBLIC_GTM_ID || "";
}

/** True except on the hosts where a tag would measure a developer, not a user. */
function isMeasurableHost() {
  if (typeof window === "undefined") return false;
  const host = window.location?.hostname || "";
  return !(
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "0.0.0.0" ||
    host.endsWith(".local")
  );
}

export const gtm = {
  id: "gtm",

  isConfigured() {
    return Boolean(containerId()) && isMeasurableHost();
  },

  /**
   * The posture before any decision, declared before `gtm.js` parses — a
   * Consent Initialization tag inside the container cannot beat the container's
   * own loader.
   *
   * `cookieless` is the desktop shell's permanent state: tags fire, GA4 sends
   * cookieless pings, nothing is written to the machine. No `wait_for_update`
   * there, because no update is coming and waiting would delay every event.
   */
  setDefaults({ cookieless = false } = {}) {
    gtag("consent", "default", {
      ad_storage: DENIED,
      ad_user_data: DENIED,
      ad_personalization: DENIED,
      analytics_storage: DENIED,
      functionality_storage: GRANTED,
      security_storage: GRANTED,
      ...(cookieless ? {} : { wait_for_update: 500 }),
    });
  },

  setConsent(granted) {
    const state = granted ? GRANTED : DENIED;
    gtag("consent", "update", {
      ad_storage: state,
      ad_user_data: state,
      ad_personalization: state,
      analytics_storage: state,
    });
  },

  forgetStoredData() {
    const host = window.location?.hostname || "";
    const bare = host.replace(/^www\./, "");
    const domains = ["", host, `.${host}`, ...(bare === host ? [] : [bare, `.${bare}`])];

    for (const entry of document.cookie ? document.cookie.split(";") : []) {
      const name = entry.split("=")[0].trim();
      if (!COOKIE_PREFIXES.some((prefix) => name.startsWith(prefix))) continue;
      for (const domain of domains) {
        document.cookie =
          `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/` +
          (domain ? `; domain=${domain}` : "");
      }
    }
  },

  start({ deferred = false } = {}) {
    if (running || !this.isConfigured()) return;
    if (!deferred) {
      load();
      return;
    }
    // The deferral is a performance win and was never the consent story, so it
    // happens after the decision rather than instead of it.
    for (const evt of ["pointerdown", "keydown", "scroll", "touchstart"]) {
      window.addEventListener(evt, load, { once: true, passive: true });
    }
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(load, { timeout: 3000 });
    } else {
      window.setTimeout(load, 3000);
    }
  },

  isRunning() {
    return running;
  },

  track(event, params = {}) {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ event, ...params });
  },

  /**
   * Name the person behind the events, so the same human on the desktop app and
   * in a browser is one user rather than two — which is the difference between
   * an activation rate that means something and one that does not.
   *
   * `userId` is the account UUID from the JWT's `uid`, never the email: `sub`
   * is an email address and GA4 must not receive personal data.
   *
   * The GA4 configuration tag reads `user_id` off the dataLayer, so this is a
   * plain variable push rather than an event.
   */
  identify(userId, properties = {}) {
    if (!userId) return;
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ user_id: userId, user_properties: properties });
  },

  /**
   * Forget them on sign-out.
   *
   * dataLayer variables persist for the life of the page, so without this the
   * previous user's id rides every hit afterwards — and on a shared machine it
   * attributes one person's session to another. Undefined rather than deleted,
   * because a push is the only way to change what is already in there.
   */
  reset() {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ user_id: undefined, user_properties: {} });
  },
};

function load() {
  if (running || !gtm.isConfigured()) return;
  running = true;

  const d = document;
  const tag = "script";
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
  const first = d.getElementsByTagName(tag)[0];
  const j = d.createElement(tag);
  j.async = true;
  j.src = `https://www.googletagmanager.com/gtm.js?id=${containerId()}`;
  first.parentNode.insertBefore(j, first);
}
