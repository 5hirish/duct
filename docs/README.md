# Documentation index

Planning and reference material for Duct. **Start here** to find the right doc by intent.

| Section | Audience | Contents |
|--------|----------|----------|
| [`engineering/`](engineering/) | Engineers | Active implementation plans and ops runbooks ([Claude Code on the web](engineering/claude-code-on-the-web.md), [Google Ads API tool design](engineering/google-ads-api-tool-design-document.md), [Agent memory research + design](engineering/agent-memory-research.html), [Desktop-adaptive UI review](engineering/desktop-adaptive-ui-review.html), [Three-tier model routing UX](engineering/model-routing-ux-design.html), [Design system contrast review](engineering/design-system-contrast-review.html), [Agent harness references](engineering/agent-harness-references.md), [Autonomous insights agent](engineering/autonomous-insights-agent-plan.md), [Smart onboarding](engineering/smart-onboarding-plan.md)) |
| [`archive/2026-Q2/`](archive/2026-Q2/) | Reference | Superseded plans and one-off agent runbooks (read [`archive/2026-Q2/README.md`](archive/2026-Q2/README.md) first) |
| [`design/`](design/) | Design + eng | Design index; historical UX specs live in [`archive/2026-Q2/`](archive/2026-Q2/) |
| [`guides/`](guides/) | Anyone prompting LLMs | Third-party model prompting references, each with its source and licence |

Product strategy, go-to-market and MVP scope are kept in a separate private
repository along with the deployment runbooks, so this index covers engineering
and reference material only.

## Naming

- **`engineering/`** — *how we build* (can link to `design/`).
- **`design/`** — UX specs and design decisions.
- **`archive/<quarter>/`** — a doc moves here when following it would produce the
  wrong thing, not merely when the work ships. Every archived file carries a banner
  saying what replaced it, and a row in that folder's `README.md` saying why.

Agent conventions are in [`../backend/AGENTS.md`](../backend/AGENTS.md); cross-agent
design and per-agent plans go in `engineering/`. There is no separate `agents/` folder —
one existed for a single unbuilt plan, which is now archived.

Add a short `README.md` in a folder when its purpose is non-obvious or status (draft vs active) matters.
