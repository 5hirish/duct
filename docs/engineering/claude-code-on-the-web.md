# Claude Code on the web, on this repo

**Author:** Shirish Kadam · **Updated:** 2026-10-26

Run a cloud Claude Code session against this monorepo in about five minutes:
connect GitHub once, paste one setup script, start tasks from your terminal.
Sessions run on Anthropic-managed machines that clone the repo fresh, so only
what is committed comes along.

## At a glance

- **Connect once.** `/web-setup` syncs your GitHub token to your Claude
  account. Nothing is needed on the repo side.
- **Install once per environment.** A cached setup script runs the Poetry and
  npm installs; later sessions start with dependencies on disk.
- **Nothing local comes along.** Your user-level Claude files, `.env*` files
  and locally added MCP servers stay on your machine.
- **No secrets, no deploys.** There is no secrets store, and deploys go
  through CI only.

## Set up and start a session

**Before you start:** push the branch you want to work on. The cloud clones
the GitHub remote, not your disk.

1. **Connect GitHub.** Run `/web-setup` in a local Claude Code terminal. The
   Claude GitHub App is only required for Auto-fix PR.
2. **Create the environment** at claude.ai/code and paste this into its
   Setup script field. The image has Python, Poetry and Node but runs no
   installs, so the script does, and its result is cached.

   ```bash
   #!/bin/bash
   ( cd backend && poetry install ) &
   ( cd app && npm ci ) &
   wait
   ```

   The default Trusted network level already allows PyPI, npm and the Poetry
   and Cloudflare registries, so no network configuration is needed.

3. **Start a task** from the terminal with
   `claude --remote "run the backend tests and fix failures"`, or from the
   web UI.
4. **Follow it** with `/tasks`. Pull a session back to your machine with
   `claude --teleport` or `/teleport`.
5. **Finish with a pull request** from the web session. Merging to `main`
   deploys through CI, as always.

**Check it worked:** a new session starts with dependencies already installed
and runs `make test` without an install step.

## A setup script, not a SessionStart hook

Environment caching snapshots the setup script's result once, so every later
session starts with dependencies on disk. A committed SessionStart hook is not
cached: it would re-run every session, and fire in every contributor's local
sessions as well.

> **Gotcha:** the snapshot rebuilds only when the script changes or after
> about 7 days, not when `poetry.lock` or `package-lock.json` change. After a
> dependency bump the cached environment is one install behind. Ask the session
> to re-run the installs, or edit the script trivially to bust the cache.

## What comes along, and what stays home

| Comes along (committed) | Stays on your machine |
|---|---|
| [`CLAUDE.md`](../../CLAUDE.md) and the area files | Your user-level `CLAUDE.md`, skills, agents and commands |
| [`.claude/rules/`](../../.claude/rules/) and [`.agents/skills/`](../../.agents/skills/) | `.claude/settings.local.json` |
| The committed `.mcp.json` | MCP servers added with `claude mcp add` |
| | Every `.env*` file |

## Secrets never go in the environment

There is no secrets store. Anything typed into the environment's env-var field
is visible to anyone who can edit that environment, so production secrets never
go there, including the contents of `backend/.env.prod`.

Most cloud tasks (refactors, tests, fixes) need no credentials. One that truly
needs a database or an API gets a dev or branch credential, in dotenv format:
one `KEY=value` per line, no quotes.

## Deploys stay in CI

A cloud session opens a pull request. Merging to `main` triggers the Cloudflare
Workers and Railway deploys that already exist; the runbook is in a separate
private repository. Never add a Cloudflare or Railway deploy command to the
setup script, and never ask a session to deploy: two paths to production means
double deploys.

## Go deeper

- Claude Code on the web: [overview and cloud environment](https://code.claude.com/docs/en/claude-code-on-the-web), [quickstart](https://code.claude.com/docs/en/web-quickstart)
- [Setup scripts vs. SessionStart hooks](https://code.claude.com/docs/en/claude-code-on-the-web#setup-scripts-vs-sessionstart-hooks)
- [Network access and the default allowlist](https://code.claude.com/docs/en/claude-code-on-the-web#network-access)
