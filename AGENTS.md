# Duct — Monorepo agent instructions

Monorepo for [getduct.ai](https://getduct.ai).

## Structure

- `site/` contains the static marketing site and blog.
- `backend/` contains Python reporting and synthesis code.
- `app/` is reserved for the future authenticated Duct app.
- `docs/` contains product, MVP, and implementation plans.

## Monorepo rules

- Keep changes scoped to the correct top-level area.
- Do not mix backend product code into `site/`.
- Do not introduce build tools into `site/` unless explicitly asked.
- Prefer directory-specific instruction files when working inside a subdirectory.

## Directory-specific guidance

- When working in `site/`, follow `site/AGENTS.md`.
- When working in `site/`, also follow `site/CLAUDE.md` for the marketing-site conventions.
