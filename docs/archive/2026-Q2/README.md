# Archived docs (Q2 2026)

Point-in-time plans, superseded recommendations, and completed UX specs. **Do not treat these as current architecture or active design source** — use active paths under [`../../engineering/`](../../engineering/).

| File | Why archived |
|------|----------------|
| [`dynamic-data-fetching-plan.md`](dynamic-data-fetching-plan.md) | Early spec (`/run`, old file layout, removed `/api/report`). Live flow: Next.js `/generate`, `backend/routes/generate.py`, `backend/service/google/`, LangChain reporter under `backend/agents/reporter/`. |
| [`add-demo-component-plan.md`](add-demo-component-plan.md) | Completed marketing-demo rollout; kept for history. Current demos live under `site/` (shared `site/assets/demo.css` / `demo.js` where applicable). |
| [`architecture-recommendations.md`](architecture-recommendations.md) | Argued for all-TypeScript on Cloudflare and no Python stack. Actual product ships FastAPI on Railway, Next.js on Cloudflare, Python Google Ads + synthesis. |
| [`2026-03-28-paid-ads-report-agent-plan.md`](2026-03-28-paid-ads-report-agent-plan.md) | Agent checklist targeting `for-paid-ads-demo.html`. Marketing paid-ads page is now `site/for-paid-ads.html` with the modular demo setup. |
| [`2026-03-28-paid-ads-report-design.md`](2026-03-28-paid-ads-report-design.md) | UX spec for that demo Step 4 (modal, KPIs, disclosure). Kept for reference; current markup is under `site/`. |

## Current pointers

- OAuth (living plan, updated): [`../../engineering/oauth-authentication-plan.md`](../../engineering/oauth-authentication-plan.md)
- Google Ads API (token app): [`../../engineering/google-ads-api-tool-design-document.md`](../../engineering/google-ads-api-tool-design-document.md)
