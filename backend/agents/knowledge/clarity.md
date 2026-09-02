# Microsoft Clarity

- **Clarity answers "what happened after the click".** Rage clicks, dead
  clicks, quick-backs (user bounced back within seconds), excessive scroll,
  and script errors per landing page — the friction the ad platforms' "landing
  page experience" score hides. A paid campaign with fine CTR and a landing
  page with 8% rage-click sessions is a page problem, not a bidding problem.
- **10 API requests per project per day, hard.** A 429 is "tomorrow", not
  "slow down" — it is never retried. Verifying a token costs 1; one Duct pull
  costs 2 (overall + per-URL). Do not poll.
- **Only the last 1–3 days exist via API.** This is a live-health signal, not
  history; trend it by pulling daily and storing the summary.
- **Sessions include bots** — read `bot_sessions` next to `sessions` before
  computing any rate.
- `sessions_pct` on each friction metric is "sessions that had at least one",
  not a count; compare pages by `sessions_pct`, not `total`.
- The API token IS the project: there is no project id in the request, so a
  token pasted from the wrong project silently reports the wrong site.
