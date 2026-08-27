# OpenAI Ads (ChatGPT Ads)

- **Insights cannot see conversions.** The metric set is exactly
  impressions, clicks, spend, ctr, cpc, cpm — no conversion, revenue, or
  ROAS metric exists on any insights endpoint. Pixel conversions are visible
  only in the Ads Manager UI. Never present CPC as the decision metric for a
  channel whose job is paid signups; judge it against the billing source.
- **Units differ between insights and the pixel.** Insights `spend` is a
  decimal in account currency (18.42); the measurement pixel's `amount` is an
  integer in MINOR units (1499). Same vendor, opposite conventions — the
  100× trap.
- **The API key is scoped to ONE ad account** — there is no account-id
  parameter anywhere; `GET /ad_account` tells you which account you're
  pointed at. A key from another account 401s.
- **Omitting `fields` returns almost nothing** (impressions + a name column)
  — always project the full metric set plus row identity explicitly.
- Array params are repeated keys (`fields[]=a&fields[]=b`), not comma lists;
  dict values (time_ranges) are JSON-encoded per item.
- Pixel/Conversions-API *management* endpoints are partner-gated (404) even
  when the pixel itself works — only API management is restricted.
- Rate limits: 600 req/min per endpoint, 1200 overall — generous, but pace
  bursts anyway.
