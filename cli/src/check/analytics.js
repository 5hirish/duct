// Which analytics tags a page loads, from its script URLs, its inline
// scripts and the first-party scripts it pulls in. The patterns are the
// checklist's ("Patterns to search for"), grouped by vendor.

export const VENDORS = [
  { name: 'Google Analytics 4', src: /googletagmanager\.com\/gtag\/js|google-analytics\.com\/(g\/)?collect/i, code: /gtag\(\s*['"]config['"]\s*,\s*['"]G-[A-Z0-9]{6,}/i },
  { name: 'Google Tag Manager', src: /googletagmanager\.com\/gtm\.js/i, code: /\bGTM-[A-Z0-9]{4,}\b/ },
  { name: 'PostHog', src: /posthog|i\.posthog\.com/i, code: /posthog\.init\s*\(|posthog\.capture\s*\(/ },
  { name: 'Plausible', src: /plausible\.io\/js|\/js\/script(\.[a-z-]+)*\.js.*plausible/i, code: /\bplausible\s*\(/, attr: 'data-domain' },
  { name: 'Umami', src: /umami/i, code: /umami\.track\s*\(/, attr: 'data-website-id' },
  { name: 'Fathom', src: /usefathom\.com/i, code: /fathom\.track(Event|Goal|Pageview)\s*\(/ },
  { name: 'Vercel Analytics', src: /\/_vercel\/insights\/script\.js|va\.vercel-scripts\.com/i, code: /\bva\.track\s*\(/ },
  { name: 'Cloudflare Web Analytics', src: /static\.cloudflareinsights\.com\/beacon/i, code: null, attr: 'data-cf-beacon' },
  { name: 'Mixpanel', src: /mixpanel/i, code: /mixpanel\.init\s*\(/ },
  { name: 'Amplitude', src: /amplitude\.com|cdn\.amplitude/i, code: /amplitude\.(init|getInstance)\s*\(/ },
  { name: 'Segment', src: /cdn\.segment\.(com|io)/i, code: /analytics\.load\s*\(\s*['"][A-Za-z0-9]{10,}/ },
  { name: 'Matomo', src: /matomo\.js|piwik\.js/i, code: /_paq\.push\s*\(/ },
  { name: 'Simple Analytics', src: /simpleanalyticscdn\.com/i, code: null },
  { name: 'Pirsch', src: /pirsch\.io/i, code: null },
  { name: 'OpenPanel', src: /openpanel/i, code: /window\.op\s*\(\s*['"]init|new\s+OpenPanel\s*\(/ },
  { name: 'Rybbit', src: /rybbit/i, code: null },
  { name: 'Microsoft Clarity', src: /clarity\.ms\/tag/i, code: /clarity\.ms\/tag/ },
];

export function detectInPage(page) {
  const found = new Map();
  const add = (name, how) => { if (!found.has(name)) found.set(name, how); };
  for (const s of page.scripts) {
    for (const v of VENDORS) {
      if (v.src.test(s.src)) add(v.name, `script ${s.src}`);
      else if (v.attr && s[v.attr] !== undefined) add(v.name, `script ${s.src} [${v.attr}]`);
    }
  }
  for (const code of page.inlineScripts) detectInCode(code, 'inline script', add);
  return found;
}

// A URL to the vendor (`//cdn.vendor.com/...`), or, for a vendor known by a
// path (`/_vercel/insights/...`), a string that starts with that path.
const urlPatterns = new Map(VENDORS.map((v) => [v.name, new RegExp(
  `(?:(?:https?:)?\\/\\/[^'"\\s]*${v.src.source.startsWith('\\/') ? `|['"\`]` : ''})(?:${v.src.source})`, 'i')]));

export function detectInCode(code, where, add) {
  for (const v of VENDORS) {
    if (v.code?.test(code)) { add(v.name, where); continue; }
    // A bare vendor word in a bundle is not a tag; an init call or a URL is.
    if (urlPatterns.get(v.name).test(code)) add(v.name, where);
  }
}
