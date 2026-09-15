# Engineering

How Duct is built. Two kinds of file, by name (the rule is in
[`../README.md`](../README.md#naming)):

- **References** — undated, kept true, listed below. Read these first.
- **Records** — dated `YYYY-MM-DD-<slug>` files in this folder: reviews,
  plans, research, decisions. Frozen on the day they were written; `ls` sorts
  them into a timeline, and each one says at the top what it is. They are
  not indexed here on purpose: a summary of a frozen document goes stale the
  moment the code moves, while the document itself does not pretend to be
  current. Superseded ones move to [`../archive/`](../archive/2026-Q2/).

## References

- [`agent-ports-and-events.md`](agent-ports-and-events.md) — the harness
  boundary: the six agent ports and the SSE event contract. The code is the
  source of truth; this explains the shape.
- [`agent-harness-references.md`](agent-harness-references.md) — the
  coding-agent harnesses we read (Codex, OpenCode, pi): why each matters,
  the revision last read, findings pinned to `file:line`.
- [`agent-evaluation.md`](agent-evaluation.md) — LLM-as-judge output QA:
  the harness in `backend/tests/eval/`, judge biases and mitigations.
- [`credential-storage.md`](credential-storage.md) — where every secret
  lives and what protects it, including exactly when macOS prompts.
- [`claude-code-on-the-web.md`](claude-code-on-the-web.md) — runbook for
  cloud Claude Code sessions on this repo.
- [`security-audit-skill-and-hooks.md`](security-audit-skill-and-hooks.md)
  — runbook for the local security gate: audit skill, leak scanner, policy.
- [`agent-prompts.md`](agent-prompts.md) — **generated, do not edit:** every
  agent's system prompt and a sample turn. `make dump-prompts`; CI fails a
  prompt change that skips it.

Two runbooks live in the private `duct-cloud` repository: deployment
(Cloudflare + Railway) and the retired TestFlight channel's Apple-account
notes.
