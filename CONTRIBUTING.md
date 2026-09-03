# Contributing to Duct

Thanks for looking. Duct is a monorepo with four independent stacks, so the
first thing to work out is which one your change lives in.

| Path | Stack | Runs on |
|------|-------|---------|
| `backend/` | Python 3.12, FastAPI, SQLModel, Alembic | Railway, or as a local sidecar |
| `app/` | Next.js App Router (JS, not TS) | Cloudflare Workers |
| `desktop/` | Tauri v2 (Rust shell) | macOS, Windows, Linux |
| `site/` | Static HTML/CSS/JS, no build step | Static hosting |

Each area has its own `AGENTS.md` with the conventions that actually apply
there (`CLAUDE.md` beside it is a symlink to the same file). **Read the one for
the directory you are editing** — backend conventions do not apply to `site/`,
and vice versa.

## Before your first commit

Enable the secret-scanning pre-commit hook. This repository is public; a
credential pushed here is public the instant it lands, and a force-push does
not unpublish it.

```bash
git config core.hooksPath .githooks
brew install betterleaks        # or: go install github.com/betterleaks/betterleaks@latest
```

Without `betterleaks` installed the hook warns and passes rather than blocking
you — CI enforces it regardless.

## Setup

**Backend**

```bash
cd backend
poetry install --with dev
cp .env.example .env.local        # fill in only what your change needs
poetry run uvicorn server:app --reload --port 8002
```

Every setting in `config.py` has a default, so a missing variable never fails
loudly — the feature it powers just silently does nothing. That is why
`.env.example` is test-enforced (see below).

**App**

```bash
cd app
npm install
npm run dev                       # http://localhost:3003
```

Dev ports are pinned deliberately: Next on **3003**, FastAPI on **8002**,
static site on **8090**.

**Site**

```bash
python3 -m http.server 8090 --directory site
```

## Checks your PR has to pass

```bash
make check            # everything CI runs, from the repo root
make check-backend    # or just the area you touched
make test             # backend tests alone — the fastest useful signal
```

`make check` runs the same commands as the workflows in `.github/workflows/`.
If the two disagree, CI is right and the `Makefile` is wrong — fix it there.
Run `make help` for the full list.

`-m "not live"` deselects tests that call real vendor APIs. They are already
deselected by `addopts`; the flag keeps it visible.

The security audit fails the build **only** on CRITICAL findings. If you hit a
false positive, prefer changing the code so the pattern no longer matches over
adding a baseline entry — baseline fingerprints are keyed on
`severity|title|filepath`, so suppressing one finding blinds the scanner to
every future finding of that kind in that file.

## Conventions worth knowing before you write code

These are the ones that cost the most to get wrong. The area `AGENTS.md` files
have the rest.

- **Backend: authorization is membership, not ownership.** `DUCT_API_KEY` is
  shipped to the browser and is not an authorization boundary. Any endpoint
  touching a project-scoped row needs `get_current_user` *plus* a membership
  check — `get_project_for_user` for a project named in the request,
  `get_project_row_for_user` for a row addressed by its own id. Return 404, not
  403, so the response is not an oracle. `routes/artifacts.py` is the reference.
- **Backend: adding a setting means updating `.env.example`.**
  `tests/test_env_example.py` enforces it for anything credential-shaped and
  catches renames. An undocumented setting is undiscoverable, not broken.
- **Backend: no framework imports in domain code.** Tool bodies, prompts,
  schemas and scoring are plain Python; framework imports live only in runners
  and binders. `tests/test_harness_boundaries.py` enforces this and holds the
  allowlist — adding a file to it is a deliberate act, not a fix for a red test.
- **Backend: use the shared helpers.** `utils/dates.py` (never
  `datetime.now()`/`utcnow()` — every persisted timestamp is UTC-aware),
  `utils/strings.py`, `utils/formatting.py`, `service/rest.py`,
  `service/memory.py`. Each replaced a family of divergent local copies.
- **Backend: JSON columns use `models/columns.py::json_column()`**, never
  `postgresql.JSONB` directly — raw JSONB will not compile on SQLite, which is
  what the desktop sidecar runs on.
- **Migrations are additive and reversible.** Always write a working
  `downgrade`. Nothing runs migrations automatically.
- **Site: follow [`site/AGENTS.md`](site/AGENTS.md).** Canonical links,
  shared CSS, sitemap entries and GTM handling all have hard rules there.

## Pull requests

- Branch from `main`. One concern per PR.
- Commit subjects are lowercase, imperative, and scoped:
  `fix(connectors): a saved provider key is not a data source`.
- Explain *why* in the body. The codebase's comments carry reasoning rather
  than description, and commit messages are held to the same bar.
- Update the docs next to the code you changed, including the relevant
  `AGENTS.md` if you changed a convention.
- Add a line to `CHANGELOG.md` under `## [Unreleased]` if the change is one a
  user would notice. `.github/scripts/release-notes.mjs` puts that section
  straight into the GitHub release, so what you write there is what they read.

## Reporting security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Licensing of contributions

Duct is MIT licensed. By contributing you agree that your contribution is
licensed under the same terms. See [LICENSE](LICENSE), including its exceptions
for third-party documentation and trademarks.
