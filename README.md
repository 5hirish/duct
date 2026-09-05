# Duct

**Open-source AI agent for cross-tool product and growth analytics.** Duct
connects Google Ads, GA4, Search Console, Mixpanel, Stripe and more, then reads
across all of them to answer questions a single dashboard cannot — and, with
your approval, writes the fix back.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Backend CI](https://img.shields.io/github/actions/workflow/status/5hirish/duct/backend.yml?branch=main&label=backend&style=flat-square)](.github/workflows/backend.yml)
[![App CI](https://img.shields.io/github/actions/workflow/status/5hirish/duct/app.yml?branch=main&label=app&style=flat-square)](.github/workflows/app.yml)
[![Site](https://img.shields.io/badge/site-getduct.ai-orange?style=flat-square)](https://getduct.ai)

Every tool in a growth stack speaks its own language. Spend lives in Google Ads,
activation lives in Mixpanel, rankings live in Search Console, revenue lives in
Stripe — and the answer to "why did signups drop last week" lives in the gaps
between them. Duct is the layer that reads all of them together.

Run it as a **desktop app on your own machine** with your own API keys, or
**self-host** the backend. MIT licensed, no account required for local use.

---

## What it does

**Connects 12 sources** — Google Ads, Google Analytics 4, Search Console, Tag
Manager, Meta Ads, Apple Search Ads, OpenAI Ads, Mixpanel, Microsoft Clarity,
GrowthBook, Stripe, RevenueCat. Read-only OAuth; credentials are encrypted at
rest and never leave your install in desktop mode.

**Runs five agents** over that data:

| Agent | What it does |
|---|---|
| `insights` | Cross-tool synthesis — a weekly brief, or an interactive session you can ask follow-ups in |
| `audit_seo` | Technical + content SEO audit with prioritised findings |
| `research` | Open-ended investigation across your connected sources |
| `blog-writer` | Long-form drafts grounded in your own search and analytics data |
| `tiktok_studio` | Short-form content planning and production |

**Executes changes, behind approval gates.** Duct can propose a change set —
pause a campaign, add negative keywords, mark a GA4 key event — show you a
preview and a guardrail check, and apply it only after you approve. Rollback is
part of the contract. The agent can propose and inspect; **it cannot approve or
apply**, in either harness. That decision lives in code the model never sees.

**Remembers.** Project memory is bi-temporal and provenance-linked, so a brief
can cite why it believes something and when that stopped being true.

**Brings your own model.** Anthropic, OpenAI, Gemini, or anything on OpenRouter.
Three tiers you assign per job, so reasoning-heavy work and cheap summarisation
do not pay the same price.

## Quickstart

Requires Python 3.12+ and Node 20+.

```bash
git clone https://github.com/5hirish/duct.git
cd duct
make setup                      # dependencies for every area

cp backend/.env.example backend/.env.local
# set one model provider key, e.g. ANTHROPIC_API_KEY or OPENROUTER_API_KEY

make serve-backend              # FastAPI on :8002
make serve-app                  # Next.js on :3003, in a second terminal
```

Open <http://localhost:3003>. `make help` lists every target.

Every setting has a default, so a missing variable never errors — the feature it
powers just quietly does nothing. `backend/.env.example` documents the full set
and is test-enforced against `config.py`.

### Desktop app

`desktop/` is a [Tauri v2](https://tauri.app) shell that bundles the backend as
a local sidecar: SQLite on disk, loopback-only, provider keys in the OS keychain
(macOS Keychain, Windows Credential Manager, Linux Secret Service). No account,
no server, no data leaving the machine. See [`desktop/README.md`](desktop/README.md).

## Repository layout

| Path | Stack | Instructions |
|---|---|---|
| [`backend/`](backend/) | Python 3.12, FastAPI, SQLModel, Alembic | [`backend/AGENTS.md`](backend/AGENTS.md) |
| [`app/`](app/) | Next.js App Router (JS), Cloudflare Workers | [`app/AGENTS.md`](app/AGENTS.md) |
| [`desktop/`](desktop/) | Tauri v2 (Rust) + PyInstaller sidecar | [`desktop/AGENTS.md`](desktop/AGENTS.md) |
| [`site/`](site/) | Static HTML/CSS/JS, no build step | [`site/AGENTS.md`](site/AGENTS.md) |
| [`docs/`](docs/) | Engineering plans and reference material | [`docs/README.md`](docs/README.md) |

Each area's `AGENTS.md` is the canonical instruction file for both humans and
coding agents; `CLAUDE.md` beside it is a symlink to the same file.

## Architecture notes worth reading

The design decisions with real reasoning behind them, rather than a diagram:

- **[Agent ports](backend/agents/core/ports/__init__.py)** — Duct rents an agent
  harness, it does not marry one. Domain code imports no framework; only runners
  and binders do, and a test enforces it.
- **[Agent memory](docs/engineering/agent-memory-research.html)** — the research
  and the bi-temporal model behind `project_memories`.
- **[Staged execution](backend/service/execution/policy.py)** — why autonomy
  changes how often an agent interrupts, never what may auto-apply.
- **[Insights architecture](docs/engineering/intelligent-insights-architecture-plan.md)**

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Setup, the checks CI runs
(`make check`), and the conventions that cost the most to get wrong.

Agent-written contributions are welcome — the PR template asks where an agent
helped so a reviewer knows where to look hardest, not to penalise it.

Security issues do **not** go in a public issue: see [SECURITY.md](SECURITY.md).

## Community

Questions, ideas and "why is it built this way" go in
[**Discussions**](https://github.com/5hirish/duct/discussions). Bugs and
concrete proposals go in [Issues](https://github.com/5hirish/duct/issues).
There is no Discord yet, deliberately: an empty chat room is a worse signal
than no chat room, and an answer in Discussions is one anybody can find later.

[**The Duct Doctrine**](https://getduct.ai/doctrine) is the short version of
what this project believes and why, each tenet linked to the file that enforces
it. Start there if you want to know whether you would enjoy contributing before
you read any code.

I also write and record about the parts of this that generalise — agent memory,
approval gates, running models locally:

- [youtube.com/@5hirish](https://youtube.com/@5hirish)
- [shirishkadam.com](https://shirishkadam.com)
- [@5hirish](https://x.com/5hirish)

## License

MIT — see [LICENSE](LICENSE), including its exceptions for third-party
documentation under `docs/guides/` and for trademarks.

Duct is built by [Shirish Kadam](https://github.com/5hirish). A hosted version
runs at [getduct.ai](https://getduct.ai) for people who would rather not operate
it themselves; the code here is the same code.
