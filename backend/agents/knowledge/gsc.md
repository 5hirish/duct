# Google Search Console

- **Paginate or lose the long tail.** Responses cap at 25,000 rows and page via
  `startRow`; a small `rowLimit` silently truncates. GSC sorts by clicks
  descending, so click totals survive truncation but the **zero-click
  impression long tail — the highest-value SEO target list — disappears**
  (measured: 71% of query impressions missing at rowLimit 250).
- **Most clicks have no attributable query.** GSC anonymizes rare queries; the
  page dimension routinely shows 3–5× the clicks of the query dimension. Use
  **page totals for "how much organic traffic," query totals only for "which
  known terms."** Never present query-sum as total organic.
- **`dataState: final` zeroes the last 2–3 days** of any window — the usual
  cause of a false "traffic fell off a cliff." Prefer `all` and label the tail
  as unfinalized.
- **Roll up locale URLs and www/non-www before reading page tables.** One page
  can appear as dozens of locale × host variants; correct 301s make this a
  reporting artifact, not a duplication bug.
- **`query × page` is the only way** to see which landing page ranks for which
  term — flat query or page tables cannot answer it.
- GSC counts **Google clicks**; GA4 organic counts **sessions from any search
  engine**. A GA4:GSC ratio of ~0.9–3.6× is normal (Bing/DDG + clicks vs
  sessions). Far outside that band, suspect bot pollution or a tagging break —
  investigate before reporting either number.
- Positions are query-weighted averages; a rising average position can mean
  losing bad rankings, not gaining good ones. Check impression volume alongside.
