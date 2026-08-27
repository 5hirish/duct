# Cross-platform reconciliation

- **Only the biller knows.** Ad platforms (Google, Meta, Apple, OpenAI)
  report *their own attributed* conversions; Stripe and RevenueCat report
  money that settled. Reconcile platforms against billing, never against
  each other, and never billing against a platform.
- **Attribution windows are different definitions, not different accuracy.**
  Meta defaults to 7d-click + 1d-view; Google Ads and Apple report
  last-click/last-touch; GA4 uses data-driven attribution. Comparing raw
  conversion counts across them is comparing three definitions of the same
  word. Normalize to a chosen window (1d-click is the closest common
  denominator) before any cross-platform table.
- **The sum of platform-attributed conversions routinely exceeds billed
  reality** — every platform claims the same purchase. Expect over-attribution
  of 1.5-3×; a total that matches billing exactly is suspicious, not
  reassuring.
- **Contamination check before any comparison:** shared ad accounts/orgs mix
  products (Apple org-scoped reports, Meta shared accounts). Confirm every
  number is scoped to the same product before comparing channels.
- **Unit check before any comparison:** minor vs major currency units differ
  per field within the same vendor (Meta budgets vs spend; OpenAI pixel vs
  insights; Stripe integer cents). Normalize to major units first.
- **Time zones shift daily rows:** each platform reports in its own account
  timezone (Apple ORTZ, Meta account TZ, Stripe UTC). Day-level joins across
  platforms are approximate near midnight; compare windows, not days.
- **Refunds and never-paid checkouts only exist in billing** — an ad
  platform's "purchase" includes orders that later refunded and checkouts
  that never charged. Net revenue lives in Stripe/RevenueCat only.
