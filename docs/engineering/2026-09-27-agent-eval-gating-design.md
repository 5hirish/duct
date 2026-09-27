# Gating agent changes with evals

**Author:** Shirish Kadam · **Date:** 2026-09-27

How Duct should decide that a change to an agent (a prompt edit, a model or
effort default, a middleware, a LangChain bump) is safe to merge. Today
nothing does: the offline suite proves the harness runs, the judge rubrics
run only by hand, and harness changes land daily. Anthropic's April 2026
Claude Code postmortem traced its quality drop to exactly this class of
change (an effort default, a caching bug, a system-prompt edit), not to the
model. Recommendation: **build on what we have, add no eval framework, and
add three tiers of triggers around it.**

## What we have

| Asset | Checks | Runs | Gap |
|---|---|---|---|
| `ToolCallingFake` runner tests (insights 60, content 19, audit 20) | the real harness with a scripted model: tools, events, pauses, compaction | every PR | scripted, not recorded; nothing asserts what is *sent* to the model (history, reasoning, effort, a stable prefix) |
| `tests/eval/` rubric + judge | weighted 1–5 dimensions, required/forbidden markers | framework offline; judge `live` only | one judge (`gemini-2.5-flash`), one call, no human-labelled calibration; Likert gate |
| Rubrics `content_post`, `audit_report` | post and report quality | live only | **no rubric for the insights brief**, the core deliverable |
| `content-eval.yml` | draft + image + judge | `workflow_dispatch` only | never on a PR, k=1, no baseline |
| `test_memory_retrieval.py` | 50 questions, 5 axes, judge-free, ratcheted floors | every PR | none — **the pattern to copy** |
| `dump_prompts.py` + `prompts.yml` | a prompt diff shows up as prose | PRs touching prompt files | model, tier, effort and max-token settings are not rendered, so an effort downgrade is invisible in review |
| `session_bundle.py` / `session_replay.py` | replay a real insights session on its own data; `seed_misses` counts divergence | by hand | insights only; needs the database; bundles are customer data |
| `session-audit` skill + private ledger | blind attempt, rubric, proposals | by hand | findings never become runnable cases |
| `backend/eval-scorecard.json` | nothing | nothing | one local run committed by accident; not a baseline |

## What good looks like in 2026

1. **Keep capability and regression evals apart.** Regression sits near 100% and protects; capability starts low and is climbed; a saturated capability case graduates. (Anthropic, *Demystifying Evals*; LangChain, *Agent Evaluation Readiness Checklist*)
2. **Deterministic trace checks first, an LLM judge only where code cannot decide.** (OpenAI, *Testing Agent Skills Systematically with Evals*)
3. **Grade the outcome; check process with invariants, not exact paths.** Up to 23% of passes are "lucky" once process is scored. (AgentLens, arXiv 2605.12925)
4. **Repeat trials, report pass^k, allow INCONCLUSIVE.** Sequential testing cuts trials ~78%. (tau-bench; Claw-Eval; AgentAssay, arXiv 2603.02601)
5. **Know the noise floor.** Infrastructure alone moved scores 6 points; distrust deltas under 3. (Anthropic, *Infrastructure noise*)
6. **Start small, from real failures.** 20–50 tasks; "every manual fix is a candidate for a future eval". (Anthropic; OpenAI)
7. **Turn production traces and feedback into cases.** (Google, *Agent Quality Flywheel*; LangChain, *Human Judgment in the Agent Improvement Loop*)
8. **An independent, capable, calibrated judge with binary verdicts.** A blended 0.80 hid a failure a HONORED/IGNORED rubric exposed; a weaker judge missed known-bad cases. (Google; Red Hat; Husain & Shankar)
9. **Evaluate the model × harness configuration; run per-model evals on every system-prompt change.** BYO keys mean Duct ships five configurations. (Anthropic postmortem; Harness-Bench, arXiv 2605.27922)
10. **Tier the CI; track efficiency.** Cheap on every PR, heavy nightly; an effort downgrade shows first as a cost drop with no visible quality change.

## Tool choice

Duct already has what the frameworks sell: rubric scoring in our code, a
fake-model runner over the real harness, a connector-free replay, per-call
`cost_usd`, OTel traces in Phoenix and a human-graded ledger. What is missing
is plumbing (k trials, three-valued verdicts, baselines, budgets, triggers)
and cases, roughly 400 lines in `tests/eval/`. Borrow ideas, not packages:
`agentevals`' trajectory match modes (MIT, last release 2025-07), Inspect's
epochs and `pass_k` vocabulary, AgentAssay's INCONCLUSIVE.

| Tool | Verdict |
|---|---|
| Phoenix experiments | viewer later, once a hosted Phoenix exists; the server is Elastic-2.0, so not the gate |
| `agentevals` | copy the match modes (~60 lines) |
| DeepEval, Inspect AI | skip: each wants to own the loop or duplicates our rubric |
| promptfoo | skip: single-prompt shaped; acquired by OpenAI (2026-03), a neutrality question for multi-provider evals |
| LangSmith, Braintrust | out: proprietary |

## Design

### Tier 0 — every PR, offline, free

- **Settings in the prompt dump.** `dump_prompts.py` renders agent × job → tier, default model per provider, effort, max tokens, caching and compaction flags. Add `agents/models.py`, `tiers.py`, `thinking.py`, `engines.py` to `prompts.yml`. An effort change becomes a reviewed line.
- **Request invariants.** A `RecordingFake` captures every model call's messages and kwargs across a three-turn script, and asserts: the tools + system prefix is byte-identical across calls; every prior assistant message (reasoning and tool calls included) is present unless a compaction fired; effort matches `thinking.py`; the tool set matches a snapshot. This is the postmortem's caching bug, caught for free.
- **Cassettes.** Real responses recorded by tier 1 on synthetic data, replayed through today's harness: same tools dispatch, same event kinds, the artifact persists. Catches tool renames and schema breaks. Refreshed nightly.

### Tier 1 — PRs that touch the harness, paid, small

`.github/workflows/agent-eval.yml` on `backend/agents/**`, `service/profile.py`,
`service/memory.py`, `poetry.lock`, `tests/eval/**`; skipped for drafts and when
a fingerprint (the prompt dump plus the locked agent-package versions) already
passed; label `run-evals` forces it.

- **Routing:** `agents/insights/**` runs insights cases; audit and content likewise; anything shared runs all three.
- **Cases:** insights, five synthetic replays (a fictional business from the `/preview` story fixture, FetchData seeded as JSON; needs a DB-free replay entry point); audit, one crawl case; content, the 3-slide draft.
- **Providers:** the default (Gemini Flash) at k=3; Sonnet at k=1 as an adapter smoke test, because caching and thinking semantics differ there.
- **Checks per trial:** run finished with an artifact and no error event; `seed_misses` ≤ 2; no repeated identical FetchData; **every figure in the brief traces to a tool output**; cost and turns under per-case caps; judge markers binary, 1–5 dimensions logged only; judge pinned and from another model family where possible.
- **Verdicts:** FAIL blocks (an invariant broken, a 3/3 case at ≤1/3, a pairwise sign test preferring main at p<0.05). INCONCLUSIVE (a 3/3 case at 2/3, or median cost or turns moving more than 30% either way) re-runs three trials once, then asks for a one-line justification in the PR. PASS otherwise.
- **Budget:** abort a trial at 2× its baseline cost and a run at $12; dedicated eval keys with provider spend limits.
- **Storage:** step summary and a sticky PR comment; `eval-results.jsonl` artifact; `tests/eval/baselines.json` changes only through a ratchet PR.
- **Rollout:** two weeks in shadow plus an A/A run on unchanged main; required once A/A shows zero false FAILs.
- **Cost (estimate, to be measured):** ~$4.5 for insights only; ~$7–8.5 for all three agents; judge ~$0.3.

This tier catches breakage and large regressions. It cannot see a 3-point
drift at five cases; that is the nightly history's and the session audits' job.

### Tier 2 — nightly and weekly

- **Nightly** on main: the regression set, default provider, k=1; refresh cassettes and the pairwise baseline; open an issue after two failures. ~$1.5.
- **Weekly provider matrix:** every V1 default at k=3. This becomes the **model admission list** the audit eval already describes: a model failing two weeks running is flagged in the picker.
- **Weekly capability set:** ten harder cases (multi-turn via the N-1 method, the full 7-slide post, the in-depth audit, cross-connector questions), not gating. A case graduates after three consecutive pass^3 nights.
- **Private replay:** the ledger's bundles against main, graded, deltas written back to the ledger. Customer data never enters public CI.

## The loop: from a signal to a case

1. Signal: a ledger proposal, a user correction (a `feedback` memory), an issue, a tier-2 failure.
2. Reduce: `make session-bundle`. A harness or prompt cause that reproduces on synthetic data becomes a public case in `tests/eval/cases/<agent>/`; otherwise it stays a private replay.
3. Label: the auditor's grades go to `tests/eval/calibration/`. A judge marker gates only once it agrees with 30+ labels at ≥85% (a proposed bar, not sourced).
4. Test the test: the case fails on the commit that produced the bad session and passes on the fix.
5. Prune: about 20 regression cases per agent; a case silent for 60 days retires to the capability set.

## Proposed rule for `backend/AGENTS.md`

Lands with tier 1, not before, because it names a workflow that does not exist yet.

- `make test` is tier 0. A harness change adds a fake-model test for the invariant it touches, never a prompt-wording test.
- A change under `agents/`, to `service/profile.py` or `service/memory.py`, or a lock bump of an agent package runs `agent-eval.yml`. FAIL does not merge; INCONCLUSIVE needs a line in the PR saying why it is acceptable.
- A model, tier or effort default change regenerates `make dump-prompts` and needs a green run on every provider whose default moved.
- A change that trades quality for cost or speed is never a no-op: the cost, turn and pairwise deltas go in the PR body.
- A bug found in a session ships with a case that fails on main and passes on the branch, on synthetic data.
- Never raise k, lower a threshold or delete a case to turn a run green; loosening the gate is its own PR with the A/A numbers.

## Before any of this

Prerequisites: a DB-free replay entry point; audit and content writing a
`CONTEXT` row; an insights-brief rubric with binary markers; `eval-scorecard.json`
removed and gitignored. Only the owner can create dedicated eval keys with
spend limits, decide whether synthetic fixtures are enough, and make the check
required. New scope: three issues through `prioritize` (tier 0, tier 1 in
shadow, tier 2).

## Sources

- Anthropic, Demystifying Evals for AI Agents, 2026-01-09 — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic, An update on recent Claude Code quality reports, 2026-04-23 — https://www.anthropic.com/engineering/april-23-postmortem
- Anthropic, Quantifying Infrastructure Noise in Agentic Coding Evals, 2026-02-05 — https://www.anthropic.com/engineering/infrastructure-noise
- OpenAI, Testing Agent Skills Systematically with Evals, 2026-01 — https://developers.openai.com/blog/eval-skills
- LangChain, Agent Evaluation Readiness Checklist, 2026-03-27 — https://www.langchain.com/blog/agent-evaluation-readiness-checklist
- LangChain, Human Judgment in the Agent Improvement Loop, 2026-04-09 — https://www.langchain.com/blog/human-judgment-in-the-agent-improvement-loop
- LangChain `agentevals` — https://github.com/langchain-ai/agentevals
- Google, Driving the Agent Quality Flywheel from Your Coding Agent, 2026-06-30 — https://developers.googleblog.com/en/driving-the-agent-quality-flywheel-from-your-coding-agent/
- AgentAssay, arXiv 2603.02601 — https://arxiv.org/abs/2603.02601
- AgentLens, arXiv 2605.12925 — https://arxiv.org/abs/2605.12925
- Harness-Bench, arXiv 2605.27922 — https://arxiv.org/abs/2605.27922
- tau-bench (pass^k), arXiv 2406.12045 — https://arxiv.org/abs/2406.12045
- Red Hat, Eval-Driven Development, 2026-03-23 — https://developers.redhat.com/articles/2026/03/23/eval-driven-development-build-evaluate-ai-agents
- Husain & Shankar, binary vs Likert — https://hamel.dev/blog/posts/evals-faq/why-do-you-recommend-binary-passfail-evaluations-instead-of-1-5-ratings-likert-scales.html
- Inspect AI options (epochs, `pass_k`) — https://inspect.aisi.org.uk/options.html
