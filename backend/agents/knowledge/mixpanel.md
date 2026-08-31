# Mixpanel

- **Mixpanel is the cross-platform event truth.** It receives the raw event
  name from web AND app SDKs, so it is the only tool that sees every platform
  under one name. Reconcile GA4 and ad-platform conversion counts *to*
  Mixpanel — a gap is a measurement bug until proven otherwise (observed: GA4
  event-edit rules renamed `signup`→`sign_up` on web while the key event stayed
  `signup`; 174 web signups/month silently stopped counting. Mixpanel's 164
  was the number that exposed it).
- **There is NO internal-traffic filter.** QA and staff accounts sit inside
  every funnel and count. Never quote a signup/upgrade number without the
  exclusion applied (`internal_traffic_excluded` in the pull says which
  distinct_id patterns were removed; empty means nothing was — say so).
  Observed: 8 of 8 iOS "upgrades" and 8 of 28 "signups" in a review window
  were test accounts.
- **Identity is usually the email.** `identify(email)` on web and app makes
  `distinct_id` the join key to Stripe / RevenueCat (`app_user_id`) — and a
  PII exposure if it reaches a report. Never print distinct_ids.
- **Legacy typo events persist forever** (e.g. `plan_upgrade_initated`).
  Hide them in Lexicon rather than filtering every query; never sum a typo
  with its corrected twin.
- **Attribution props ride on the event** (`utm_*`, `gclid`), first-touch
  on the profile. Expect the majority untagged (observed 89%) — an untagged
  signup is not an organic one.
- **Funnel results are per day and per-day ratios do not average.** The
  pull sums step counts across the window and recomputes conversion.
- Query API quota: 60 queries/hour, 5 concurrent. EU/India projects live on
  their own hosts — a 401 with the right secret is usually the wrong region.
- Service accounts are project-scoped; a pull for a project the account was
  not granted 403s and looks like a bad secret.
