# Duct — Claude Code monorepo instructions

Monorepo for [getduct.ai](https://getduct.ai).

## Top-level areas

- `site/` — static marketing site
- `backend/` — Python reporting and synthesis MVP
- `app/` — Next.js App Router report viewer and agent interface (Cloudflare Workers)
- `desktop/` — Tauri v2 desktop shell (loads the hosted app; OS-keychain BYO provider keys)
- `docs/` — strategy, GTM, MVP, engineering, design, guides ([`docs/README.md`](docs/README.md))

## Monorepo guidance

- Keep instructions local to the directory they describe.
- Prefer directory-level `CLAUDE.md` files in monorepo areas with different stacks or workflows.
- When editing files under `site/`, follow `site/CLAUDE.md`.
- When editing files under `site/`, also follow `site/AGENTS.md`.
- Do not assume site conventions apply to `backend/` or `app/`.
- Cursor Agent Skills live under `.cursor/skills/<name>/SKILL.md` as symlinks to `.claude/skills/<name>.md`; change the `.claude` file to update both tools.
