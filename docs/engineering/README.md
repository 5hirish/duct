# Engineering

Feature and system implementation plans (living documents until shipped).

- [`deployment-cloudflare-railway.md`](deployment-cloudflare-railway.md) — **runbook:** redeploy, env pushes, verification (Next.js on Cloudflare, API on Railway)
- [`claude-code-on-the-web.md`](claude-code-on-the-web.md) — **runbook:** Claude Code cloud sessions on this repo (account connect, setup script, secrets, `--remote`/`--teleport`)
- [`agent-evaluation.md`](agent-evaluation.md) — agent output QA: the LLM-as-judge / persona critique harness (`backend/tests/eval/`), judge biases + mitigations, and the eval landscape
- [`oauth-authentication-plan.md`](oauth-authentication-plan.md) — Google Ads connector OAuth (updated with current routes)
- **Google Ads API (token application):** [`google-ads-api-tool-design-document.md`](google-ads-api-tool-design-document.md) — canonical text; add `.docx` / `.doc` locally if needed for Google submissions (not tracked in repo).

Superseded specs live under [`../archive/2026-Q2/`](../archive/2026-Q2/) (dynamic fetch plan, completed demo rollout, old stack recommendation, paid-ads agent checklist).

## History

[`history/`](history/) is for ephemeral notes. Prefer [`../archive/`](../archive/2026-Q2/) for dated, completed execution plans.
