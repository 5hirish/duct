import * as Sentry from "@sentry/nextjs";

const appEnv = process.env.NEXT_PUBLIC_APP_ENV ?? process.env.NODE_ENV;

const _SENSITIVE_FIELDS = /token|code|refresh_token|api_key|secret|password|authorization/i;

function _scrubUrl(u?: string): string | undefined {
  if (!u) return u;
  const idx = u.indexOf("?");
  return idx === -1 ? u : u.slice(0, idx) + "?[Filtered]";
}

if (appEnv !== "local" && process.env.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    environment: appEnv,
    sendDefaultPii: false,
    tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,
    enableLogs: process.env.NODE_ENV !== "production",
    profileSessionSampleRate: 1.0,
    profileLifecycle: "trace",
    beforeSend(event) {
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
  Sentry.setTag("shell", "web");
  const tauri = (window as { __TAURI__?: { core?: { invoke: (cmd: string) => Promise<unknown> } } })
    .__TAURI__;
  if (!tauri?.core?.invoke) return;

  Sentry.setTag("shell", "desktop");
  try {
    const info = (await tauri.core.invoke("get_shell_info")) as {
      version?: string;
      capabilities?: Record<string, boolean>;
    };
    if (info?.version) Sentry.setTag("shell.version", info.version);
    if (info?.capabilities) {
      Sentry.setContext("shell", { version: info.version, ...info.capabilities });
      // Whether requests are going to the bundled backend or the hosted API is
      // the first thing worth knowing when triaging a desktop report.
      Sentry.setTag("shell.localSidecar", String(Boolean(info.capabilities.localSidecar)));
    }
  } catch {
    // An older shell without the command still reports as shell:desktop.
  }
}

if (appEnv !== "local" && process.env.NEXT_PUBLIC_SENTRY_DSN) {
  void tagShellContext();
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
