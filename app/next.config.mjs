import { withSentryConfig } from "@sentry/nextjs/config";
import { linguiMacroSwcPlugin } from "@lingui/swc-plugin/options";

const DEV = process.env.NODE_ENV === "development";

/**
 * Where a script may come from. Everything bundled (React, Sentry, Mermaid,
 * DOMPurify, Lingui) is 'self'; the app spawns no worker and calls no `eval`.
 * The two remote hosts are the only scripts the app fetches by URL: the tag
 * container, which the web app loads after consent and the desktop shell
 * never loads (`lib/analytics/gtm.js`), and the sign-in page's Turnstile
 * check. A new remote script goes here, because nothing else will let it run.
 * 'unsafe-eval' is dev only: Next's own CSP guidance asks for it there, for
 * HMR and the error overlay, and nothing in a production bundle needs it.
 */
const SCRIPT_SOURCES = [
  "'self'",
  "'unsafe-inline'",
  "https://www.googletagmanager.com",
  "https://challenges.cloudflare.com",
  ...(DEV ? ["'unsafe-eval'"] : []),
];

/**
 * Security headers on every response the worker renders.
 *
 * The session JWT lives in localStorage and the desktop shell lets this origin
 * read keychain-held provider keys, so script injection here is the expensive
 * failure. `script-src` is what answers it: no script from any origin but ours
 * and the two above, and no `eval`.
 *
 * Why 'unsafe-inline' and not a nonce. Every route already renders dynamically
 * (the root layout reads the locale cookie), so a nonce would cost no static
 * page; what rules it out is inheritance. The brief and artifact frames
 * (`InsightsWorkspace`, `ArtifactRenderer`) are `srcDoc` iframes, and an
 * `about:srcdoc` document inherits its parent's policy. They run model-authored
 * HTML whose charts are inline `<script>` by instruction (the insights prompt
 * forbids external assets), and a nonce cannot be handed to a script the model
 * wrote. So inline stays allowed and the policy's work is the origin list,
 * which that inheritance also enforces inside the frames: a model-authored
 * page cannot pull a script from anywhere. Every `srcDoc` iframe (briefs, the
 * audit report, slides) inherits the policy, which is half of why object-src
 * and base-uri are set.
 *
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
    value: [
      `script-src ${SCRIPT_SOURCES.join(" ")}`,
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      `frame-ancestors ${DEV ? "'self'" : "'none'"}`,
    ].join("; "),
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

