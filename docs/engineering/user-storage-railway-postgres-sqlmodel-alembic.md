# User storage: Railway Postgres + SQLModel + Alembic

**Summary:** Persist only authenticated users (Google sign-in) in Railway Postgres for now. Implement with SQLModel (SQLAlchemy 2 + Pydantic) and Alembic migrations from day one so schema evolution stays explicit and safe. Cloudflare remains for edge and R2; FastAPI on Railway owns the database connection and migrations.

## Checklist (implementation)

- [x] **Postgres host:** Railway Postgres — provision plugin, set `DATABASE_URL` on FastAPI service
- [ ] **Dependencies + config:** Add `sqlmodel`, `alembic`, `psycopg[binary]` (or `asyncpg` if standardizing on async DB) + `database_url` in `backend/config.py`
- [ ] **Layout + Alembic:** Add `backend/db` (engine, `SessionLocal`, `get_session`) + `backend/models` (SQLModel tables) + `alembic.ini` and `alembic/env.py` wired to `SQLModel.metadata`; register new packages in `backend/pyproject.toml`
- [ ] **First migration:** Initial Alembic revision (empty baseline or first tables once models exist); document local workflow (`alembic upgrade head`)
- [ ] **Schema v1 (auth-only):** Design tables for Google user identity and durable OAuth state (`users`, `auth_identities`, `oauth_states`)
- [ ] **Sign-in persistence:** On `/auth/signin/google/callback`, upsert user + identity before issuing JWT
- [ ] **OAuth state:** Replace in-memory OAuth state in `backend/routes/auth.py` and `backend/routes/signin.py` with Postgres-backed state
- [ ] **Deferred domains:** Keep connectors/report persistence out of this first DB milestone

## Decision (locked)

- **Database:** Railway managed PostgreSQL in the same Railway project as the FastAPI API (`DATABASE_URL` / private networking as Railway documents).
- **ORM / models:** SQLModel (typed tables that align with Pydantic v2, built on SQLAlchemy 2).
- **Migrations:** Alembic from the start—every schema change is a versioned migration, not ad-hoc `CREATE TABLE` in production.

## Railway Postgres setup

**Goal:** Managed PostgreSQL in the **same Railway project** as the FastAPI API, with a stable **`DATABASE_URL`** available to the backend at runtime (and for local Alembic runs when you choose).

Official reference: [Railway PostgreSQL](https://docs.railway.com/databases/postgresql).

### 1. Use the existing API project

Use the Railway project that already deploys Duct’s API from this monorepo. Confirm the API service has **Root Directory** set to **`backend`** and follows [Part 2 — Railway (API)](./deployment-cloudflare-railway.md#part-2--railway-api) in the deployment runbook.

### 2. Add PostgreSQL

In the Railway dashboard:

1. **New** → **Database** → **PostgreSQL** (or add PostgreSQL from the template gallery).
2. Wait until the database service is **active** and shows connection details.

Railway creates credentials and a default database; you normally do **not** hand-create users or DBs for the first setup.

### 3. Attach `DATABASE_URL` to the FastAPI service

The Postgres service exposes variables such as **`DATABASE_URL`**, **`PGHOST`**, **`PGPASSWORD`**, etc.

On the **FastAPI** service (not the database card):

1. Open **Variables** (or **Settings → Variables**).
2. Add **`DATABASE_URL`** for the API process.
3. Prefer a **variable reference** to the Postgres service’s **`DATABASE_URL`** (Railway UI: add variable → reference another service) so the API always picks up the canonical URL, including after credential rotation.

Redeploy the API service if needed so new variables are visible to running containers (Railway usually restarts on variable changes; confirm on the deployment).

### 4. Networking

Services in the same project communicate over Railway’s **private network**. The referenced `DATABASE_URL` is intended for **server-side** use from the API container. Do **not** paste that URL into public client code or commit it to git.

### 5. Local development

Pick one:

| Approach | When to use |
|--------|--------------|
| **`.env` / `.env.local`** | Copy a **development** connection string from the Postgres service **Connect** (or **Data**) tab into `backend/.env.local` as `DATABASE_URL`. Keep files gitignored; do not commit secrets. |
| **Railway CLI** | From `backend/` with the project linked (`railway link`), run commands via `railway run …` so injected variables match the linked environment ([Railway CLI](https://docs.railway.com/guides/cli)). |
| **Local Postgres** | Run Postgres in Docker or locally; set `DATABASE_URL` for Alembic and the app to that instance. |

For **Alembic** and **SQLAlchemy**, use the same `DATABASE_URL` convention locally and in production so migrations target the same engine shape.

### 6. SQLAlchemy driver URL (optional tweak)

Railway’s `DATABASE_URL` typically starts with `postgresql://`. That works with many stacks. If you standardize on **psycopg v3** with SQLAlchemy, you may need to normalize to:

`postgresql+psycopg://…`

(same user, password, host, port, database, and query string) so the engine uses the intended driver. If connection errors mention the driver or scheme, adjust in `config.py` or Alembic `env.py` once, centrally.

### 7. After the app uses the database

When FastAPI and Alembic are wired up:

- Run **`alembic upgrade head`** against production (or a release-phase command on Railway) as described in **Implementation sequence** below—do not rely on `create_all()` alone in production.
- If you use [`scripts/push_env_to_railway.py`](../../scripts/push_env_to_railway.py) to sync `backend/.env.test` → Railway, remember it pushes **every** non-empty key from that file—avoid storing production **`DATABASE_URL`** in a file you sync; prefer **variable references** in the Railway UI for the deployed API, and keep real URLs only in gitignored local env files.

## Why this stack for “future in perspective”

- **SQLModel** keeps one model shape for DB rows and API boundaries where you want overlap, while still allowing full SQLAlchemy Core and relationship patterns when things get relational.
- **Alembic** gives reproducible environments (local, CI, Railway deploy) and safe roll-forward/rollback discipline as you add users, connectors, reports, and context.
- **Railway Postgres + Python** is the same proven path as any other Postgres host; you are not locked in—only the connection string changes if you ever move hosts.

## Auth-first schema (Supabase-inspired, minimal)

Supabase’s `auth.users`/`identities` split is a good pattern: keep a stable internal user row, and keep provider-specific identity details separate. For Duct today, we only need Google sign-in, so we keep this lean.

### Tables for phase 1

1. **`users`** (internal user record)
   - `id` UUID PK
   - `email` text unique not null
   - `full_name` text null
   - `avatar_url` text null
   - `created_at` timestamptz not null default now()
   - `updated_at` timestamptz not null default now()
   - `last_sign_in_at` timestamptz null

2. **`auth_identities`** (provider mapping, Supabase-style)
   - `id` UUID PK
   - `user_id` UUID FK -> `users.id` (cascade delete)
   - `provider` text not null (`google` only for now)
   - `provider_user_id` text not null (Google `sub`)
   - `provider_email` text null
   - `raw_profile` JSONB null (small subset of Google claims if needed)
   - `created_at` timestamptz not null default now()
   - `updated_at` timestamptz not null default now()
   - unique index on (`provider`, `provider_user_id`)

3. **`oauth_states`** (durable anti-CSRF + PKCE state)
   - `state` text PK
   - `flow` text not null (`signin_google`, `connector_google_ads`)
   - `code_verifier` text null
   - `issued_at` timestamptz not null default now()
   - `expires_at` timestamptz not null
   - `consumed_at` timestamptz null
   - index on `expires_at`

### What we intentionally do not add yet

- No workspaces/organizations table yet.
- No connector credential storage yet.
- No report metadata/artifacts tables yet.
- No refresh-token session store (JWT remains stateless for now).

## Current repo constraints

- `backend/pyproject.toml` may not yet list `sqlmodel`, `sqlalchemy`, `alembic`, or a Postgres driver—add them when implementing.
- Poetry `packages` uses explicit includes (`routes`, `service`, …)—any new top-level package (e.g. `db`, `models`) must be added to `[tool.poetry.packages]` so imports work when installed.

## Suggested backend layout (when implementing)

| Area | Responsibility |
|------|----------------|
| `backend/config.py` | `database_url: str` from env (Railway’s `DATABASE_URL`; optional `postgresql+psycopg://` style for SQLAlchemy) |
| `backend/db/` | Engine factory, session maker, `get_session` dependency for FastAPI (or async equivalent if you standardize on async DB access) |
| `backend/models/` | SQLModel `table=True` models; relationships and indexes defined here |
| `backend/alembic.ini` + `backend/alembic/` | Alembic env; `target_metadata = SQLModel.metadata` after importing all models so autogenerate sees every table |

**Alembic `env.py` requirement:** import all model modules (or a single `models/__init__.py` that re-exports them) before setting metadata, otherwise autogenerate will miss tables.

## Sync vs async sessions

The codebase uses mixed sync and async route handlers. A practical default is:

- **Start with a sync engine + `Session` + `Depends(get_session)`** for the shortest path and straightforward Alembic usage; or
- If you prefer **async everywhere** for new DB code, use SQLAlchemy 2 async + asyncpg (or async psycopg3) and ensure session lifecycle is correct per request.

Pick one style for new DB access and avoid mixing both in the same codebase long term.

## Implementation sequence

1. **Railway:** Create Postgres, wire `DATABASE_URL` into the backend service.
2. **Dependencies:** Add `sqlmodel`, `alembic`, and a Postgres driver (e.g. `psycopg[binary]` for sync SQLAlchemy URLs).
3. **Scaffold:** `db/` + `models/` + `alembic init` under `backend/`, wire `env.py` to `SQLModel.metadata`.
4. **First migration:** Create the first real tables with **autogenerate only** (`alembic revision --autogenerate -m "..."` then review by hand). Do not hand-write revision files.
5. **CI / deploy:** Run `alembic upgrade head` as part of the Railway release command or a one-off migration job; document in `docs/engineering/deployment-cloudflare-railway.md` when added.

## Migration workflow policy (always)

- Revisions must be machine-generated with Alembic autogenerate.
- Human review is still required before merge/deploy.
- Recommended command wrapper in this repo:
  - `python backend/scripts/migrations.py revision -m "<message>"`
  - `python backend/scripts/migrations.py upgrade`
  - `python backend/scripts/migrations.py check-pending`

## Domain sequencing

1. Ship auth-only tables: `users`, `auth_identities`, `oauth_states`.
2. Update sign-in callback to upsert user/identity from Google claims (`sub`, `email`, `name`, `picture`).
3. Replace in-memory OAuth state in both auth routes with `oauth_states` and enforce expiry + one-time consume semantics.
4. After sign-in persistence is stable, add connector credentials (encrypted), then report metadata/artifacts.

## Security note (connectors)

Encrypt refresh tokens at rest; enforce **application-level** tenant scoping on every query (Railway Postgres does not give you Supabase RLS unless you add policies by hand—the app layer must be correct).

## Alternative hosts (context)

**Supabase** and **Neon** remain valid swaps—same SQLModel + Alembic story, different connection string and ops. **Cloudflare D1** is a poor primary store while FastAPI on Railway owns writes unless you re-architect access patterns.

## Related docs

- [Deployment: Cloudflare + Railway](./deployment-cloudflare-railway.md)
- [OAuth authentication plan](./oauth-authentication-plan.md)
- MVP direction: `docs/mvp/mvp-plan.md` (historical Supabase mention; this doc supersedes the host choice for the current stack)
