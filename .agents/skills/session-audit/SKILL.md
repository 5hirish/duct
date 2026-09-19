---
name: session-audit
description: Independent audit of a stored Duct agent session. Pulls it from the database (the context the model read, every tool call and payload, the reply, artifact versions, memories, cost), solves the same task yourself on the same data before reading Duct's answer, grades both against a fixed rubric, diagnoses the gap to a prompt, tool, harness, model or product cause, and records proposals in a private ledger so audits compound. Use for "audit session X", "review the last brief", "how good was that answer", "compare Duct against <another agent>".
argument-hint: "<conversation-id | list> [--agent insights|audit|content] [--focus artifact|reply|run]"
---

Duct's agents run unattended on other people's data, and the only regular
reader of what they produce is the person who asked. Nobody re-derives the
answer to see whether it was right, whether the prose matched the person,
or whether the twenty tool calls were the right twenty. This skill is that
reader. It is deliberately **independent**: the auditor solves the task first,
blind, on exactly the data the agent had, and only then reads what Duct
wrote. A review that reads the answer first grades the answer's own framing.

It is also the standing comparison of Duct against other harnesses. Whoever
runs this skill (Claude Code, Codex, OpenCode, a person) is the "other
agent"; the ledger records which one, so over time it says how Duct's
insights agent compares with a frontier agent given the same inputs.

**Rubric v1.** Bump the version and log the change in the ledger when a
dimension is added or redefined.

## Ground rules

- **Read-only.** The pull script reads the database and never writes to it.
  Nothing in an audit changes a session, a memory or an artifact.
- **The bundle is customer data.** It lives in the private audit home and
  nowhere else. Nothing from it goes into `duct`, a GitHub issue, a
  changelog or a memory file without anonymising it (no names, domains,
  figures that identify the business). Proposals are written so they can
  be filed publicly without the bundle.
- **Secrets.** The script reads `DATABASE_URL` from `backend/.env.local`
  through the app's own config and prints nothing from it. Never open,
  print or copy that file yourself. Every string in the bundle is passed
  through `redact_secrets`; if you still see a credential, stop and say so.
- **Sandbox.** The database host does not resolve inside the sandbox, so
  the pull runs unsandboxed. Only the pull; the rest is reading files.
- **Independence is the point.** Phase 2 happens before you open
  `artifacts/` or read any `assistant` row in `transcript.md`. If you
  cannot keep that order (you already saw the answer), say so in the
  record; the comparison is then a review, not an audit.

## Audit home

Records, the ledger and bundles live outside this repository:

1. `../duct-cloud/docs/audits/` when the private checkout is beside this one
   (it is on the maintainer's machine; `README.md` there explains the layout).
2. Otherwise `.audits/` at the root of `duct`, which is gitignored. Say in the
   record that the ledger was not available, and hand the record to the
   maintainer to move.

## Phase 0. Pull

```bash
make session-bundle ID=list                       # recent sessions, newest first
make session-bundle ID=<conversation-id> OUT=<audit home>/bundles/<short id>
```

`ID=list` takes `--agent` through the script directly:
`cd backend && poetry run python scripts/session_bundle.py list --agent insights --limit 20`.

The bundle:

| File | What it is |
|---|---|
| `transcript.md` | The run as a document: context first, then turns, each tool call as one line, artifacts and memories at the end. Read this first, **stopping before the first `Assistant` row** until Phase 2 is done. |
| `bundle.json` | Everything, machine-readable: conversation, project context, profile, every event, artifacts with content, memories written by this session and active for the project, change sets, usage. |
| `tools/NNNN-<name>.json` | Each tool call's full input and output. These are the agent's entire view of the world; Phase 2 works from them alone. |
| `artifacts/<slug>-vN.<ext>` | Every artifact version, as stored. Do not open until Phase 3. |

The script's last line is the **prompt check**: whether the system prompt
the session ran on matches this checkout. If it has changed, read
`docs/engineering/agent-prompts.md` at the session's commit
(`git show <sha>:docs/engineering/agent-prompts.md`) before proposing prompt
edits. A session that predates `CONTEXT` rows (before 2026-09-19) has no
fingerprint and no stored opening turn; grade it, but mark every
prompt-level finding as unverified.

## Phase 1. Understand the request

From the `Context the model read` section and the `User` rows only:

1. **What was asked**, in one sentence, and what the person almost certainly
   meant (the profile's role and writing preset are in the context block).
2. **What a great answer needs**: the questions it must answer, the numbers
   it must show, the decisions it should enable. Write this as a checklist
   before seeing any answer. It is the yardstick for both.
3. **What data was available**: list `tools/` by name and window. Note what
   was fetched twice, what failed, what was never fetched though the
   connector list offered it.

## Phase 2. Independent attempt, blind

Solve the task yourself with exactly what the agent had: the context block,
the memory digest, the connector list, and the tool outputs in `tools/`.
No live fetches, no web, no other knowledge of the business. If a needed
pull is missing, say what you would have fetched and proceed on what exists,
which is what the agent should have done.

Write the same deliverable in the same format (`artifact_format` in the
context block): a brief in `attempt.md` beside the record, plus the chat
reply you would have given. Time-box to what a careful analyst would spend,
and note the harness and model doing this (they go in the ledger).
`attempt-prompt.md` in this folder is the exact instruction to hand a second
harness so two independent attempts are comparable.

## Phase 2b. Replay (when the question is a prompt or a model)

The audit's proposals are about the prompt, the tools, the harness or the
model. Before any of them ships, run the same question over the same pulls
with the change in place and read what comes out:

```bash
make session-replay BUNDLE=<audit home>/bundles/<short id>                 # today's prompt, the user's model
make session-replay BUNDLE=... ARGS="--tier heavy"                         # same, one tier up
make session-replay BUNDLE=... ARGS="--provider anthropic --model claude-opus-5"
make session-replay BUNDLE=... ARGS="--prompt 'the question, asked better'"
```

`FetchData` is served from the bundle and the connectors are closed, so a
pull the original never made comes back `not_in_replay` and nothing reaches
a provider; no recorder, no artifact persister, no memory writes, no pausing
tools. Output lands in `bundles/<short id>/replays/<timestamp>-<model>/`:
the brief, the reply, every stream event, and `replay.json` with the seed
coverage and `reconstructed` (true for a session without a CONTEXT row,
whose priming was rebuilt from the database today). It spends a real model
call at the user's settings, so say so in the record with the cost from the
stream's usage events.

Grade a replay with the same rubric as a third column. A proposal is
`verified` when the replay moves the dimension it targeted; a replay that
moves nothing is the cheapest possible way to learn a proposal was a guess.

## Phase 3. Grade

Now read Duct's `assistant` rows and `artifacts/`. Score every dimension
1 to 5 for Duct **and for your attempt**, each with a one-line reason and
evidence (`[seq]` references, artifact line numbers, tool file names). A 5
is "nothing to improve", a 3 is "usable with a caveat", a 1 is "wrong or
missing". Grade your own attempt as hard as Duct's and say where you could
not be objective.

**Run** (how the agent worked)

| Dimension | Question |
|---|---|
| Tool choice | Were the right sources pulled, once each, over windows that answer the question? |
| Data reach | Was anything available and relevant left unfetched, or fetched and unused? |
| Turn economy | Model turns that produced no new information (planning rewrites, narration, re-asking). Count them. |
| Questions | Did it ask when it had to, and only then? Was each question answerable by this person? |
| Failure handling | A failed pull or expired connector: named plainly, worked around, not retried into the ground? |
| Cost and time | From `Usage`: calls, tokens, dollars. Proportionate to the task? |

**Reply** (the chat answer)

| Dimension | Question |
|---|---|
| Resolution | Does it answer what was asked, or something adjacent? |
| Accuracy | Every number and claim traceable to a `tools/` output. Mark each that is not. |
| Reasoning | Are conclusions argued from the data, with the alternative explanations considered? |
| Intelligence | Did it notice what a sharp analyst would (a window mismatch, a metric definition, a confound)? |
| Style | Does it match the profile: language, preset, role, length? Does it sound like a colleague or a model? |
| Honesty | Gaps, uncertainty and failed pulls stated, not smoothed over? |

**Artifact** (the brief or report)

| Dimension | Question |
|---|---|
| Structure | Findable: a reader gets the point in the first screen, and the sections earn their place. |
| Information | The numbers that matter, with their windows and comparisons; nothing decorative. |
| Accuracy | Same test as the reply: every figure traceable. This is the dimension that decides trust. |
| Analytical thinking | Segments, trends, deltas, ratios: is the data made to say something, or restated? |
| Critical thinking | Are weak signals called weak? Is causation claimed only where it is earned? |
| Comprehension | Does it understand the business (context block) well enough to know what matters to it? |
| Actionability | Recommendations specific enough to act on tomorrow, with the expected effect and how to check it. |
| Style | Format as requested, the house voice, readable at a glance; tables where tables help. |

**Memory and side effects**

- Memories written this session: are they facts worth keeping, correctly
  scoped, non-duplicating? Anything remembered that should not have been?
- Change sets proposed: safe, reversible, worth proposing?

## Phase 4. Compare and diagnose

One table: dimension, Duct, attempt, gap, cause. Every gap of 2 or more
points gets a cause from one class, with the file it points at:

| Class | Means | Points at |
|---|---|---|
| `prompt` | The system prompt or turn blocks told it the wrong thing, or did not tell it. | `backend/agents/<agent>/prompts/`, `agents/core/turn.py` |
| `tool` | A fetcher, a window default, a description that misled, compaction that lost the signal. | `agents/insights/data_tools.py`, `fetchers.py`, `connector_tools.py` |
| `harness` | The loop: verifier, planning, retries, idle timeouts, how a pause is surfaced. | `agents/core/deep_session.py`, `agents/core/lc.py`, the runner |
| `model` | The tier or model chosen could not do it; a stronger one would. | `agents/tiers.py`, `settings/models` |
| `product` | The UI set the wrong expectation, or the person could not give what was needed. | `app/` |

Where Duct did **better** than the attempt, say why: that is what the
prompt is getting right and must not be edited away.

## Phase 5. Propose

For each cause, one proposal: what changes, the evidence (`[seq]`,
anonymised), the expected effect on which rubric dimension, and how the
re-audit will show it. Prompt proposals are written as the new wording,
not a description of it, and end with `make dump-prompts`.

- A small fix (a sentence in a prompt, a tool description, a default
  window) can be made in the same session, with its test, and offered for
  commit.
- Anything larger goes through the `prioritize` skill and becomes an issue.
  The issue carries the anonymised finding and the proposal, never the bundle.

## Phase 6. Record

Write `<audit home>/YYYY-MM-DD-<agent>-<short id>.md` from
`record-template.md` in this folder, put `attempt.md` beside it, and append
to `ledger.md`: one row in **Audits**, one row per proposal in
**Proposals** with status `proposed` or `filed #N`. A record is frozen; a
later re-audit is a new record that references it.

## The loop that makes this compound

- **Read the ledger before auditing.** A finding already in it is a repeat:
  reference the proposal id instead of writing a new one, and raise its
  weight.
- **Re-audit after a proposal ships.** Pick a fresh session of the same
  agent, run the full skill, and write the delta on the proposal's row
  (`verified` or `regressed`). A proposal that never gets a delta is a
  guess that shipped.
- **Every fifth audit, read the ledger as a whole.** Three audits with the
  same class of finding is a systemic issue: one issue for the maintainer,
  not five proposals.
- **Rubric changes are logged.** If a session shows a failure the rubric
  cannot name, add the dimension here, bump the version, and record why in
  the ledger's Rubric changes table.
- **Harness comparison.** The ledger's Harness column plus the attempt
  scores are the standing answer to "how does Duct compare with X on Duct's
  own tasks". Run Phase 2 through a second harness with `attempt-prompt.md`
  when that question is the point of the audit.

## Running the attempt in another harness

The independent attempt is whoever runs this skill. To make it a second
agent on purpose, hand `attempt-prompt.md` and the bundle to that harness
non-interactively, from inside the bundle directory, and record the harness
and model in the ledger:

```bash
cd <audit home>/bundles/<short id>
sed -n '/Context the model read/,/^## \[/p' transcript.md > context.md   # the priming, without the answer
claude -p "$(cat ../../../../duct/.agents/skills/session-audit/attempt-prompt.md)" \
  --allowedTools "Read,Glob,Grep,Write" --model opus
codex exec --sandbox workspace-write "$(cat .../attempt-prompt.md)"
```

Both write `attempt.md` into the bundle directory; move it beside the
record. The two attempts and Duct's brief are then three columns of one
rubric, which is the comparison the ledger accumulates.

## Tooling considered, and why the skill is what it is

Surveyed 2026-09-19. The trajectory-eval frameworks (DeepEval's agent
metrics, Phoenix's trajectory and tool-call evaluators, promptfoo, Inspect)
all do the same two things: an LLM-as-judge over a trace against a rubric,
and a regression harness that re-runs cases. This skill keeps both jobs but
takes neither dependency, for three reasons:

- The judge here is a frontier agent that first solved the task blind. A
  single-shot judge prompt over the trace is a weaker reviewer than that,
  and calibrating it would be more work than the audits it replaces.
- The regression harness is `session_replay.py`: the real runner, the real
  prompt, the real model, on the session's own data. A framework's replay
  would re-implement the fetch layer to get the same hermeticity.
- Phoenix is already installed for traces. Set `OTEL_EXPORTER_OTLP_ENDPOINT`
  before a replay and the per-turn and per-tool timings are in Phoenix,
  reachable from the MCP; that is the timing half of the run rubric without
  a second tool.

Reach for `phoenix.evals` (already in the venv) when the ledger has enough
records to need a batch judge over many sessions; until then a batch judge
would score what nobody has time to read.

## Known gaps

- Sessions before 2026-09-19 have no `CONTEXT` row: no stored opening turn,
  no memory digest, no prompt fingerprint. The audit and content agents do
  not write one yet; the insights runner does. Give a runner a
  `recorder.record_context(run_context(...))` call before relying on this
  skill for that agent (see `backend/AGENTS.md`).
- A replay is a fresh checkpoint thread: it cannot replay a paused session
  past its pause, and a session that asked the user a question gets the
  unattended shape (no question, stated assumption) instead.
- A replay of a session without a CONTEXT row primes from the database as
  it is today. The digest lines citing memories the session itself wrote
  are dropped (`memory_lines_dropped` in `replay.json`), but anything the
  project learned since, from other sessions, is in the priming and was not
  in the original's. Read `reconstructed: true` as "same data, different
  priming".
- The first audit (2026-09-19, insights 696dd088) found four defects in
  this tooling on its first run; the record lists them. Expect the second
  run to find fewer, not none.
- Artifact content is read from storage; if the storage backend is not
  reachable from this machine the file is empty and the record says so.
- `MEMORY_RECALLED` is not persisted, only the digest text inside the
  `CONTEXT` row; which individual memories were recalled is inferred from
  the digest.
