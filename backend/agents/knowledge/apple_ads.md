# Apple Search Ads

- **Money fields are STRINGS.** Apple returns Money as
  `{"amount":"12.34","currency":"USD"}` — parse the amount, never sum the raw
  field, and never assume a float.
- **`/reports/campaigns` is ORG-scoped.** Without campaign conditions the
  totals mix every app in the org — a shared org silently contaminates one
  app's numbers with another's spend. Always condition report calls on the
  campaign ids you mean.
- **v5 renamed installs:** `installs` → `tapInstalls` (tap-through) and
  `totalInstalls` (incl. view-through). Old field names read as zero.
- **Apple attributes installs only.** There is no revenue or downstream
  conversion metric — reconcile channel value against the billing source
  (Stripe/RevenueCat), never against installs.
- **`selector.orderBy` is documented optional but is REQUIRED** on every
  reporting endpoint (`REQUIRED_INPUT_ORDER_BY_MISSING`). The id field works
  at every level except searchterms (use `impressions` there).
- **Report totals rule Apple documents only in prose:** with `granularity`
  set, `returnRowTotals` and `returnGrandTotals` must both be false; without
  one, `returnRowTotals` must be true. Getting it wrong is a 400 that never
  mentions granularity.
- **Granularity windows are hard limits:** HOURLY ≤ 7 days (start ≤ 30 days
  ago), DAILY ≤ 90 days, WEEKLY > 14 and ≤ 365 days, MONTHLY > 3 months.
  Exceeding one 400s naming the field but not the limit.
- **Search-terms rows only appear above an impressions threshold** — silence
  is not "no traffic", it can be "below the privacy floor".
- Attribution is last-touch within Apple's ecosystem; compare against Meta's
  7d-click/1d-view or GA4 data-driven models only after normalizing windows.
- **v5 sunsets 2027-01-26** (Apple Ads Platform API replaces it) — treat
  version-specific field mappings as migration surface.
