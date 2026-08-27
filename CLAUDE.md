# Duct — Claude Code monorepo instructions

Monorepo for [getduct.ai](https://getduct.ai).

## Top-level areas

- `site/` — static marketing site
- `backend/` — Python reporting and synthesis MVP
- `app/` — Next.js App Router report viewer and agent interface (Cloudflare Workers)
- `desktop/` — Tauri v2 desktop shell (loads the hosted app; OS-keychain BYO provider keys)
- `docs/` — strategy, GTM, MVP, engineering, design, guides ([`docs/README.md`](docs/README.md))

## Helper scripts (`scripts/`)

Deploy/env plumbing shared across areas — check here before hand-rolling env or secret pushes:

- `push_env_to_railway.py` — push a dotenv file to the linked Railway service (`--file backend/.env.prod`; default `backend/.env.test`). Sets each var via `railway variable set --skip-deploys`, then redeploys unless `--no-redeploy`. Needs `railway login` + `railway link`.
- `push_app_env_to_cloudflare.py` — load an app env file, then OpenNext build + `wrangler deploy` (NEXT_PUBLIC_* are baked at build time, so env changes need this, not just a dashboard edit).
- `push_env_to_github.py` — push allowlisted keys from gitignored `.env.test` files to GitHub repo secrets/variables (reads `backend/.env.test` + `app/.env.test`).
- `bootstrap_env_test.sh` — copy local dev env files to the gitignored `.env.test` targets.
- `envfile.py` — shared dotenv parser used by the scripts above.
- `security/` — `audit.py`, `leak_scan.py` repo hygiene checks.

Env file map: `backend/.env.local` = local dev (also the Railway DB proxy URL for alembic), `backend/.env.prod` = Railway source of truth, `.env.test` files = gitignored staging for the push scripts. All are gitignored — never commit them.

## Monorepo guidance

- Keep instructions local to the directory they describe.
- Prefer directory-level `CLAUDE.md` files in monorepo areas with different stacks or workflows.
- When editing files under `site/`, follow `site/CLAUDE.md`.
- When editing files under `site/`, also follow `site/AGENTS.md`.
- Do not assume site conventions apply to `backend/` or `app/`.
- Cursor Agent Skills live under `.cursor/skills/<name>/SKILL.md` as symlinks to `.claude/skills/<name>.md`; change the `.claude` file to update both tools.
