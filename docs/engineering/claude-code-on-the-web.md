# Runbook: Claude Code on the web

**What this doc is for:** Running [Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web) (cloud sessions at [claude.ai/code](https://claude.ai/code)) against this monorepo. Cloud sessions run on Anthropic-managed VMs that clone the repo fresh, so anything that isn't committed (your local `~/.claude`, `.env*` files, `claude mcp add` servers) is **not** present. This is the one place to come back to for the setup-script text and the account-connect step.

**Stack reminder:** [`backend/`](../../backend/) is Python + **Poetry**; [`app/`](../../app/) is Next.js on Cloudflare Workers + **npm**. The cloud image ships Python, poetry, and Node pre-installed but does not run our installs — that's what the setup script below is for.

---

## Quick reference

| Goal | What to do |
|------|------------|
| **Connect GitHub** (one-time, account-level) | Run `/web-setup` in the terminal to sync your `gh` token to your Claude account. (Or install the [Claude GitHub App](https://github.com/apps/claude) — only *required* for Auto-fix PR.) Nothing repo-side needed; the repo is already on GitHub. |
| **Install deps in the cloud** | Paste the [setup script](#setup-script) into the environment's **Setup script** field in the web UI. Result is cached, so later sessions start fast. |
| **Start a cloud task from the terminal** | `claude --remote "run the backend tests and fix failures"` (clones the current branch's GitHub remote — **push local commits first**). |
| **Watch / pull a session back** | `/tasks` to monitor; `claude --teleport` (or `/teleport`) to continue a cloud session locally. |
| **Open a PR** | From the web session UI. **Do not deploy from the session** — see [Deploys stay in CI](#deploys-stay-in-ci). |

---

## Setup script

We use a **setup script** (web UI, environment-scoped, cached) rather than a committed `SessionStart` hook. Rationale: the two installs (`poetry install` + `npm ci`) benefit from [environment caching](https://code.claude.com/docs/en/claude-code-on-the-web#environment-caching) — they run once, get snapshotted, and every later session starts with deps on disk. A `SessionStart` hook is not cached (re-runs every session) and would also fire in every contributor's *local* sessions.

Paste this into the environment's **Setup script** field:

```bash
#!/bin/bash
( cd backend && poetry install ) &
( cd app && npm ci ) &
wait
```

The default **Trusted** network level already allows PyPI, npm, and the Poetry/Cloudflare registries, so installs work with no network config.

**Cache caveat:** the snapshot only rebuilds when you edit the setup script or after ~7 days — **not** when `poetry.lock` / `package-lock.json` change. Right after a dependency bump the cached env may be one install behind; just ask the session to re-run `poetry install` / `npm ci`, or make a trivial edit to the script to bust the cache.

---

## What carries over vs. what doesn't

| Carries over (committed) | Does **not** carry over |
|---|---|
| [`CLAUDE.md`](../../CLAUDE.md) + area files ([`backend/`](../../backend/), [`app/`](../../app/), [`site/`](../../site/)) | Your user `~/.claude/CLAUDE.md`, skills, agents, commands |
| [`.claude/rules/`](../../.claude/rules/), [`.claude/skills/`](../../.claude/skills/) | `.claude/settings.local.json` (local-only) |
| A committed `.mcp.json`, if present | MCP servers added via `claude mcp add` (write to local config) |
| | **`.env*` files** — see [Secrets](#secrets) |

---

## Secrets

⚠️ `.env*` files are **not** uploaded, and there is **no secrets store yet**. Anything entered in the environment's env-var field is **visible to anyone who can edit that environment**, so **never paste prod secrets** (e.g. the contents of [`backend/.env.prod`](../../backend/)) there.

Most cloud tasks (refactors, tests, fixes) don't need credentials. If a task genuinely needs a DB/API, supply a **dev or branch** credential — not prod. Env vars use `.env` format, one `KEY=value` per line, **no quotes**.

---

## Deploys stay in CI

Our standing rule holds in cloud sessions: **deploys go through CI/CD only** (deployment runbook (duct-cloud, private)). A cloud session should open a PR; merging to the watched branch triggers the existing Cloudflare Workers / Railway deploys. **Do not** add `wrangler deploy` (or Railway pushes) to the setup script or ask a session to deploy — that risks double deploys.

---

## Official references

- Claude Code on the web: [overview & cloud environment](https://code.claude.com/docs/en/claude-code-on-the-web), [quickstart](https://code.claude.com/docs/en/web-quickstart)
- [Setup scripts vs. SessionStart hooks](https://code.claude.com/docs/en/claude-code-on-the-web#setup-scripts-vs-sessionstart-hooks)
- [Network access & default allowlist](https://code.claude.com/docs/en/claude-code-on-the-web#network-access)
