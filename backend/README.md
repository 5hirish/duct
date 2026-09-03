# Duct Backend

The FastAPI service: connectors, normalization, the agent runners, memory, and
staged execution. It produces JSON — the app owns rendering.

The same codebase runs in two shapes. On a server it is a normal FastAPI app on
Postgres. On a laptop it is a PyInstaller-frozen sidecar the desktop shell
spawns, bound to loopback on an OS-assigned port, on SQLite in a per-user data
directory. `local_server.py` is that second entry point.

## Layout

| Path | What it holds |
|---|---|
| `routes/` | HTTP surface. `namespace.py` assembles every router and documents the auth gates |
| `service/` | Connectors, credentials, membership, memory, execution, storage |
| `agents/` | Agent types (`insights`, `audit`, `content`, …), each with its own goals, prompts, schema and versioned runners |
| `agents/core/ports/` | The harness boundary — read this before touching a framework import |
| `models/` | SQLModel tables |
| `alembic/` | Migrations |
| `utils/` | Shared date, string and formatting helpers |
| `tests/` | Including the boundary gates listed below |

## Local run

```bash
poetry install --with dev
cp .env.example .env.local
poetry run uvicorn server:app --reload --port 8002
```

Or `make serve-backend` from the repo root.

**Python 3.12 or 3.13** (`>=3.12,<3.14`). `.python-version` pins 3.12 for pyenv;
CI uses 3.12.

`GET /` returns public API metadata; `GET /health` is the liveness check.
OpenAPI (`/docs`, `/openapi.json`) is **off** unless `EXPOSE_OPENAPI_DOCS=true`.
With docs on, `OPENAPI_DOCS_BASIC_PASSWORD` (and optional
`OPENAPI_DOCS_BASIC_USER`) puts Basic auth in front of them.

## Configuration

`config.py` is the source of truth for what the backend reads; `.env.example` is
its documentation, and `tests/test_env_example.py` keeps the two honest.

Worth knowing before adding a setting: **every field in `Configs` has a
default.** A missing variable therefore never fails — the feature it powers
silently does nothing, which makes an undocumented setting undiscoverable rather
than broken. Anything credential-shaped must appear in `.env.example`, and a
rename has to happen in both places.

## Migrations

Alembic owns the schema, and migrations are applied deliberately — nothing runs
them automatically on deploy.

```bash
python scripts/migrations.py revision -m "..."   # always autogenerate
python scripts/migrations.py upgrade
python scripts/migrations.py check-pending
```

Never hand-write a revision file. Autogenerate diffs the models against the live
schema, which is the step that catches a column you added to a model and forgot
to migrate. Review what it produces before applying — it is a good first draft
and a poor final one, particularly for renames and server defaults. New models
must be imported in `models/__init__.py` or autogenerate cannot see them. Always
provide a working `downgrade`.

## Checks

```bash
make check-backend     # ruff + pytest, exactly what CI runs
make test              # pytest alone
```

Four gates are worth knowing about, because they fail on properties rather than
on behaviour and the fix is usually not "edit the test":

- `test_route_auth_boundaries.py` — every project-scoped route resolves a user,
  and every ungated `/api` route is declared with a reason.
- `test_harness_boundaries.py` — no agent-framework import outside a declared
  adapter.
- `test_env_example.py` — `config.py` and `.env.example` agree.
- `test_deepagents_harness.py` — the upgrade gate for the exact `deepagents`
  pin, which changes behaviour in minor releases.

## Boundaries

- **`validate_api_key` is not an authorization boundary.** `DUCT_API_KEY` ships
  to the browser as `NEXT_PUBLIC_DUCT_API_KEY`. Project access is by membership
  (`service/membership.py`), and a non-member gets 404, not 403.
- **This is a data pipeline, not a renderer.** No HTML leaves the backend.
- **No marketing site files here**, and no frontend code.

## Production

Railway (Railpack + Poetry), with the service root set to `backend` so
[`railway.json`](railway.json) applies. Deploys run from CI on merge to `main`.

Conventions: [`AGENTS.md`](AGENTS.md) (`CLAUDE.md` symlinks to it).
