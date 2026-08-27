# Meta Ads (Facebook/Instagram Marketing API)

- **Two money scales in the same response.** `daily_budget`,
  `lifetime_budget`, `bid_amount`, `spend_cap` are strings in MINOR units
  (cents); `spend`, `cpc`, `cpm`, action values are strings in MAJOR units
  (dollars). Reading budgets as dollars overstates them 100× — the single
  most common Meta reporting bug.
- **One purchase, three action_types.** Conversions arrive as an `actions`
  list of {action_type, value}; the SAME order can appear under
  `offsite_conversion.fb_pixel_purchase`, `purchase`, and `omni_purchase`.
  Pick ONE (pixel first), never sum — summing is how Meta ROAS looks 3×
  better than Stripe.
- **Attribution is 7d-click + 1d-view by default** vs Google/Apple last-click.
  Request explicit `action_attribution_windows` and never compare raw
  conversion counts across platforms.
- **Default listing hides paused history.** Without an explicit
  `effective_status` list, campaign/adset/ad edges return only ACTIVE rows —
  most of what you want to audit is silently missing.
- **The HTTP status is nearly always 400** — branch on `error.code` /
  `error_subcode`, not the status. code 190 = token dead (a *User* token dies
  at ~60 days; a System User token doesn't expire); code 100/subcode 33 =
  not-found OR not-visible-to-this-token (indistinguishable for ad accounts).
- **Too-big sync insights don't paginate** — Meta bounces "please reduce the
  amount of data" (code 1/100); rerun the identical query as an async report
  job instead of shrinking windows by guesswork.
- `reach` and `frequency` are refused on some breakdowns and fail the WHOLE
  request rather than dropping the field — keep them out of shared field sets.
- Breakdowns can't be combined freely: request country / platform / device /
  demo splits as separate calls.
- **Shared ad accounts contaminate totals** — filter campaigns by product
  (name substrings) and push the filter server-side into insights `filtering`
  so aggregates stay clean.
