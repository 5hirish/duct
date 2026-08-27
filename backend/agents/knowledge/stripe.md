# Stripe

- **Stripe is the money truth.** Every ad platform reports its own attributed
  conversions; Stripe reports money that settled. When they disagree, Stripe
  wins — reconcile ad-platform numbers against Stripe, never the reverse.
- **`incomplete` / `incomplete_expired` subscriptions NEVER CHARGED.** They
  are abandoned or failed checkouts, not sales — counting them as acquisition
  overstates it 2-3× (observed: 31 never-paid vs 40 real in one month).
- **`metadata.change_type == "upgrade"` is expansion, not acquisition.**
  Separate first purchases from plan changes before counting "new".
- **Charge volume ≠ acquisition.** Most successful charges are renewals of
  the existing base (observed: 65 charges / $1,547 in a window with only 2
  new paid subscriptions).
- **Net refunds out** — a charge with `refunded` is not revenue.
- **Read prices off subscription ITEMS, not the legacy top-level `plan`** —
  `plan` is null for multi-item subscriptions and silently records $0.
- **Amounts are integers in the smallest currency unit** (1999 = $19.99);
  zero-decimal currencies (JPY, KRW, …) pass through unchanged. Timestamps
  are unix seconds UTC.
- **`charge.invoice` was REMOVED in the dahlia release train** — subscription
  payments link via `payment_intent` now; never infer "no invoice ⇒ not a
  renewal".
- **Restricted keys fail per-resource:** a key missing one read permission
  403s on just that endpoint and looks healthy everywhere else — probe each
  resource before concluding data is absent.
- **Pin the API version.** Monthly releases within a named train (acacia →
  … → dahlia) are non-breaking; a train change reshapes fields — read the
  changelog before bumping.
- Pagination is by the last object's id (`starting_after`), newest-first,
  100/page max — there is no offset and no server-side GROUP BY without
  Sigma (`reporting_write`, which a read key should not carry).
