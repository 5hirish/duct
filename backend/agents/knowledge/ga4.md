# Google Analytics 4

- **GA4 ships with no internal-traffic filtering.** QA testers, staff, and dev
  machines land in production metrics by default — and they concentrate in
  exactly the low-N segments decisions are made on (a real case: 23 of 36
  "upgrades" came from 7 QA users). Before trusting any conversion count,
  check for geo/user clusters that look like a QA team.
- **Staging/dev hostnames often report into the production web stream.**
  Filter on the production `hostName` for any serious read.
- **Validate organic against GSC before baselining.** Bot bursts can log 40×+
  more "google/organic" sessions than GSC clicks for weeks, then stop — any
  baseline spanning such a window reads as a collapse when traffic actually
  grew. Normal GA4:GSC organic ratio is ~0.9–3.6×.
- **A key event's history is poisoned by its configuration history.** If a
  high-volume event (e.g. `session_start`) was ever marked as a key event,
  earlier windows are inflated — start conversion windows after the config
  change, and check the change history before comparing periods.
- **Event names are exact strings.** `signup` vs `sign_up` is two different
  events; a rename silently zeroes the old series and dashboards render the
  gap in the same font as real data.
- Cross-check paid: GA4 Paid Search sessions ≈ 90% of Google Ads clicks is
  normal; large gaps mean auto-tagging (`gclid`) or filtering problems — do not
  key paid attribution on `utm_medium` when auto-tagging is on.
- Admin mutations (key events, audiences) need the `analytics.edit` scope; a
  read-only token fails with 403 only at call time, not at connect time.
- Audiences are forward-looking — a new audience starts empty and cannot
  backfill; membership accumulates from creation.
