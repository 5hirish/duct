# Duct Backend — Claude Code instructions

Python reporting and synthesis backend for Duct.

## Product role

Per `docs/mvp/mvp-plan.md`, this backend is the actual product engine:

- read from client-owned destinations with read-only access
- normalize data into typed internal models
- compute signals and comparisons
- synthesize findings into structured output
- deliver via email and alerts

The web app owns HTML rendering. The backend produces JSON payloads only — it does not render HTML.

## MVP architecture

### Current stack

- **AI synthesis:** Three versioned engine implementations under `agents/insights/` — V1 (LangChain), V2 (Google ADK), V3 (Claude Agent SDK). Runtime-switchable via `generate_engine` env var.
- **Ingestion:** Direct Google API clients (`google-ads`, `google-analytics-data`, `google-api-python-client`). Async concurrent fetching in `service/pipeline.py`.
- **Normalization:** Lightweight Python pipeline — raw API response → typed Pydantic/SQLModel brief models. No query layer or transforms yet.
- **Database:** PostgreSQL on Railway — SQLModel ORM, Alembic migrations, `psycopg` driver.
- **Auth:** JWT for users; Google OAuth for connector linking (Ads, GA4, GSC, Sign-In).
- **Observability:** Sentry error tracking; optional OpenTelemetry tracing (wired via Claude Agent SDK).
- **Hosting:** Railway — auto-deploys from `main` via GitHub integration; `railway.json` defines Railpack build + uvicorn start.
- **CI:** GitHub Actions (`backend.yml`) — Ruff lint + pytest on every PR and push to `main`.

### Roadmap (not in codebase yet)

- **Ingestion framework:** PyAirbyte for early pilots → client-managed Airbyte later
- **Query layer:** DuckDB + Ibis
- **Transforms:** dbt
- **Orchestration:** Dagster
- **Delivery:** Resend (email) + Slack webhooks

## Product-shape constraints

- Do not build a dashboard-first product here.
- The primary value is the brief and alert output.
- The backend should support a thin onboarding app, not depend on a rich frontend.
- Design all outputs for operator clarity: what changed, why it matters, what to do next.

## Current directory structure

- `service/google/brief.py` — Google Ads brief normalization (loads demo from `data/<connector_id>/`, default `google_ads`)
- `service/google/schema.py` — typed Google Ads brief payload (dataclasses / JSON contract)
- `agents/insights/prompts.py` — synthesis system + user prompts (e.g. Google Ads weekly insight brief)
- `routes/auth.py` — OAuth by connector (`/auth/connectors/{connector_id}/oauth/...`)
- `routes/generate.py` — `POST /api/insights/generate` for interactive brief + LangChain synthesis envelope
- `data/google_ads/` — `google-ads-report.json` (demo brief), `raw/demo_raw_payload.json`

## Agent-type architecture

The `agents/` directory is organised by agent type. Each type is independent and has its own goals, tools, prompts, schema, and versioned runners.

```
agents/
├── engines.py          — engine/provider/model registry (shared across all agent types)
├── models.py           — Provider, ModelName enums (shared)
├── insights/           — Insights agent (paid ads + organic growth intelligence)
│   ├── v1/             — LangChain runner
│   ├── v2/             — Google ADK runner
│   ├── v3/             — Claude Agent SDK runner
│   └── goals/, tools/, schema.py, registry.py, prompts/
├── audit/              — future: SEO audit agent
└── content/            — future: Content marketing agent (plans, posts, publishing)
```

Route convention: each agent type gets its own route prefix:
- `POST /api/insights/generate` — exists
- `POST /api/audit/run` — future
- `POST /api/content/plan/stream` / `POST /api/content/post/stream` — future

Cross-agent invocations are modelled at the frontend level (e.g. audit findings carry an `invoke_insights` action that pre-populates the insights wizard). Backend agents remain decoupled — no direct calls between agent types.

## Artifact contract

The app lists top-level `*.json` briefs in `data/google_ads/` (e.g. `google-ads-report.json`) for local dev; user-generated insights are returned from `POST /api/insights/generate` and stored client-side (`localStorage`).

The JSON contract:
- `source_metadata.theme` — theme key (`paid_ads`, `product_intelligence`, `organic_growth`); the app resolves accent colors from this
- `source_metadata.generated_at` — ISO 8601 timestamp
- All other fields follow the typed models in `service/google/schema.py`

Do not write HTML from the backend. Do not reference `themes.json` or HTML templates — those have moved to the app.

## Code design rules

- Normalize first, synthesize second.
- Keep typed schemas central and explicit.
- The backend is a data pipeline, not a renderer. Output JSON; let the app handle presentation.
- Separate ingestion, normalization, synthesis, and delivery concerns.
- Prefer extensible evidence models so future tools can enrich the same findings.

## Sequencing rules from the plans

- Validate the brief/report shape before building heavy automation.
- Start with one customer, one tool, one brief/report end-to-end.
- Add connectors and orchestration only after the output format is useful.
- Add real-time anomaly detection after the scheduled brief flow works.

## What not to build yet

- no custom auth in backend
- no full Airbyte platform management
- no heavyweight job system beyond the planned orchestration layer
- no broad dashboard experience
- no complex cross-tool logic before the single-source MVP is producing useful output
