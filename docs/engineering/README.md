# Engineering

Feature and system implementation plans (living documents until shipped).

- the deployment runbook (duct-cloud, private) — **runbook:** redeploy, env pushes, verification (Next.js on Cloudflare, API on Railway)
- [`claude-code-on-the-web.md`](claude-code-on-the-web.md) — **runbook:** Claude Code cloud sessions on this repo (account connect, setup script, secrets, `--remote`/`--teleport`)
- the TestFlight runbook (duct-cloud, private) — **runbook:** shipping the desktop shell to macOS TestFlight (Apple setup, secrets, App Store constraints)
- [`tauri-desktop-byo-keys-plan.md`](tauri-desktop-byo-keys-plan.md) — Tauri desktop shell + bring-your-own provider keys (design)
- the engine consolidation review (duct-cloud, private) — review: v1 (LangChain) / v2 (Google ADK) / v3 (Claude Agent SDK) capability comparison and a phased plan to consolidate on one harness
- [`agent-evaluation.md`](agent-evaluation.md) — agent output QA: the LLM-as-judge / persona critique harness (`backend/tests/eval/`), judge biases + mitigations, and the eval landscape
- [`agent-memory-research.html`](agent-memory-research.html) — **research + design (Phases 1–2 built):** how ChatGPT, Claude, Claude Code, Hermes Agent and the memory frameworks (Mem0, Zep, Letta…) implement memory; the Duct model — user / project / artifact scopes in one bi-temporal `project_memories` table, agent `RememberFact`/`SearchMemory` tools, post-session consolidation, provenance chips and the project timeline. §07 carries the build status: the table, tools, timeline, consolidation, controls and the UX pass that shipped, and what is still Phase 3+
- [`agent-memory-taxonomy-and-ux-patterns.md`](agent-memory-taxonomy-and-ux-patterns.md) — **reference:** the memory taxonomy the literature converged on (substrate, function, retrieval, consolidation, temporal validity, evaluation) and the product UX patterns for provenance, timelines, trust/control and proactive recall
- [`agent-memory-on-deepagents.md`](agent-memory-on-deepagents.md) — **design:** what the `deepagents` SDK gives us for memory (`MemoryMiddleware`, backends, summarization, skills), the gaps, how the Duct memory model wires into V1 (`DuctMemoryBackend` projection, `RememberFact`/`SearchMemory` tools, structured-output consolidation), and the open-source-only stack (no memory library; Postgres FTS / pgvector, SQLite / sqlite-vec). §5 records where the shipped build departed from this plan — plain tools on both harnesses, no middleware or backend projection yet
- [`artifact-store-design.md`](artifact-store-design.md) — how the industry builds AI artifacts and what Duct's artifact store adopts (slugs, edit verbs, versions, exports)
- [`oauth-authentication-plan.md`](oauth-authentication-plan.md) — Google Ads connector OAuth (updated with current routes)
- [`project-collaboration-plan.md`](project-collaboration-plan.md) — project members + email invitations (owner/collaborator roles, invite tokens, Resend delivery)
- **Google Ads API (token application):** [`google-ads-api-tool-design-document.md`](google-ads-api-tool-design-document.md) — canonical text; add `.docx` / `.doc` locally if needed for Google submissions (not tracked in repo).

Superseded specs live under [`../archive/2026-Q2/`](../archive/2026-Q2/) (dynamic fetch plan, completed demo rollout, old stack recommendation, paid-ads agent checklist).

## History

[`history/`](history/) is for ephemeral notes. Prefer [`../archive/`](../archive/2026-Q2/) for dated, completed execution plans.
