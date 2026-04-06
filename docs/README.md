# Documentation index

Planning and reference material for Duct. **Start here** to find the right doc by intent.

| Section | Audience | Contents |
|--------|----------|----------|
| [`strategy/`](strategy/) | Founders, PM, architects | Product direction, architecture principles |
| [`gtm/`](gtm/) | Marketing, growth | Paid and organic GTM plans |
| [`mvp/`](mvp/) | Product + eng shipping a slice | MVP scope and vertical plans (e.g. Google Ads) |
| [`engineering/`](engineering/) | Engineers | Active implementation plans and ops runbook ([Cloudflare + Railway](engineering/deployment-cloudflare-railway.md)), [User storage: Railway Postgres + SQLModel + Alembic](engineering/user-storage-railway-postgres-sqlmodel-alembic.md), [Google Ads API tool design](engineering/google-ads-api-tool-design-document.md) |
| [`archive/2026-Q2/`](archive/2026-Q2/) | Reference | Superseded plans and one-off agent runbooks (read [`archive/2026-Q2/README.md`](archive/2026-Q2/README.md) first) |
| [`engineering/history/`](engineering/history/) | Reference | Reserved for short-lived notes; most dated narratives moved to [`archive/`](archive/2026-Q2/) |
| [`design/`](design/) | Design + eng | Design index; historical UX specs live in [`archive/2026-Q2/`](archive/2026-Q2/) |
| [`guides/`](guides/) | Anyone prompting LLMs | Evergreen model prompting notes (not roadmap) |

## Naming

- **`strategy/`** — *what and why* (long horizon).
- **`mvp/`** — *what we ship next* for a defined slice.
- **`engineering/`** — *how we build* (can link to `design/` and `mvp/`).

Add a short `README.md` in a folder when its purpose is non-obvious or status (draft vs active) matters.
