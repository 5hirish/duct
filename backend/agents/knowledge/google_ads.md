# Google Ads

- **All money fields are micros** (millionths of the account currency).
  Divide by 1,000,000; never mix micros and units in one comparison.
- **`DURING` accepts only fixed literals** (LAST_7_DAYS/14/30 etc.). Arbitrary
  windows need explicit `segments.date BETWEEN 'x' AND 'y'` — "90 days" via
  DURING fails, and depending on error handling can silently return nothing.
- **Bulk mutates return HTTP 200 with per-row failures in the body**
  (`partial_failure_error`). Anything that checks only the status code reports
  success on a no-op. Always inspect per-operation results.
- **GAQL fields churn between API versions** (fields removed from `campaign`,
  bid-strategy detail moved to the `bidding_strategy` resource, position
  estimates gone entirely). An UNRECOGNIZED_FIELD error can silently kill an
  entire pull whose failure is buried in a truncated error string. Before a
  version bump, A/B every query against the live account.
- **Shared budgets:** a campaign's budget may be shared across campaigns —
  changing it changes siblings. Check `campaign_budget` linkage before any
  budget mutation and say so in the preview.
- **Page-load pseudo-conversions poison Smart Bidding.** A conversion that
  fires on page view (not a real action) trains PMax/Demand Gen toward junk
  traffic. Audit what each imported conversion actually measures before
  optimizing toward it.
- **Attribution is last-click by default** — never compare Google Ads
  conversions 1:1 against Meta (7d-click/1d-view) or platform-reported numbers
  from any other network without normalizing windows.
- Search-term reports hide low-volume terms below privacy thresholds — the
  uncovered spend share is structural, not a data bug.
- MCC access needs `login-customer-id` (manager ID, digits only); without it
  child-account queries fail in ways that look like empty accounts.
- A developer token is bound permanently to the first Cloud project that uses
  it, and a token in Test access mode cannot query production accounts.
- Campaign/ad-group/keyword removal is **irreversible** (`REMOVED` is forever).
  Pause instead; never propose removal as a reversible change.
