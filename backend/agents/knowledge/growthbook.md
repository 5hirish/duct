# GrowthBook

- **"Running" is a setting, not a signal.** Two experiments ran 92 days,
  displayed running throughout, and bucketed nobody after day 14 because a
  datasource assignment-query edit broke the exposure predicate. Nothing in
  the platform flagged it. Before citing any experiment, confirm exposures
  are still arriving: the pull marks `stale_running` when a running phase is
  older than 45 days and no result window reaches the last week.
- **Assignment and analysis must key on the same identity.** Experiments
  hashed on `distinct_id` (email) while the warehouse resolved users
  `$device_id`-first — assignment and results on different identifiers means
  misattribution wherever they diverge. Ask which id each side uses.
- **Results with control arms under the configured minimum sample are not
  results.** Both observed experiments sat under `minSampleSize: 150`; a
  chance-to-win on an underpowered arm is noise with a percentage sign.
- **A missing metric cannot be tested.** If there is no signup metric, no
  experiment here can test signup — say so rather than reading the nearest
  proxy as if it were the goal.
- Duct never writes to GrowthBook: flag flips and experiment stops are
  product decisions, out of scope for marketing execution.
- API keys are org-wide; filter by `project_id` to keep another product's
  experiments out of the picture (shared orgs are common).
