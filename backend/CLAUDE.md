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
- **Auth:** JWT for users; Google OAuth for connector linking (Ads, GA4, GSC, Sign-In). Project access is by membership (`project_members`), not by `projects.user_id` — always go through `service/membership.py`.
- **Email:** `service/email/` — Resend when `RESEND_API_KEY` is set, otherwise a logging console backend so dev/CI need no vendor account.
- **Observability:** Sentry error tracking; optional OpenTelemetry tracing (wired via Claude Agent SDK).
- **Hosting:** Railway — auto-deploys from `main` via GitHub integration; `railway.json` defines Railpack build + uvicorn start.
- **CI:** GitHub Actions (`backend.yml`) — Ruff lint + pytest on every PR and push to `main`.

### Desktop (local sidecar) mode

The backend runs in two shapes from one codebase. Railway is unchanged; the
desktop build runs the same FastAPI app as a sidecar on the user's machine —
see `docs/engineering/agent-engine-consolidation-review.md` §7–8.

- **Entrypoint:** `local_server.py`. Sets `DUCT_LOCAL=1`, resolves the per-user
  data dir, binds **127.0.0.1** on an OS-assigned port, and prints a single JSON
  handshake line on stdout before starting uvicorn:
  `{"duct_sidecar":1,"url":...,"port":...,"api_key":...,"data_dir":...}`.
  The Tauri shell must read the port from that line — never assume one.
- **Data dir** (`utils/appdirs.py`): macOS `~/Library/Application Support/ai.getduct.desktop`,
  Windows `%APPDATA%\Duct`, Linux `$XDG_DATA_HOME/duct`. Created `0700`.
  Override with `--data-dir` or `DUCT_DATA_DIR`.
- **Local mode defaults** (`Configs._apply_local_mode_defaults`): SQLite at
  `<data_dir>/duct.db`, uploads at `<data_dir>/uploads`, `init_db_on_startup=True`
  (no Alembic on a laptop). Each is only filled when unset, so
  `DATABASE_URL=postgresql://…` still works for a developer running local mode.
- **Local API key:** generated once, persisted `0600` at `<data_dir>/local-api-key`,
  and exported as `DUCT_API_KEY` so the existing `validate_api_key` gate applies
  unchanged. It only stops other local processes driving the sidecar.
- **JSON columns must use `models/columns.py::json_column()`**, never
  `postgresql.JSONB` directly — raw JSONB fails to compile on SQLite. The variant
  still renders JSONB on Postgres, so it produces no Alembic diff.
- **Never name a module `models/types.py`** — it shadows the stdlib `types`.

### Database migrations

Schema changes are applied **manually** with Alembic — a normal local dev step,
distinct from an app deploy (the global "deploys go through CI/CD" rule is about
shipping app code, not running migrations). Nothing runs migrations
automatically: `railway.json` only starts uvicorn and there is no CI migration job.

- Apply: from `backend/`, run `alembic upgrade head`. The DB URL resolves from
  `backend/.env.local` (the Railway TCP proxy) via `config.get_configs()`.
- Inspect: `alembic current`, `alembic heads`, `alembic history`.
- The proxy host is not resolvable inside the command sandbox, so migration
  commands run with the sandbox disabled (they need network to `*.rlwy.net`).
- New models must be imported in `models/__init__.py` so `SQLModel.metadata`
  picks them up for autogenerate.
- Migrations should be additive/reversible — always provide a working `downgrade`.

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
- `routes/project_members.py` — project members + email invitations (`docs/engineering/project-collaboration-plan.md`)
- `service/membership.py` — project access checks (owner vs collaborator) and invite token handling
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
