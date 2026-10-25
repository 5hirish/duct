# Engineering

**Author:** Shirish Kadam · **Updated:** 2026-10-25

How Duct is built, by what you want to do. References are kept current;
dated records are frozen on the day they were written (the rule is in
[`../README.md`](../README.md#naming)).

## Build and change an agent

| To | Read |
|---|---|
| Add an agent, or change a prompt, tool, model default, middleware or pin: each rule, what enforces it, the open gaps | [Building and changing agents](agent-engineering.md) |
| Understand the harness seam: the six agent ports and the event stream the app reads. The code is the source of truth; this explains the shape | [Agent ports and the event contract](agent-ports-and-events.md) |
| Test an agent whose output is subjective: the LLM-as-judge harness, the eval gate on agent PRs, judge biases and their mitigations | [Agent output QA](agent-evaluation.md) |
| Read what every agent is told: its system prompt and a sample turn | [Agent prompts](agent-prompts.md), **generated** by `make dump-prompts`. CI fails a prompt change that skips it |
| See which harnesses we read for answers (Codex, OpenCode, pi), the revision last read and the findings pinned to `file:line` | [Agent harnesses we learn from](agent-harness-references.md) |

## Store, secure and run

| To | Read |
|---|---|
| Decide where something is recorded before proposing a table, event kind or log | [Data model](data-model.md) |
| Know where every secret lives, what protects it, and exactly when macOS prompts | [Credential storage](credential-storage.md) |
| Run the local security gate: audit skill, leak scanner, policy | [Local security audit](security-audit-skill-and-hooks.md) |
| Run Claude Code in the cloud against this repo | [Claude Code on the web](claude-code-on-the-web.md) |

Deployment (Cloudflare and Railway) and the retired TestFlight channel's
Apple-account notes are runbooks in a separate private repository.

## Records

Dated `YYYY-MM-DD-<slug>.md|html` files in this folder: reviews, plans,
research, decisions. `ls` sorts them into a timeline and each says at the top
what it is.

They are not indexed here on purpose. A summary of a frozen document goes
stale the moment the code moves, while the document itself never claims to be
current. Ones a reader should no longer follow move to
[`../archive/`](../archive/2026-Q2/).
