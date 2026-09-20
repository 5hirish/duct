# Duct — monorepo agent instructions

Monorepo for [getduct.ai](https://getduct.ai). Duct connects a product and
marketing stack and synthesises cross-tool insights into briefs and alerts.

**Human contributors: start with [CONTRIBUTING.md](CONTRIBUTING.md).** This file
is the same information for coding agents, plus the conventions worth knowing
before writing a line.

## How the instruction files work

`AGENTS.md` is canonical in every directory. `CLAUDE.md` beside it is a symlink
to the same file — edit `AGENTS.md` and both tools see the change.

Skills follow the same one-source rule, against the cross-client Agent Skills
convention: the skill lives at `.agents/skills/<name>/SKILL.md` and each
harness's own directory holds a symlink to that folder.

```
.agents/skills/<name>/SKILL.md   # canonical — edit here
.claude/skills/<name>  -> ../../.agents/skills/<name>
.cursor/skills/<name>  -> ../../.agents/skills/<name>
```

Codex, Copilot, OpenCode and Zed read `.agents/skills/` directly and need no
symlink — Zed's project skill root *is* `<worktree>/.agents/skills/`, so every
skill here was already a Zed skill before Zed was ever opened on this repo.
Claude Code and Cursor scan only their own directories, but both follow a
symlinked skill folder. A skill **must** be a directory holding a file
named exactly `SKILL.md`: the flat `.claude/skills/<name>.md` layout this
replaces was not a supported form, so Claude Code discovered none of these
skills at all. Adding one means creating the directory and both symlinks —
copies drift, so never copy.

MCP servers get no such shared file, because none can exist: VS Code names the
key `servers` rather than `mcpServers`, Codex is TOML, Zed calls them
`context_servers` and puts them among its other settings, and Cursor expands
`${env:VAR}` where Claude Code expands `${VAR}`. The project list lives in
`.mcp.json`, which Claude Code prompts to trust on first use; `.cursor/mcp.json`
and the `context_servers` block of `.zed/settings.json` are the generated
copies of the same set. Credentials in the first two are `${VAR}` references;
Zed expands nothing, so a server needing a token carries no `env` block there
and reads it from the shell Zed was launched from. **Never write a real token
into any of them** — this repository is public.

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
| `design/` | Storyboards (Claude Design) and the Remotion film | [`design/motion/README.md`](design/motion/README.md) |

Product strategy, GTM and deployment runbooks live in a separate private
repository. Documents here occasionally cite them; those citations state their
reasoning inline, so a missing link never blocks understanding the code.

## Scope and prioritization

Development here is 100% agent-executed, which flips the usual constraint:
implementation was never the scarce resource, so a wrong feature costs almost
nothing to build and a permanent maintenance surface to carry afterward —
another line in `.env.example`, another test, another thing `STYLE.md`'s
review pass has to hold up against everything else. Before starting anything
beyond a small fix — a new endpoint, connector, setting, or UI surface — run
it through the **`prioritize`** skill (`.agents/skills/prioritize/`). It's a
four-question bar (whose problem specifically, what it costs forever, is
there a cheaper way to test it, does it match what Duct actually is) that
ends in a scoped GitHub issue with a written spec, or an explicit "not now,
because" recorded in a closed issue — either is a finished outcome, not just
the first one.

- The live roadmap is the GitHub Project
  ([5hirish/projects/10](https://github.com/users/5hirish/projects/10)), not
  a document in this repo. Its `Priority` field (`P0`/`P1`/`P2`) and each
  issue's milestone (the actual dated deadline, not the Project's title) are
  the source of truth for what's next — check it rather than inferring
  priority from the conversation alone.
- Scope proposed on an agent's own initiative — not asked for by name — goes
  through `prioritize` before code, not after. A well-argued feature nobody
  asked for is still scope creep, however clean the diff.

## Before you start: git hygiene

**Check where this branch stands before writing a line.** Not after, not when
something looks wrong:

```bash
scripts/sync_main.sh                             # fast-forwards local main, reports this branch
git rev-list --left-right --count origin/main...HEAD   # left = missing here, right = only here
```

The SessionStart hook already runs the first one and puts its answer in the
session context. **That warning is a stop-and-fix, not a note.** On 2026-09-20
a session read "47 commit(s) behind origin/main", started work anyway, and the
branch turned out to be fully merged already: two days of shipped UI work
(the shimmer, artifact thumbnails, the folding activity rail) was simply not in
the working tree, and the session's first theory was a botched PR merge.

What the two numbers mean:

- **right is 0** — every commit here is already on `origin/main`. The branch is
  finished. Do not merge main into it; branch off `origin/main` instead.
- **left is large** — the tree is stale. Anything you conclude about a file,
  a feature or a bug is an answer about the past. Rebase or re-branch first.
- Compare against `origin/main`, **never local `main`**, and never before a
  successful `git fetch`. A stale ref answers wrong without saying so.

**Never create a directory beside the repo.** No `../duct-<something>` clone,
no sibling worktree, nothing outside this tree. Work on a branch in this
checkout. A worktree is justified only when the user's dev servers must keep
running on another branch, and then it goes *inside*, gitignored, and is
removed the moment its branch merges:

```bash
git worktree add .worktrees/<name> <branch>   # inside, never ../duct-<name>
git worktree remove .worktrees/<name>         # the same day the PR merges
git worktree list                             # "prunable" means someone forgot
```

Why: on 2026-09-20 `duct-splash` and `duct-zed` sat beside the repo holding
**1.7G** of duplicated code whose branches had merged the day before, on a
laptop with 8G of RAM and an already-full swap. Worse than the disk, a stale
sibling tree is a stale tree: grep it and you get last week's answer with no
sign that it is old, which is the same failure as a stale branch, one
directory over.

One more trap specific to this repo: the agent sandbox cannot write `.mcp.json`,
`.vscode/` or `.claude/skills/`, so a branch switch that touches them **fails
half-done** — the index and working tree move, `HEAD` does not. If `git status`
suddenly shows the whole diff of another branch as staged, that is this, not a
broken repository. `git symbolic-ref HEAD refs/heads/<branch>` finishes the
switch, and those few paths need restoring from outside the sandbox.

## Git practice in a shared repository

[`CONTRIBUTING.md`](CONTRIBUTING.md) holds the conventions themselves: branch
from `main`, one concern per PR, lowercase scoped commit subjects, *why* in the
body, the `betterleaks` pre-commit hook. Read it once; it applies to agents
exactly as written. What follows is what an agent gets wrong that a human
contributor does not.

This repository is public, several people and several agents commit to it, and
`main` deploys. History is a thing other people read and depend on, not a
scratchpad.

- **Ask before `git commit`, `git push` or `gh pr create`. Every time.** Make
  the change, summarise it, stop. Approval for one commit is not approval for
  the next. This is the standing rule and it outranks any inference that
  committing would be convenient.
- **Never rewrite published history.** No force-push, no `--amend`, no rebase
  of anything already on `origin`. Someone may have pulled it. Unpushed local
  commits are yours to tidy. A branch already pushed takes a merge of
  `origin/main`, not a rebase onto it.
- **Stage deliberately. Never `git add -A` or `git commit -a`.** Name the paths
  you changed. The working tree routinely carries things that must not ride
  along: generated files (`app/next-env.d.ts` regenerates on every dev run),
  another session's edits, and the failure mode the hook exists for, a
  credential. A blind `add -A` is how all three get committed.
- **Changes you did not make are a stop sign.** If `git status` shows files you
  did not touch, do not stage them and do not "clean them up". Say what is
  there and ask. They are someone else's unfinished work, or a symptom, and on
  2026-09-20 they were a half-completed branch switch that looked exactly like
  a broken repository.
- **`main` requires signed commits.** One unsigned commit fails an otherwise
  green PR. Re-sign with `git commit-tree`; do not reach for `rebase -f` to fix
  it.
- **Green before merge, even with the bypass.** Admin bypass on the `main`
  ruleset exists for emergencies, not for impatience. Let the checks finish.
- **Branches are short-lived and named for their type** (`feat/`, `fix/`,
  `chore/`, `docs/`, `ci/`, `test/`). When it merges, delete the branch and
  remove its worktree the same day. A merged branch left lying around is what
  cost a session and 1.7G above.

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

Codex Desktop worktrees use `.codex/environments/environment.toml`. It runs
`make setup` once and exposes the same checks, tests, and development commands
as actions in the app. It contains no credentials; local secrets stay outside
the repository.

Two editors are configured, `.vscode/` and `.zed/`, and each holds the same
material in its own shape because neither format is a superset of the other:
the LSP and exclusion settings that keep rust-analyzer off 167k files, the
dev-server tasks, and the debug configurations. Two
differences are worth knowing before editing either. Zed merges
`.vscode/tasks.json` into its own task list, so a task can appear twice and
both copies must work; and Zed implements no task dependencies, which is why
the stop tasks in both files call `scripts/dev_stop.sh` instead of fanning out
over each other. Zed reads `.vscode/launch.json` only when `.zed/debug.json` is
absent, and it supports neither `compounds` nor `node-terminal`, so the
multi-process launches live in `.zed/tasks.json` rather than being translated
into debug configurations that would not run.

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
  files to GitHub repo secrets/variables. Reads `backend/`, `app/` and
  `desktop/` `.env.test`; the desktop release signing keys are on the allowlist
  because a runner can only ever receive them as GitHub secrets.
- `stage_devid_secrets.py` — turn a Developer ID `.cer` plus its private key
  into the three `DUCT_DEVID_*` values, staged in `desktop/.env.test`. Exists
  because OpenSSL 3 exports a PKCS#12 that Apple's `security(1)` cannot read,
  and blames the password for it.
- `bootstrap_env_test.sh` — copy local dev env files to the gitignored
  `.env.test` targets.
- `envfile.py` — shared dotenv parser used by the above.
- `dev_stop.sh` — stop what a dev session started: `all`, or any of `backend`,
  `app`, `site`, `phoenix`, `desktop`. Both editors' stop tasks call it, so the
  kill list exists once.
- `security/audit.py`, `security/leak_scan.py` — repo hygiene, both run in CI.
- `shots/shoot.mjs` — product screenshots from the real app for the README and
  the site: one story (`app/src/lib/__fixtures__/solo-story.mjs`) feeds the
  mock agent backend and the `/preview` scenes, Playwright captures at 2x, and
  `sharp` frames the result. Needs the app dev server; adds no dependency.

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
- A PR that finishes an issue says `Closes #N` in its body (the template
  prompts for it); `Refs #N` is for partial work. GitHub only auto-closes on
  the first form, and the board's "PR merged → Done" automation only fires
  when the PR is linked that way — #127 sat open a week after it shipped
  because its commits said `Refs`.
- Any change to user-facing copy in `app/` or `site/` ends with `make i18n`,
  which translates the new and changed strings into the four other languages
  and commits nothing by itself; `make check` is red until the catalogues and
  the generated `site/<lang>/` pages are current. The writing rules live in
  each area's `AGENTS.md` under "Interface language" and "Translated pages".
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
