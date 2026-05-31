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
          event.request.cookies = "[Filtered]";
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

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
