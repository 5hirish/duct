// What counts as a connected data source, pinned to the cases that decide it.
//
// The load-bearing property: a source counts REGARDLESS of how it
// authenticates. The rule this replaced could only see four Google OAuth
// session keys, so an account whose only sources were Mixpanel and Stripe was
// told to go and connect one — while the Connections page showed both.
//
// The second property: `available` counts. The backend uses a single stored
// account with no binding rather than asking about it, so calling that
// "not connected" would ask for a reconnect nothing needs.
//
// Run: node scripts/check-data-sources.mjs

import {
  STATUS_BOUND, STATUS_AVAILABLE, STATUS_NOT_CONNECTED,
  isConnected, connectedCount,
} from "../src/lib/dataSources.js";

const src = (over = {}) => ({
  connector_id: "ga4", label: "GA4", status: STATUS_NOT_CONNECTED,
  auth_kind: "oauth", stored_accounts: [], ...over,
});

const cases = [];
const check = (name, got, want) => cases.push({ name, got, want });

// --- what counts -----------------------------------------------------------
check("a bound source counts", isConnected(src({ status: STATUS_BOUND })), true);
check("an available source counts", isConnected(src({ status: STATUS_AVAILABLE })), true);
check("a not_connected source does not", isConnected(src({ status: STATUS_NOT_CONNECTED })), false);
check("an unknown status is not counted", isConnected(src({ status: "weird" })), false);
check("a missing source is not counted", isConnected(undefined), false);

// --- both connector shapes -------------------------------------------------
{
  const sources = [
    src({ connector_id: "ga4", auth_kind: "oauth", status: STATUS_BOUND }),
    src({ connector_id: "mixpanel", auth_kind: "manual", status: STATUS_AVAILABLE }),
    src({ connector_id: "stripe", auth_kind: "manual", status: STATUS_NOT_CONNECTED }),
  ];
  check("an API-key source counts the same as an OAuth one", connectedCount(sources), 2);
  check("a purely API-key account is not told to connect something",
    connectedCount([src({ connector_id: "mixpanel", auth_kind: "manual", status: STATUS_AVAILABLE })]),
    1);
}

// --- degenerate input ------------------------------------------------------
check("no sources is zero, not a crash", connectedCount([]), 0);
check("a non-array is zero, not a crash", connectedCount(null), 0);
let failed = 0;
for (const { name, got, want } of cases) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failed++;
  console.log(`${ok ? "✓" : "✗"} ${name}${ok ? "" : ` — expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`}`);
}
console.log(failed ? `\n${failed} case(s) failed` : `\nall ${cases.length} cases pass`);
process.exit(failed ? 1 : 0);
