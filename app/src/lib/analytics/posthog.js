"use client";

/**
 * PostHog: product analytics, session replay, web vitals and error tracking,
 * and everything that knows PostHog's name.
 *
 * Two modes on one client, because error reports and analytics answer to
 * different rules:
 *
 * - **errors**, for every browser session from the first idle moment: uncaught
 *   errors, error-boundary reports and web vitals, held in memory only. Nothing
 *   is written to the device, so there is nothing for a cookie banner to ask
 *   about. The error tracker this replaced ran on the same terms.
 * - **full**, once measurement is allowed (`ProductAnalytics` decides): page
 *   views, click autocapture, heatmaps and, in a browser, session replay, with
 *   the visitor kept across getduct.ai and app.getduct.ai by a first-party
 *   cookie. Inside the desktop shell it stays in memory and never records a
 *   replay: the shell sets nothing and asks nothing (privacy policy), so its
 *   Preferences switch is the whole consent story there.
 *
 * Safe inside the desktop shell, unlike `gtm`: the shell's IPC trusts every
 * script on this origin, and this provider runs only code bundled from this
 * repository. The `no-external` build never loads a script from PostHog —
 * no remote config scripts, no site apps, no toolbar — which also keeps the
 * CSP's script-src at 'self'.
 *
 * Google's API Limited Use rule forbids humans reading Google user data, and
 * this app shows a customer's GA4, Ads and Search Console numbers. So replays
 * mask every text node and block images, embeds and canvases, and click
 * autocapture keeps the element but not its text: what we watch is the shape
 * of a session, never its data.
 */

import { isDesktopShell } from "../shell.js";
import { beforeSend } from "./scrub.js";

const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY || "";
/** Same-origin reverse proxy (next.config.mjs), so blocklists of PostHog's hosts do not drop events. */
const API_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST || "/ingest";
const UI_HOST = "https://us.posthog.com";

const REPLAY = {
  maskAllInputs: true,
  maskTextSelector: "*",
  blockSelector: "img, iframe, canvas, video, svg image",
};

let client = null;
let loading = null;
let mode = "off"; // "off" | "errors" | "full"
/** Calls made before the library arrived, replayed in order once it does. */
const pending = [];
/** Errors thrown before the library arrived, reported once it does. */
const early = [];
/**
 * Product events from before the consent decision. The sign-up event fires as
 * the OAuth callback lands, usually before the region lookup has answered, and
 * it is the one event the funnel cannot do without. Sent if measurement is
 * allowed, dropped if it is refused.
 */
const undecided = [];
const UNDECIDED_MAX = 50;

function measurableHost() {
  if (typeof window === "undefined") return false;
  const host = window.location?.hostname || "";
  return !(
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "0.0.0.0" ||
    host.endsWith(".local")
  );
}

/** Who and where, on every event: the questions a desktop-only bug asks first. */
async function surfaceProperties() {
  const root = document.documentElement;
  const props = {
    surface: "app",
    shell: isDesktopShell() ? "desktop" : "browser",
    platform: root.dataset.platform || "other",
    locale: root.lang || "en",
    build_id: process.env.NEXT_PUBLIC_BUILD_ID || "dev",
  };
  if (isDesktopShell()) {
    try {
      const info = await window.__TAURI__.core.invoke("get_shell_info");
      if (info?.version) props.shell_version = info.version;
      props.local_sidecar = Boolean(info?.capabilities?.localSidecar);
    } catch {
      // A shell too old for the command still reports as shell: desktop.
    }
  }
  return props;
}

/** What errors mode may send: the failure, the page timing, who it happened to. */
const ERRORS_MODE_EVENTS = new Set(["$exception", "$web_vitals", "$identify"]);

/**
 * The mode is enforced here, at the last step, rather than with PostHog's
 * opt-out: its opt-out marker is written to localStorage, which is storage a
 * refusal must not leave behind, and an extension still running after a
 * downgrade sends nothing either way.
 */
function gate(event) {
  if (!event || mode === "off") return null;
  if (mode === "errors" && !ERRORS_MODE_EVENTS.has(event.event)) return null;
  return beforeSend(event);
}

/** Back to errors mode: what consent enabled stops, and the cookie goes. */
const ERRORS_CONFIG = {
  persistence: "memory",
  capture_pageview: false,
  capture_pageleave: false,
  autocapture: false,
  capture_heatmaps: false,
  capture_dead_clicks: false,
};

function whenLoaded(fn) {
  if (client) fn(client);
  else pending.push(fn);
}

function captureEarly(event) {
  const error = event?.reason ?? event?.error;
  if (error) early.push(error);
}

/** Catch what throws before the library loads; it is reported once it does. */
function listenEarly() {
  window.addEventListener("error", captureEarly);
  window.addEventListener("unhandledrejection", captureEarly);
}

function stopListeningEarly() {
  window.removeEventListener("error", captureEarly);
  window.removeEventListener("unhandledrejection", captureEarly);
}

function load() {
  if (loading) return loading;
  loading = Promise.all([
    import("posthog-js/dist/module.no-external"),
    import("posthog-js/dist/exception-autocapture"),
    import("posthog-js/dist/web-vitals"),
    surfaceProperties(),
  ]).then(([{ default: posthog }, , , props]) => {
    if (mode === "off") {
      // Switched off while loading: let a later switch-on load it afresh.
      loading = null;
      return null;
    }
    posthog.init(KEY, {
      ...ERRORS_CONFIG,
      api_host: API_HOST,
      ui_host: UI_HOST,
      person_profiles: "identified_only",
      disable_session_recording: true,
      session_recording: REPLAY,
      enable_recording_console_log: false,
      mask_all_text: true,
      capture_exceptions: true,
      capture_performance: { web_vitals: true, network_timing: false },
      disable_external_dependency_loading: true,
      disable_surveys: true,
      disable_product_tours: true,
      disable_conversations: true,
      disable_web_experiments: true,
      // Flags off, remote config on: replay cannot start without the
      // project's recording settings, and those arrive as remote config.
      advanced_disable_feature_flags: true,
      opt_in_site_apps: false,
      before_send: gate,
    });
    posthog.register(props);
    client = posthog;
    stopListeningEarly();
    for (const error of early.splice(0)) posthog.captureException(error);
    for (const fn of pending.splice(0)) fn(posthog);
    return posthog;
  });
  return loading;
}

function idle(fn) {
  if ("requestIdleCallback" in window) window.requestIdleCallback(fn, { timeout: 4000 });
  else window.setTimeout(fn, 2000);
}

async function desktopReportingAllowed() {
  const { getTelemetrySettings } = await import("../telemetry.js");
  const settings = await getTelemetrySettings();
  return Boolean(settings.enabled);
}

export const posthog = {
  id: "posthog",

  isConfigured() {
    return Boolean(KEY) && measurableHost();
  },

  /**
   * Error reports and web vitals, before and regardless of any cookie choice
   * in a browser; behind the Preferences switch in the desktop shell, where
   * nothing at all is sent while it is off.
   */
  startErrorReporting() {
    if (mode !== "off" || !this.isConfigured()) return;
    mode = "errors";
    listenEarly();
    const begin = () => idle(() => load());
    if (!isDesktopShell()) {
      begin();
      return;
    }
    desktopReportingAllowed().then((allowed) => {
      if (allowed) begin();
      else {
        mode = "off";
        stopListeningEarly();
        early.length = 0;
      }
    });
  },

  setDefaults() {},

  setConsent(granted) {
    if (granted) return;
    undecided.length = 0;
    // In a browser a refusal is of the cookie and what it enables; error
    // reports store nothing and carry on. In the shell the Preferences switch
    // is about anything leaving at all, so off means off.
    if (isDesktopShell()) mode = "off";
    else if (mode === "full") mode = "errors";
    whenLoaded((ph) => {
      ph.stopSessionRecording();
      ph.set_config(ERRORS_CONFIG);
    });
  },

  forgetStoredData() {
    const host = window.location?.hostname || "";
    const labels = host.split(".");
    const registrable = labels.length >= 2 ? `.${labels.slice(-2).join(".")}` : "";
    const domains = ["", host, `.${host}`, registrable].filter((d, i, all) => all.indexOf(d) === i);
    for (const entry of document.cookie ? document.cookie.split(";") : []) {
      const name = entry.split("=")[0].trim();
      if (!name.startsWith("ph_")) continue;
      for (const domain of domains) {
        document.cookie =
          `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/` + (domain ? `; domain=${domain}` : "");
      }
    }
    try {
      for (const key of Object.keys(window.localStorage)) {
        if (key.startsWith("ph_")) window.localStorage.removeItem(key);
      }
    } catch {
      /* storage disabled: nothing was stored */
    }
  },

  /**
   * From errors to full. In a browser that means a first-party cookie, page
   * views, clicks, heatmaps and replay; in the shell everything but replay,
   * and still nothing on disk.
   */
  start() {
    if (mode === "full" || !this.isConfigured()) return;
    if (mode === "off") this.startErrorReporting();
    mode = "full";
    const desktop = isDesktopShell();
    // `posthog-recorder`, not `recorder`: the session-recording code itself
    // ships in this bundle, and the plain rrweb one leaves the SDK reaching
    // for a script it is not allowed to fetch, which fails without a word.
    const recorder = desktop ? Promise.resolve() : import("posthog-js/dist/posthog-recorder");
    Promise.all([load(), recorder]).then(([ph]) => {
      if (!ph || mode !== "full") return;
      ph.set_config({
        persistence: desktop ? "memory" : "localStorage+cookie",
        cross_subdomain_cookie: true,
        capture_pageview: "history_change",
        capture_pageleave: true,
        autocapture: true,
        capture_heatmaps: !desktop,
        capture_dead_clicks: true,
      });
      // Registered again: the properties lived in the memory store this replaced.
      surfaceProperties().then((props) => ph.register(props));
      // history_change counts the next navigation; this one already happened.
      ph.capture("$pageview");
      for (const [event, params] of undecided.splice(0)) ph.capture(event, params);
      if (!desktop) ph.startSessionRecording();
    });
  },

  isRunning() {
    return mode === "full";
  },

  track(event, params = {}) {
    if (mode === "full") whenLoaded((ph) => ph.capture(event, params));
    else if (this.isConfigured() && undecided.length < UNDECIDED_MAX) undecided.push([event, params]);
  },

  /** The account UUID from the JWT's `uid`, the same distinct id the backend uses. */
  identify(userId, properties = {}) {
    if (!userId || mode === "off") return;
    whenLoaded((ph) => ph.identify(userId, properties));
  },

  reset() {
    whenLoaded((ph) => ph.reset());
  },

  captureException(error, properties = {}) {
    if (mode === "off") return;
    if (client) client.captureException(error, properties);
    else early.push(error);
  },
};
