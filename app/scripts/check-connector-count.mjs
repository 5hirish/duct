// The sidebar's connector badge, checked against the cases that broke it.
//
// The badge used to count two hardcoded sessionStorage keys (GA4, GSC), so it
// could never read past 2 and never saw Google Ads, GTM, or any of the twelve
// server-stored connector types. These cases pin the replacement's rule:
// union the two credential sources, count DISTINCT connector types, and hold
// Google Ads to the same two-part test the Connections page applies.
//
// Run: node scripts/check-connector-count.mjs

import { resolveConnectedTypes } from "../src/lib/connectorCount.js";

const CASES = [
  {
    name: "the reported bug: three connected, badge showed two",
    input: { sessionTypes: ["ga4", "gsc"], serverTypes: ["ga4", "gsc", "mixpanel"] },
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
    name: "session token and server row for the same type are not double counted",
    input: { sessionTypes: ["ga4"], serverTypes: ["ga4"] },
    expect: 1,
  },
  {
    name: "signed out: session tokens alone still count",
    input: { sessionTypes: ["ga4", "gsc", "gtm"] },
    expect: 3,
  },
  {
    name: "google ads without a developer token is partial, not connected",
    input: { sessionTypes: ["google_ads", "ga4"], hasAdsDevToken: false },
    expect: 1,
  },
  {
    name: "google ads with a developer token counts",
    input: { sessionTypes: ["google_ads", "ga4"], hasAdsDevToken: true },
    expect: 2,
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
