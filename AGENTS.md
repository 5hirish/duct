# Duct — monorepo agent instructions

Monorepo for [getduct.ai](https://getduct.ai). Duct connects a product and
marketing stack and synthesises cross-tool insights into briefs and alerts.

**Human contributors: start with [CONTRIBUTING.md](CONTRIBUTING.md).** This file
is the same information for coding agents, plus the conventions worth knowing
before writing a line.

## How the instruction files work

`AGENTS.md` is canonical in every directory. `CLAUDE.md` beside it is a symlink
to the same file — edit `AGENTS.md` and both tools see the change. The same
pattern already applies to skills: `.cursor/skills/<name>/SKILL.md` symlinks to
`.claude/skills/<name>.md`.

There was previously a root `AGENTS.md` holding auto-accumulated "learned
preferences" separate from `CLAUDE.md`. Two files describing one repo drift, and
that one did — it still named modules that had been deleted. One file per
directory, written by hand, is the rule now. **Do not append machine-generated
preference logs to these files.** If a preference is worth keeping it is worth
writing as a rule, in the directory it applies to.

Instructions are local to the directory they describe. Read the `AGENTS.md` for
the area you are editing; site conventions do not apply to `backend/`.

## Areas

| Path | Stack | Instructions |
|------|-------|--------------|
| `backend/` | Python 3.12, FastAPI, SQLModel, Alembic | [`backend/AGENTS.md`](backend/AGENTS.md) |
| `app/` | Next.js App Router (JS, not TS), Cloudflare Workers | [`app/AGENTS.md`](app/AGENTS.md) |
| `desktop/` | Tauri v2 shell; OS-keychain BYO provider keys | [`desktop/AGENTS.md`](desktop/AGENTS.md) |
| `site/` | Static HTML/CSS/JS, no build step | [`site/AGENTS.md`](site/AGENTS.md) |
| `docs/` | Engineering plans and reference material | [`docs/README.md`](docs/README.md) |
| `scripts/` | Deploy/env plumbing and repo hygiene | below |

Product strategy, GTM and deployment runbooks live in a separate private
repository. Documents here occasionally cite them; those citations state their
reasoning inline, so a missing link never blocks understanding the code.

## Setup and verification

```bash
make setup          # dependencies for every area
make check          # everything CI runs on a PR
make check-backend  # or just the area you touched
make test           # backend tests alone — the fastest useful signal
```

`make check` runs the same commands as `.github/workflows/*.yml`. **Run it
before proposing a change.** If it disagrees with CI, CI is right and the
`Makefile` is wrong — fix the `Makefile`.

Dev ports are pinned deliberately, not framework defaults, so they stay clear of
other local stacks: Next.js **3003**, FastAPI **8002**, static site **8090**.
Only one process can bind a port — `Address already in use` on 8090 usually
means a leftover `dev_server.py`.

## Non-negotiables

These are the ones that cost the most to get wrong. Each is enforced by a test,
so you will find out — the point of listing them is that finding out early is
cheaper.

- **Authorization is membership, not ownership, and `validate_api_key` is not a
  boundary.** `DUCT_API_KEY` ships to the browser as
  `NEXT_PUBLIC_DUCT_API_KEY`; it proves "this is the Duct app", never "this
  caller owns that row". Any route touching a project-scoped row needs
  `get_current_user` **plus** a membership check, and returns 404 (not 403) for
  a non-member so the response is not an oracle.
  Enforced by `backend/tests/test_route_auth_boundaries.py`.
- **Domain code imports no agent framework.** Framework imports live only in
  runners and binders. Enforced by `backend/tests/test_harness_boundaries.py`,
  which holds the allowlist — adding a file to it is a deliberate act, not the
  fix for a red test.
- **A new setting means updating `backend/.env.example`.** Every field in
  `Configs` has a default, so a missing variable never fails loudly; the feature
  silently does nothing. Enforced by `backend/tests/test_env_example.py`.
- **Never commit a credential.** This repository is public and its history is
  public with it; a force-push does not unpublish, and the only real remedy is
  rotation. Install the pre-commit scanner once per clone:
  `git config core.hooksPath .githooks` (plus `brew install betterleaks`).

## Helper scripts (`scripts/`)

Check here before hand-rolling env or secret plumbing:

- `push_env_to_railway.py` — push a dotenv file to the linked Railway service
  (`--file backend/.env.prod`; default `backend/.env.test`). Sets each var with
  `--skip-deploys`, then redeploys unless `--no-redeploy`. Needs `railway login`
  and `railway link`.
- `push_app_env_to_cloudflare.py` — load an app env file, then OpenNext build +
  `wrangler deploy`. `NEXT_PUBLIC_*` are baked at build time, so an env change
  needs this, not just a dashboard edit.
- `push_env_to_github.py` — push allowlisted keys from gitignored `.env.test`
  files to GitHub repo secrets/variables.
- `bootstrap_env_test.sh` — copy local dev env files to the gitignored
  `.env.test` targets.
- `envfile.py` — shared dotenv parser used by the above.
- `security/audit.py`, `security/leak_scan.py` — repo hygiene, both run in CI.

Env file map: `backend/.env.local` = local dev (also the database proxy URL for
Alembic), `backend/.env.prod` = deployment source of truth, `.env.test` =
gitignored staging for the push scripts. All are gitignored — never commit one.

## Working style

[`STYLE.md`](STYLE.md) is the companion to this file. This one holds the rules
that must not break; that one holds what good code looks like once it works,
organised by principle — modularity, reusability, named constants over magic
strings, error handling, comments, readability, design patterns — plus a
close-on-touch list of the places the tree currently falls short. Read it
before writing in an area you have not written in before.

- One concern per change. Explain *why* in the commit body; the diff shows what.
- Comments in this codebase carry reasoning, not description. Match that — a
  comment restating the line below it is noise, one naming the failure that
  motivated the line is why the code survives.
- **Attack your own diff before calling it done.** Read it back as though
  someone else wrote it and you are looking for the reason to reject it. The
  author catches most of what a reviewer would, and catches it for free.
- **Then read the diff against its neighbours.** A set of individually
  defensible changes that together dissolve an architecture is the specific way
  agent-accelerated codebases fail: every change argues for itself and nothing
  argues for the whole. Ask what the third change of this shape would do to the
  module. If the answer is "we would have to reorganise", do it now, while it is
  still one file.
- Update the docs next to the code you changed, including the area `AGENTS.md`
  if you changed a convention.
- Deployment happens through CI on merge to `main`. Do not deploy from a CLI.
