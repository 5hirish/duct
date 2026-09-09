# Archived docs (Q2 2026)

Point-in-time plans, superseded recommendations, and completed UX specs. **Do not treat these as current architecture or active design source** — use active paths under [`../../engineering/`](../../engineering/).

| File | Why archived |
|------|----------------|
| [`dynamic-data-fetching-plan.md`](dynamic-data-fetching-plan.md) | Early spec (`/run`, old file layout, removed `/api/report`). Live flow: Next.js `/generate`, `backend/routes/generate.py`, `backend/service/google/`, LangChain reporter under `backend/agents/reporter/`. |
| [`add-demo-component-plan.md`](add-demo-component-plan.md) | Completed marketing-demo rollout; kept for history. Current demos live under `site/` (shared `site/assets/demo.css` / `demo.js` where applicable). |
| [`architecture-recommendations.md`](architecture-recommendations.md) | Argued for all-TypeScript on Cloudflare and no Python stack. Actual product ships FastAPI on Railway, Next.js on Cloudflare, Python Google Ads + synthesis. |
| [`2026-03-28-paid-ads-report-agent-plan.md`](2026-03-28-paid-ads-report-agent-plan.md) | Agent checklist targeting `for-paid-ads-demo.html`. Marketing paid-ads page is now `site/for-paid-ads.html` with the modular demo setup. |
| [`2026-03-28-paid-ads-report-design.md`](2026-03-28-paid-ads-report-design.md) | UX spec for that demo Step 4 (modal, KPIs, disclosure). Kept for reference; current markup is under `site/`. |
| [`oauth-authentication-plan.md`](oauth-authentication-plan.md) | Superseded on both load-bearing decisions: tokens live in `connector_credentials`, not `sessionStorage`, and the Google Ads developer token is now user-supplied. Routes generalised to `/auth/connectors/{connector_id}/oauth/*`. |
| [`user-storage-railway-postgres-sqlmodel-alembic.md`](user-storage-railway-postgres-sqlmodel-alembic.md) | The setup it plans is done; its unchecked boxes are stale, not pending. The live parts (migration workflow, `.env.local` proxy URL, additive/reversible policy) are in [`backend/AGENTS.md`](../../../backend/AGENTS.md). |
| [`dashboard-library-evaluation.md`](dashboard-library-evaluation.md) | Evaluation decided and executed — shadcn/ui shipped. Living design docs are `app/DESIGN.md` and [`design-system-contrast-review.html`](../../engineering/design-system-contrast-review.html); the token values here predate both. |
| [`ga4-gsc-connectors-plan.md`](ga4-gsc-connectors-plan.md) | Both connectors shipped (`backend/service/google/ga4.py`, `gsc.py`) and the connector set grew well past two. Adding one now follows the `add-connector` skill. |
| [`business-profile-context-enrichment-plan.md`](business-profile-context-enrichment-plan.md) | Assumed a localStorage business profile filled in by an onboarding wizard. The wizard is deleted; context is an `agent_context` row per (project, agent) served by `backend/routes/user_contexts.py`. |
| [`intelligent-insights-architecture-plan.md`](intelligent-insights-architecture-plan.md) | Its two ideas shipped (`ENTITY_CATALOG`, agent-authored `dashboard_spec`) but the wizard + two-call pipeline around them did not. Current design: [`autonomous-insights-agent-plan.md`](../../engineering/autonomous-insights-agent-plan.md). |
| [`persistent-insights-live-data-chat-context-plan.md`](persistent-insights-live-data-chat-context-plan.md) | Premised on "localStorage-only, no backend DB". Insights persist in Postgres against a project; the planned chat sidebar became the artifact store plus the insights session. |
| [`blog-writer-agent.md`](blog-writer-agent.md) | Never implemented, and its engineering half is built on the removed Claude Agent SDK (`output_format`, `allowed_tools`, `audit/v3/runner.py`). `AgentType.BLOG_WRITER` is still *Coming soon*, so the product narrative and three-phase shape survive; rebuild the rest on LangChain. |

## Current pointers

- Connector OAuth, as shipped: `backend/routes/auth.py` and `backend/service/connectors.py`; adding a connector follows the `add-connector` skill.
- Insights architecture: [`../../engineering/autonomous-insights-agent-plan.md`](../../engineering/autonomous-insights-agent-plan.md)
- Database and migrations: [`../../../backend/AGENTS.md`](../../../backend/AGENTS.md)
- Google Ads API (token app): [`../../engineering/google-ads-api-tool-design-document.md`](../../engineering/google-ads-api-tool-design-document.md)
