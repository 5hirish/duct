import { withSentryConfig } from "@sentry/nextjs";
import { linguiMacroSwcPlugin } from "@lingui/swc-plugin/options";

// Keep in step with public/_headers and PYODIDE in public/python-worker.js.
const PYODIDE_ORIGIN = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const PYTHON_WORKER_CSP = [
  "default-src 'none'",
  `script-src ${PYODIDE_ORIGIN} 'wasm-unsafe-eval'`,
  `connect-src ${PYODIDE_ORIGIN}`,
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Source maps are 30-40% of dev memory; skip them locally.
  productionBrowserSourceMaps: false,
  experimental: {
    // Smaller initial dev-server footprint on low-RAM machines.
    preloadEntriesOnStart: false,
    serverSourceMaps: false,
    // Expands the Lingui macros (<Trans>, t``, msg``) at compile time, so a
    // message's id is derived from its English text and no key is ever
    // invented by hand. Reads lingui.config.mjs for the locale list.
    swcPlugins: [linguiMacroSwcPlugin()],
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
      // RunPython's worker obeys its own response's policy, not the page's:
      // scripts and connections to one pinned Pyodide release and nowhere
      // else. The same line is in public/_headers, which is what Cloudflare
      // serves static files with; next dev and a Node host read this one.
      {
        source: "/python-worker.js",
        headers: [{ key: "Content-Security-Policy", value: PYTHON_WORKER_CSP }],
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

