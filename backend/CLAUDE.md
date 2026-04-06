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

The current and planned backend stack is:

- **Ingestion:** PyAirbyte for early pilots, client-managed Airbyte later
- **Query layer:** DuckDB + Ibis
- **Transforms:** dbt
- **Orchestration:** Dagster
- **Synthesis:** Claude API + Instructor with typed models
- **Delivery:** Resend and Slack webhooks
- **Workspace/auth metadata:** Supabase

## Product-shape constraints

- Do not build a dashboard-first product here.
- The primary value is the brief and alert output.
- The backend should support a thin onboarding app, not depend on a rich frontend.
- Design all outputs for operator clarity: what changed, why it matters, what to do next.

## Current directory structure

- `service/google/brief.py` — Google Ads brief normalization (loads demo from `data/<connector_id>/`, default `google_ads`)
- `service/google/schema.py` — typed Google Ads brief payload (dataclasses / JSON contract)
- `agents/reporter/prompts.py` — synthesis system + user prompts (e.g. Google Ads weekly brief)
- `routes/auth.py` — OAuth by connector (`/auth/connectors/{connector_id}/oauth/...`)
- `routes/generate.py` — `POST /api/generate` (interactive brief + LangChain synthesis envelope)
- `data/google_ads/` — `google-ads-report.json` (demo brief), `raw/demo_raw_payload.json`

## Artifact contract

The app lists top-level `*.json` briefs in `data/google_ads/` (e.g. `google-ads-report.json`) for local dev; user-generated reports are returned from `POST /api/generate` and stored client-side (`localStorage`).

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
