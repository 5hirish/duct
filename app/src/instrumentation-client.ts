import * as Sentry from "@sentry/nextjs";

const appEnv = process.env.NEXT_PUBLIC_APP_ENV ?? process.env.NODE_ENV;

const _SENSITIVE_FIELDS = /token|code|refresh_token|api_key|secret|password|authorization/i;

/**
 * The desktop shell honours the Preferences switch, and this file is the reason
 * it can claim to.
 *
 * Sentry initialises synchronously; the preference lives in a file the Rust side
 * reads over an async command. So events are dropped until that resolves, and
 * dropped forever if it resolves to "off" or fails. Erring toward silence is the
 * only defensible direction: the alternative is reporting for somebody who
 * turned reporting off, which is exactly what the switch promises not to do.
 *
 * In a browser this is inert — `inDesktopShell` is false and nothing changes.
 */
const inDesktopShell =
  typeof window !== "undefined" && Boolean((window as unknown as { __TAURI__?: unknown }).__TAURI__);
let desktopReportingAllowed: boolean | null = null;

if (inDesktopShell) {
  import("./lib/telemetry.js")
    .then(({ getTelemetrySettings }) => getTelemetrySettings())
    .then((settings: { enabled?: boolean }) => {
      desktopReportingAllowed = Boolean(settings?.enabled);
    })
    .catch(() => {
      desktopReportingAllowed = false;
    });
}

function _scrubUrl(u?: string): string | undefined {
  if (!u) return u;
  const idx = u.indexOf("?");
  return idx === -1 ? u : u.slice(0, idx) + "?[Filtered]";
}

// Header, cookie and query names that identify a visitor or their network path.
// `@sentry/core` 10 applied exactly this list under `sendDefaultPii: false`
// (`PII_HEADER_SNIPPETS`); 11 no longer exports it, so it is copied here.
// Matched as case-insensitive substrings.
const PII_KEY_SNIPPETS = ["forwarded", "-ip", "remote-", "via", "-user"];

/**
 * What the browser SDK may collect: Sentry 10's `sendDefaultPii: false`,
 * written out.
 *
 * Sentry 11 replaced that flag with `dataCollection`, and leaving it unset now
 * collects every category — including `userInfo`, which lets Sentry store each
 * visitor's IP (`infer_ip: "auto"`). Sentry is not behind the cookie-consent
 * gate, so that would be new personal data from every web visitor with nobody
 * asked. Headers and query strings keep v10's filter. Cookies and GraphQL are
 * off where v10 filtered or allowed them, as in the SDK's own migration recipe:
 * no integration loaded here reads either, so the stricter value collects
 * the same nothing and cannot start collecting if one is added. Deleting this
 * block is not a cleanup; it turns every category on.
 */
const CLIENT_DATA_COLLECTION = {
  userInfo: false,
  cookies: false,
  httpHeaders: { request: { deny: PII_KEY_SNIPPETS }, response: { deny: PII_KEY_SNIPPETS } },
  httpBodies: [],
  urlQueryParams: { deny: PII_KEY_SNIPPETS },
  graphQL: { document: false, variables: false },
  genAI: { inputs: false, outputs: false },
  databaseQueryData: false,
  queues: false,
} satisfies Sentry.BrowserOptions["dataCollection"];

if (appEnv !== "local" && process.env.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    environment: appEnv,
    dataCollection: CLIENT_DATA_COLLECTION,
    tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.5,
    /**
     * Profiling only happens if all three of these agree, and two of them are
     * not in this file.
     *
     * `profileLifecycle: "trace"` ties a profile to a sampled transaction, so
     * the effective profile rate is `tracesSampleRate x this` — 0.5, not 1.0.
     * The integration below is what actually starts the profiler, and the
     * `Document-Policy: js-profiling` header in `next.config.mjs` is what lets
     * it. Remove any one and the other two go quiet without complaining.
     */
    profileSessionSampleRate: 1.0,
    profileLifecycle: "trace",
    integrations: [
      // Not a default integration — the sample rates above did nothing at all
      // until this was added.
      Sentry.browserProfilingIntegration(),
    ],
    beforeSend(event) {
      // Before anything else: the user may have said no.
      if (inDesktopShell && desktopReportingAllowed !== true) return null;

      if (event.request) {
        // Scrub full URL (query string may contain tokens)
        if (event.request.url) {
          event.request.url = _scrubUrl(event.request.url) as string;
        }
        if (event.request.query_string) {
          event.request.query_string = "[Filtered]";
        }
        if (event.request.headers) {
          for (const key of Object.keys(event.request.headers)) {
            if (_SENSITIVE_FIELDS.test(key)) {
              event.request.headers[key] = "[Filtered]";
            }
          }
        }
        if (event.request.cookies) {
          event.request.cookies = {};  // Record<string, string> — clear all cookies
        }
      }
      // Scrub breadcrumb navigation URLs
      if (event.breadcrumbs) {
        for (const b of event.breadcrumbs) {
          if (b.data && typeof b.data.url === "string") {
            b.data.url = _scrubUrl(b.data.url) as string;
          }
          if (b.data && typeof b.data.to === "string") {
            b.data.to = _scrubUrl(b.data.to) as string;
          }
          if (b.data && typeof b.data.from === "string") {
            b.data.from = _scrubUrl(b.data.from) as string;
          }
        }
      }
      return event;
    },
  });
}

/**
 * A tag reaches errors only. Sentry 11 streams spans, and streamed spans carry
 * attributes, never scope tags, so a key written as a tag alone silently drops
 * out of performance data, which is where desktop and web get compared.
 */
function setShellTag(key: string, value: string) {
  Sentry.setTag(key, value);
  Sentry.setAttribute(key, value);
}

/**
 * Tell Sentry which shell this session is running in.
 *
 * The desktop app loads this same hosted build in a webview, so without this
 * every desktop crash is indistinguishable from a browser one — same release,
 * same URL, no way to tell that the user was on a bundled shell talking to a
 * local sidecar. That matters because the failure modes are different: a
 * desktop session can lose its backend without losing the network, and vice
 * versa.
 *
 * Fire-and-forget: `get_shell_info` is an IPC round-trip, and a session that
 * crashes before it lands is still worth reporting untagged.
 */
async function tagShellContext() {
  if (typeof window === "undefined") return;
  setShellTag("shell", "web");
  const tauri = (window as { __TAURI__?: { core?: { invoke: (cmd: string) => Promise<unknown> } } })
    .__TAURI__;
  if (!tauri?.core?.invoke) return;

  setShellTag("shell", "desktop");
  try {
    const info = (await tauri.core.invoke("get_shell_info")) as {
      version?: string;
      capabilities?: Record<string, boolean>;
    };
    if (info?.version) setShellTag("shell.version", info.version);
    if (info?.capabilities) {
      Sentry.setContext("shell", { version: info.version, ...info.capabilities });
      // Whether requests are going to the bundled backend or the hosted API is
      // the first thing worth knowing when triaging a desktop report.
      setShellTag("shell.localSidecar", String(Boolean(info.capabilities.localSidecar)));
    }
  } catch {
    // An older shell without the command still reports as shell:desktop.
  }
}

if (appEnv !== "local" && process.env.NEXT_PUBLIC_SENTRY_DSN) {
  void tagShellContext();
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
