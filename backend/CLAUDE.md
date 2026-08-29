# Duct Backend — Claude Code instructions

Python reporting and synthesis backend for Duct.

## Product role

Per the MVP plan (duct-cloud, private), this backend is the actual product engine:

- read from client-owned destinations with read-only access
- normalize data into typed internal models
- compute signals and comparisons
- synthesize findings into structured output
- deliver via email and alerts

The web app owns HTML rendering. The backend produces JSON payloads only — it does not render HTML.

## MVP architecture

### Current stack

- **AI synthesis:** Three versioned engine implementations under `agents/insights/` — V1 (LangChain / deepagents), V2 (Google ADK), V3 (Claude Agent SDK). Runtime-switchable via `generate_engine` env var.

  **Consolidating on V1.** Per the engine consolidation review (duct-cloud, private), all
  agents are moving to one harness — LangChain 1.x / `deepagents` — because customers bring
  their own model (OpenAI / Gemini / Claude / OpenRouter) and the Claude Agent SDK is
  Anthropic-only by design (upstream issue #410, closed `not planned`).
  Each engine has a different status, and they imply different rules:

  - **V1 — the target, under construction.** Rebuilt on `create_agent` + structured output;
    `v1/graph.py` is gone. New agent work goes here.
  - **V2 — frozen.** Kept as insurance, not maintained. Do not extend it. When a change to
    shared code would require ADK work, leave V2 on the old behaviour and note the divergence
    rather than porting the change.
  - **V3 — maintained, and still the production path** for audit and content. It is *not*
    being retired yet. Keep it working: shared-code changes (`agents/core/`,
    `agents/audit/`, `agents/content/`, `schema.py`, `agents/models.py`) must keep V3 at
    parity, and V1 ports land **alongside** V3 rather than replacing it. Retirement happens
    only once V1 has earned full confidence — real-provider evals plus a clean audit and
    content run.

  So a shared change may need doing twice (V1 + V3) but never three times: V2 absorbs nothing.
  Claude remains a first-class *model* through V1, so retiring V3 later costs no capability.
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
see the engine consolidation review (duct-cloud, private) §7–8.

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
  commands run with the sandbox disabled — they need outbound network to the
  managed database's proxy domain.
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

### Shared helpers — check here before writing a local copy

Each of these replaced a family of divergent duplicates (23 private
`_utcnow()` definitions, five hand-rolled retry loops). A new local copy
re-opens that drift, so reach for these first and extend them when they
don't fit.

- `utils/dates.py` — `utcnow()`, `now_iso()`, `parse_iso()`, `last_n_days()`.
  **Never `datetime.now()` or `datetime.utcnow()`**: every persisted timestamp
  is UTC-aware, and naive ones compare and serialise inconsistently across
  SQLite (desktop) and Postgres (Railway). Stdlib-only leaf module, so
  `models/` can use `default_factory=utcnow` without an import cycle.
- `utils/strings.py` — `slugify()`, `titleize()`.
- `utils/formatting.py` — `money()`, `number()`, `percent()`, `multiplier()`,
  `safe_divide()`.
- `service/memory.py` — agent memory (`project_memories`): `remember()` is the
  ONLY write path (it redacts secrets, dedupes, honours the pause switch, and
  closes the previous value of a state key), `search()` is the only read path
  (Postgres FTS, SQLite LIKE), and `build_memory_context()` assembles the prompt
  blocks. Never write the table directly and never re-render the digest locally
  — the supersession and never-raise contracts live in that module.
  `service/memory_consolidation.py` owns the post-session extraction pass; its
  model output is a proposal that still goes through `remember()`. Tools for
  both harnesses are in `agents/core/memory_tools.py` and the shared prompt
  stanza is `agents/core/prompts.py::MEMORY_DISCIPLINE`. Per-project memory goes
  in the USER message, never the system prompt.
  `search(time_aware=True, rank=True)` is the question-shaped read — it reads a
  date range out of the words, treats a named kind as a filter, matches on ANY
  term and then tightens (all terms → two → one), and ranks by relevance +
  recency + importance + recall. Leave both off for a filter form like the
  timeline, whose inputs are the user's explicit instructions. Retrieval makes
  no model calls, by design. `tests/eval/memory_recall.py` holds the 50-question
  set (`pytest tests/test_memory_retrieval.py -s` prints the per-axis report);
  it exists because it caught the AND-everything query bug that made questions
  retrieve nothing, so extend it before tuning retrieval by feel.
- `service/rest.py` — sync HTTP transport for the reporting connectors:
  retry, backoff, rate-limit pacing, error typing. A new connector declares
  an `Endpoint` and an `ApiError` subclass and writes no transport code;
  auth headers, query encoding and pagination stay vendor-side. Not for
  `service/apify` or `service/post_bridge` — those are async, hold a
  long-lived client, and need no retry.

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
