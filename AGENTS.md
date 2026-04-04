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
- Google Ads demo data: raw input `backend/data/google_ads/raw/demo_raw_payload.json`; canonical brief sample `backend/data/google_ads/google-ads-report.json` (this is what the Next.js report list reads — one demo). API writes new briefs to `backend/data/google_ads/generated/` (`demo-<date>.json`, etc.).
- The typed Google Ads brief payload (dataclasses / JSON contract and reporting `StrEnum`s) lives in `backend/service/google/schema.py`; `backend/service/google/brief.py` builds it and `backend/service/google/metrics.py` formats comparison metrics.
- The backend no longer renders HTML or writes themes.json — it embeds `source_metadata.theme` (e.g. `paid_ads`) into the JSON payload.
- Theme accent colors live in `app/src/lib/themes.js`. The app resolves them from the theme key in the payload.
- The `app/` area is a Next.js App Router report viewer. `app/src/components/GoogleAdsReport.js` renders the full report from the JSON payload.
- Run the FastAPI API from `backend/` with `DUCT_API_KEY` set for `/api/*`. Google Ads OAuth: `GET /auth/connectors/google_ads/oauth/authorize`; callbacks are `/auth/connectors/google_ads/oauth/callback` and alias `/auth/google/callback` (same handler). Set `GOOGLE_OAUTH_REDIRECT_URI` to exactly match the authorized redirect URI in Google Cloud. `google_auth_oauthlib` enables PKCE by default; the backend stores the PKCE code verifier with OAuth state between authorize and callback so token exchange succeeds.
- Application settings load from `backend/config.py` via class `Configs` and `get_configs()` (pydantic-settings; optional `backend/.env`).
- LangChain-based report synthesis lives under `backend/agents/reporter/` (e.g. `generate_agent.py`, `schema.py`, `entities.py`).
