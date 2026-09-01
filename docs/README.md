# Documentation index

Planning and reference material for Duct. **Start here** to find the right doc by intent.

| Section | Audience | Contents |
|--------|----------|----------|
| [`engineering/`](engineering/) | Engineers | Active implementation plans and ops runbooks ([Claude Code on the web](engineering/claude-code-on-the-web.md), [User storage: Postgres + SQLModel + Alembic](engineering/user-storage-railway-postgres-sqlmodel-alembic.md), [Google Ads API tool design](engineering/google-ads-api-tool-design-document.md), [Agent memory research + design](engineering/agent-memory-research.html), [Desktop-adaptive UI review](engineering/desktop-adaptive-ui-review.html), [Three-tier model routing UX](engineering/model-routing-ux-design.html)) |
| [`archive/2026-Q2/`](archive/2026-Q2/) | Reference | Superseded plans and one-off agent runbooks (read [`archive/2026-Q2/README.md`](archive/2026-Q2/README.md) first) |
| [`design/`](design/) | Design + eng | Design index; historical UX specs live in [`archive/2026-Q2/`](archive/2026-Q2/) |
| [`agents/`](agents/) | Anyone writing agents | Agent runbooks |
| [`guides/`](guides/) | Anyone prompting LLMs | Third-party model prompting references, each with its source and licence |

Product strategy, go-to-market and MVP scope are kept in a separate private
repository along with the deployment runbooks, so this index covers engineering
and reference material only.

## Naming

- **`engineering/`** — *how we build* (can link to `design/`).
- **`design/`** — UX specs and design decisions.

Add a short `README.md` in a folder when its purpose is non-obvious or status (draft vs active) matters.
