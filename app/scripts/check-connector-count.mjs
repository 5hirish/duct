// The sidebar's connector badge, checked against the cases that broke it.
//
// The badge used to count two hardcoded sessionStorage keys (GA4, GSC), so it
// could never read past 2 and never saw Google Ads, GTM, or any of the twelve
// server-stored connector types. These cases pin the replacement's rule:
// count DISTINCT connector types among the stored rows, and nothing else — a
// Google token no longer lives in the browser to be counted (issue #456).
//
// Run: node scripts/check-connector-count.mjs

import { resolveConnectedTypes } from "../src/lib/connectorCount.js";

const CASES = [
  {
    name: "the reported bug: three connected, badge showed two",
    input: { serverTypes: ["ga4", "gsc", "mixpanel"] },
    expect: 3,
  },
  {
    name: "a manual connector alone is still a connection",
    input: { serverTypes: ["clarity"] },
    expect: 1,
  },
  {
    name: "every server-stored type counts, not just the Google four",
    input: { serverTypes: ["mixpanel", "clarity", "growthbook", "stripe", "meta_ads"] },
    expect: 5,
  },
  {
    name: "two accounts of one connector are one source",
    input: { serverTypes: ["stripe", "stripe", "stripe"] },
    expect: 1,
  },
  {
    // Google Ads used to need a developer token on top of OAuth to count.
    // Google sunset those on 2026-09-09, so OAuth alone is the whole answer
    // and Ads counts exactly like GA4 next to it.
    name: "google ads counts on OAuth alone",
    input: { serverTypes: ["google_ads", "ga4"] },
    expect: 2,
  },
  {
    // What a caller from before #456 still passes: a tab's session tokens are
    // no evidence of a connection anywhere else, so they count for nothing.
    name: "session-only tokens are not a connection",
    input: { sessionTypes: ["ga4", "gsc"] },
    expect: 0,
  },
  { name: "nothing connected", input: {}, expect: 0 },
];

let failed = 0;
for (const { name, input, expect } of CASES) {
  const got = resolveConnectedTypes(input).size;
  const ok = got === expect;
  if (!ok) failed++;
  console.log(`${ok ? "✓" : "✗"} ${name} — expected ${expect}, got ${got}`);
}
console.log(failed ? `\n${failed} case(s) failed` : "\nall cases pass");
process.exit(failed ? 1 : 0);
