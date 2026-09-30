# Agent output QA — the LLM-as-judge eval harness

**Author:** Shirish Kadam, Claude · **Updated:** 2026-09-30

How we test agents whose output is **subjective** (a TikTok post, an SEO audit, a
brief), why we do it this way, and where to take it next. The harness lives in
`backend/tests/eval/`. Its consumers: the **eval gate** on agent PRs (below),
and the live content and audit tests (`test_content_post_e2e.py`,
`test_audit_eval.py`). The design and the evidence behind it are in
[`2026-09-27-agent-eval-gating-design.md`](2026-09-27-agent-eval-gating-design.md).

## The gate on agent changes

Three tiers; the first two exist.

| Tier | Runs | What | Where |
|---|---|---|---|
| 0 | every PR, offline, free | what is *sent* to the model: the system prompt and tool schemas byte-stable across calls, the history append-only; the gate's own arithmetic and verdicts; model, tier, effort and run limits rendered in the prompt dump | `tests/test_request_invariants.py`, `tests/test_eval_gate.py`, `make dump-prompts` |
| 1 | PRs touching `backend/agents/**`, memory, profile or the lock; shadow for now | each case k=3 on a synthetic account, verdict against `tests/eval/baselines.json` | `make agent-eval`, `.github/workflows/agent-eval.yml` |
| 2 | nightly and weekly | the provider matrix, harder capability cases, private replays | not built |

**A case** (`tests/eval/cases/`) is a question, a synthetic business, and a
simulated account that answers **any** window from daily series, installed
under the real `fetch_entity`, so envelopes, totals and the payload cut are
production code. Solo's world plants one story (the tax guide slipped in
Search Console); a good brief finds it. Customer sessions never become cases:
the repository is public. A bug from a real session becomes a case when it
reproduces on a synthetic account, and otherwise stays a private replay.

**A trial passes** when every deterministic check holds (the run finished with
a brief and no error event; the named entities were read; the brief quotes a
total exactly as Duct computed it) and every **binary** judge marker does. The
1–5 dimensions are logged, never gated: a blended score hid a failure a
HONORED/IGNORED rubric exposed, and binary answers resist self-preference far
better than scores do. A **provenance** share (figures of three or more
significant digits found in the run's pulls) is reported as a metric first.

**Verdicts per case.** PASS: passed as often as its baseline. INCONCLUSIVE: one
trial short, or median cost or model calls moved more than 30% either way (an
effort downgrade shows first as a cost drop); the CLI runs three more once.
FAIL: two or more short. A case's trials run at once, each on its own thread,
so a run takes about as long as its slowest trial. A per-trial cost, call and
time cap stops a runaway, a trial that will not stop when cancelled is
abandoned (a stalled OpenRouter stream once held a run for three hours), and
the run budget is checked before each batch. `--write-baseline` is for a
ratchet PR only; never raise k, lower a threshold or drop a case to turn a run
green.

**Reading a failed trial.** The step summary gives each failing trial's
reasons and, for one that wrote no brief, the last thing it said in chat and
any file it wrote to its scratch filesystem instead. `eval-results.jsonl`,
kept as the run's artifact, holds every trial's brief, chat reply, tool calls,
scratch files, pulls and judge card. A judge verdict that leaves markers out
is asked for again, then counted as a judge outage (the trial is judged on
its deterministic checks alone), never as the brief's failure.

**Models.** The agent defaults to DeepSeek V4 Flash on OpenRouter and the text
judge to GLM 5.3 Flash. Both started on DeepSeek V4 Pro, where a trial measured
$0.03-0.11 and a PR run of 3-6 trials about $0.25; on every push to a busy PR
that emptied the CI key's credits in two days (2026-09-29). Flash is about a
sixth of that per trial. The judge moved to another family, which ends the
self-preference risk of an agent graded by its own kind, and at 2026-09-30 GLM
5.3 Flash scored above V4 Pro on Artificial Analysis's Intelligence Index (42
against 36) at a fifth of the price. OpenRouter serves it through dozens of
hosts, some unable to make the verdict's tool call and some at fp4, so the
judge's request is pinned to hosts that take every parameter at fp8 or better
(`TEXT_JUDGE_ROUTING` in `tests/eval/client.py`), and asks for low reasoning
effort (`TEXT_JUDGE_REASONING`): at its default depth GLM thought for 11-20k
tokens per brief, took three minutes a verdict, and sometimes answered in prose
with no verdict at all. The judge is also told which sources the project had
connected, since `invented_source` cannot be judged without it. Re-grading 43
stored briefs, GLM agreed with V4 Pro's verdicts on 96% of checks, and every
difference was GLM failing a brief Pro had passed. On the briefs read by hand
GLM was right: Pro passed briefs that never said the tax guide fell. The Flash
baseline is 18 trials (14 passed, $0.005 median), because three six-trial
runs of it came in at 3, 4 and 5 passes, too wide to set a bar with. A
baseline records its model,
and a run on another model is INCONCLUSIVE until `--write-baseline` records
one. `--provider` / `--model` run any other; the text judge follows
`DUCT_JUDGE_PROVIDER` / `DUCT_JUDGE_MODEL`.


## Why a critique agent, not assertions

For subjective deliverables "correct" isn't a string match. Exact-match asserts
miss the failures that matter — a weak hook, an off-brand image, a flattened
narrative all still "validate" structurally. So we grade real output with a
**critique agent**: a third-party LLM judge that scores the artifact against a
rubric and gates a threshold. This is the standard *LLM-as-a-judge* pattern. We
add a **persona** so the judge assesses *as the end user* ("masking as the
user") — for short-form content, a sound-off short-form scroller reacting to the
hook, per-slide retention, and save/share-worthiness — rather than as a neutral
grader.

## What we built (`backend/tests/eval/`)

- **`Rubric` / `Dimension` / `Marker`** — weighted 1–5 dimensions, present/absent
  markers, a `pass_threshold`, and a `persona`. Agent-agnostic; each agent ships
  its own rubric (`rubrics/content_post.py`, `rubrics/audit_report.py`; insights
  can add its own). A rubric's renderer must show the judge the whole
  deliverable: the audit judge once failed two reports for an "empty"
  roadmap because the renderer printed the phase labels without the tasks.
- **`JudgeVerdict` (structured output) + a deterministic `Scorecard`** — the
  judge returns scores + rationale; *we* compute the weighted overall, the
  per-dimension floors, and the marker gates. Scoring lives on our side so
  thresholds are auditable and stable across judge runs.
- **`judge.py`** — two judges. A rubric with **images** gets one **Gemini**
  `generate_content` call: rubric + artifact text + images as parts, with
  `response_schema=JudgeVerdict`. Gemini is chosen for native multimodality:
  image dimensions (composition, legibility at a glance, on-brand styling) are
  graded on the actual pixels. A **text** rubric (the insights brief, the
  audit report) goes through Duct's own `resolve_chat_model` with
  `with_structured_output(JudgeVerdict)`, on OpenRouter by default.
- **`prompts.py`** — the judge's system prompt + persona framing, in one place to
  review and tune.
- **Live e2e** runs the real agent → generates an image → judges it, on the
  provider `DUCT_EVAL_PROVIDER` names (Claude by default; the Actions workflow
  runs a Claude leg and a Gemini leg). A second live test drives plan mode —
  enrichment, the research sub-agents, WebSearch — and asserts one real plan
  landed, with no rubric: it is the machinery check for the capabilities the
  V1 port had to rebuild. **Offline tests** (`test_eval_framework.py`) lock the
  scoring logic and run on every PR.

## Best practices we follow (and the biases behind them)

LLM judges have well-documented biases; design around them.

- **Verbosity / formatting bias** — judges over-reward long, fluent, well-formatted
  answers regardless of substance. → The system prompt explicitly says not to
  reward length, formatting, or fluent prose; the rubric scores substance.
- **Self-preference bias** — a model scores its *own* outputs higher. ⚠️ Our
  judge is Gemini and our images are Gemini-generated, so the **image**
  dimensions carry some self-preference risk; the copy is Claude-generated
  (cross-model, lower risk). Mitigation today: humans spot-check image quality;
  later option: a second/different-provider judge for image dimensions.
- **Position bias** — order changes the verdict. Only applies to *pairwise*
  judging; we do *pointwise/absolute* scoring, so it's not in play. If we add A/B
  regression, randomize order and average both orders.
- **Determinism** — low temperature + structured output + our own threshold math.
- **Calibrate against humans** — an LLM judge is only trustworthy once its scores
  correlate with human ratings on a sample. Treat `pass_threshold`/weights as
  provisional until calibrated.

## Persona / user-simulation — and its limits

Persona-driven evaluation (the judge "masking as the user") is an active,
effective technique for content and conversational agents. **Caveat from the
literature:** LLM-simulated users are *unreliable proxies* for real users — they
over-ask, are over-polite, and can systematically diverge — so persona-judging
is a cheap, fast proxy, **not** a replacement for real engagement signal
(retention, saves, shares). Use it to catch regressions early; validate against
real metrics before trusting absolute numbers.

## What others do (landscape, 2025–26)

- **CI gating (lightweight, code-defined):** Promptfoo (now part of OpenAI;
  strong red-teaming), DeepEval, RAGAS. Our harness sits in this tier.
- **Platforms (tracing, human annotation, regression, dashboards):** Braintrust,
  LangSmith, Arize **Phoenix** (already a backend dev dependency here), Helicone.
- The recommended division of labor: a lightweight framework for CI gating +
  a platform for human annotation and regression tracking. A natural next step is
  exporting our scorecards into Phoenix for trend/regression views.

## How to extend

- **More agents:** define a `Rubric` (+ persona) for the deliverable and reuse
  `evaluate()` / `assert_scorecard`.
- **Trajectory (process) eval:** today we grade the *outcome* (the final post).
  Add *process* checks from the emitted events — did the agent call the right
  tools, avoid banned ones, stay within turn/budget limits.
- **Regression / A-B:** pairwise-judge old vs. new on a fixed topic set
  (randomize order) to catch drift between prompt/model changes.
- **Human calibration:** periodically hand-score a sample and check judge↔human
  correlation; adjust thresholds and weights from that.
- **Multi-judge:** average independent judges for high-stakes dimensions to blunt
  single-model bias (with the caveat that naive multi-agent panels can *amplify*
  shared biases — keep them independent).

## Sources

- [LLM-as-a-Judge overview](https://www.emergentmind.com/topics/llm-as-a-judge-evaluations)
- [Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge](https://llm-judge-bias.github.io/)
- [Position Bias in LLM-as-a-Judge (ACL 2025)](https://aclanthology.org/2025.ijcnlp-long.18/)
- [Self-Preference Bias in LLM-as-a-Judge](https://arxiv.org/pdf/2410.21819)
- [Lost in Simulation: LLM-Simulated Users are Unreliable Proxies](https://arxiv.org/html/2601.17087)
- [Persona-driven user simulation for evaluating conversational agents (EMNLP 2025)](https://aclanthology.org/2025.emnlp-industry.16/)
- [Evaluating AI agents — lessons from Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- [LLM evaluation platforms comparison (Arize)](https://arize.com/llm-evaluation-platforms-top-frameworks/)
