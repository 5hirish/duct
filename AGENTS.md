## Learned User Preferences

- Prefers modular implementations with shared assets/templates over duplicated inline page logic.
- Prefers report visuals to be data-driven from actual payload data, not mocked or approximated.
- For the Next.js app, wants OAuth-based data connections and report viewing/generation flows (not only a no-auth demo shell), with attention to mobile usability and add-to-home-screen behavior.
- Prefers Playwright (or similar) for automated smoke QA on the static marketing site so routing and internal-link regressions are caught early.
- For third-party service logos in the app UI, prefers official brand marks with authentic colors (e.g. Simple Icons), not improvised or single-hue substitutes.

## Learned Workspace Facts

- The marketing demos are modularized into shared `site/assets/demo.css` and `site/assets/demo.js` plus variant data files.
- The static marketing site (`site/`) is deployed on Cloudflare Pages; internal navigation should use extensionless paths (e.g. `/blog`, `/for-paid-ads`) rather than hardcoded `.html` URLs so production routing stays consistent.
- Playwright smoke tests for the marketing site live under `site/tests/e2e/` (see `site/playwright.config.js`).
- Google Ads report artifacts are generated as JSON only under `backend/reports/` (`google-ads-report.json`).
- The backend no longer renders HTML or writes themes.json — it embeds `source_metadata.theme` (e.g. `paid_ads`) into the JSON payload.
- Theme accent colors live in `app/src/lib/themes.js`. The app resolves them from the theme key in the payload.
- The `app/` area is a Next.js App Router report viewer. `app/src/components/GoogleAdsReport.js` renders the full report from the JSON payload.
- Backend CLI: `python backend/scripts/google_ads_brief.py --demo --theme paid_ads --output-json backend/reports/google-ads-report.json`
