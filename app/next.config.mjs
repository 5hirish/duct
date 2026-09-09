import { withSentryConfig } from "@sentry/nextjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Source maps are 30-40% of dev memory; skip them locally.
  productionBrowserSourceMaps: false,
  experimental: {
    // Smaller initial dev-server footprint on low-RAM machines.
    preloadEntriesOnStart: false,
    serverSourceMaps: false,
  },
  /**
   * Browser profiling is granted per document, not per SDK.
   *
   * Chrome's JS Self-Profiling API refuses to start unless the response that
   * delivered the page carried this header, and it refuses *silently*:
   * `browserProfilingIntegration` initialises, logs nothing, and produces zero
   * profiles. That is precisely how this sat for months — the sample rates were
   * in `instrumentation-client.ts` the whole time with nothing on the wire.
   *
   * Scoped to documents rather than `/:path*` because the policy only means
   * anything on an HTML response; sending it on every asset is noise on a
   * header Cloudflare charges us bytes for.
   */
  async headers() {
    return [
      {
        source: "/:path*",
        missing: [{ type: "header", key: "next-router-prefetch" }],
        headers: [{ key: "Document-Policy", value: "js-profiling" }],
      },
    ];
  },
};

// Skip the Sentry build plugin in dev — it only matters for prod releases.
export default process.env.NODE_ENV === "development"
  ? nextConfig
  : withSentryConfig(nextConfig, {
      org: "alleviate-lab",
      project: "app-duct",
      silent: !process.env.CI,
    });

