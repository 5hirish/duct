## Learned User Preferences

- Prefers modular implementations with shared assets/templates over duplicated inline page logic.
- Prefers report visuals to be data-driven from actual payload data, not mocked or approximated.
- For current app phase, prefers a no-auth open shell focused on rendering reports.

## Learned Workspace Facts

- The marketing demos are modularized into shared `site/assets/demo.css` and `site/assets/demo.js` plus variant data files.
- Google Ads report artifacts are generated as JSON only under `backend/reports/` (`google-ads-report.json`).
- The backend no longer renders HTML or writes themes.json — it embeds `source_metadata.theme` (e.g. `paid_ads`) into the JSON payload.
- Theme accent colors live in `app/src/lib/themes.js`. The app resolves them from the theme key in the payload.
- The `app/` area is a Next.js App Router report viewer. `app/src/components/GoogleAdsReport.js` renders the full report from the JSON payload.
- Backend CLI: `python backend/scripts/google_ads_brief.py --demo --theme paid_ads --output-json backend/reports/google-ads-report.json`
