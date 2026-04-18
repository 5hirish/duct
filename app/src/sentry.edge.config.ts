import * as Sentry from "@sentry/nextjs";

const appEnv = process.env.APP_ENV ?? process.env.NODE_ENV;

if (appEnv !== "local" && process.env.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    environment: appEnv,
    sendDefaultPii: true,
    tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,
    enableLogs: true,
  });
}
