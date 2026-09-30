import { withSentryConfig } from "@sentry/nextjs/config";
import { linguiMacroSwcPlugin } from "@lingui/swc-plugin/options";

const DEV = process.env.NODE_ENV === "development";

/**
 * Security headers on every response the worker renders.
 *
 * The session JWT lives in localStorage and the desktop shell lets this origin
 * read keychain-held provider keys, so script injection here is the expensive
 * failure. This set is the part that cannot break a page. The part that would
 * stop injection, a script-src, is not here: App Router hydrates with inline
 * scripts, so a strict policy needs a per-request nonce from middleware, and a
 * nonce makes every page render dynamically. That is its own change.
 *
 * Before tightening it, know that every srcDoc iframe (briefs, the audit
 * report, slides) inherits this policy, so a directive added here also governs
 * model-authored HTML. That is half of why object-src and base-uri are set.
 * `/_next/static` and `public/` never reach the worker (Workers Static Assets
 * serves them), so `public/_headers` carries their nosniff instead.
 */
const SECURITY_HEADERS = [
  // HSTS is per host, not per port, and outlives the header. Browsers ignore it
  // over http, but a dev server run over https would pin every localhost port
  // to https for a year, the API and the site included.
  ...(DEV ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000" }]),
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=(), display-capture=()",
  },
  // `/preview` frames `/preview/frame` on this origin and exists only in dev
  // (it 404s in a build). Nothing frames the app in production; the desktop
  // shell loads it as a top-level window.
  { key: "X-Frame-Options", value: DEV ? "SAMEORIGIN" : "DENY" },
  {
    key: "Content-Security-Policy",
    value: `object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors ${DEV ? "'self'" : "'none'"}`,
  },
];

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
      { source: "/:path*", headers: SECURITY_HEADERS },
      {
        source: "/:path*",
        missing: [{ type: "header", key: "next-router-prefetch" }],
        headers: [{ key: "Document-Policy", value: "js-profiling" }],
      },
    ];
  },
};

// Skip the Sentry build plugin in dev — it only matters for prod releases.
export default DEV
  ? nextConfig
  : withSentryConfig(nextConfig, {
      org: "alleviate-lab",
      project: "app-duct",
      silent: !process.env.CI,
    });

