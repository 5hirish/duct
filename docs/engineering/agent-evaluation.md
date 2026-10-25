# Agent output QA

**Author:** Shirish Kadam, Claude · **Updated:** 2026-10-26

Duct's agents write briefs, audits and posts, so no test can assert the one right answer. This is how we learn whether a change made an agent worse, before it merges.

## At a glance

- **A judge grades, our code decides.** A second model reads each deliverable against a rubric; we turn its answers into pass or fail.
- **Only yes/no checks gate.** Quoted totals, entities read, binary rubric markers; the judge's 1 to 5 scores are logged, never gated.
- **Pass means as often as before.** Each case is held to a recorded baseline on the same model.
- **Every case is synthetic.** A fictional business with a planted story; customer sessions never enter a public repository.

## Three tiers, two built

| Tier | Runs | Checks | Lives in |
|---|---|---|---|
| 0 | Every PR, offline, free | The request sent: system prompt and tool schemas byte-stable across calls, history append-only; the gate's own arithmetic; model, tier, effort and run limits in the prompt dump | `tests/test_request_invariants.py`, `tests/test_eval_gate.py`, `make dump-prompts` |
| 1 | PRs touching agent code, memory, profile or the lock, and merges to main that do. Shadow (reports, never blocks) until an A/A window on main shows no false FAIL | Each case on a synthetic account: three trials on a PR, six on main, a verdict against its baseline | `make agent-eval`, `agent-eval.yml` |
| 2 | Nightly and weekly | Provider matrix, harder capability cases, private replays | Not built; see the [design record](2026-09-27-agent-eval-gating-design.md#design) |

## A case plants a story; a trial must find it

A case is a question, a fictional business and a simulated account that answers any date window from daily series, installed under the real data fetch. Solo's world plants one story: the freelance tax guide slipped in Search Console.

> **Rule:** no customer session becomes a case; this repository is public. A real bug becomes a case once it reproduces on a synthetic account, else it stays a private replay ([the registry](../../backend/tests/eval/cases/__init__.py)).

A trial is one real agent session on the case. It passes when every deterministic check holds (a brief, no error event, the named entities read, a total quoted exactly as Duct computed it) and every binary judge marker does.

The judge's 1 to 5 scores are logged, never gated: a blended score once hid a failure a yes/no rubric exposed, and yes/no answers resist a judge favouring its own kind.

## Verdicts are relative to a baseline

A baseline is a recorded run of the unchanged agent: pass rate, median cost and calls, on a named model.

| Verdict | Means | Then |
|---|---|---|
| PASS | Passed as often as the baseline | Merge |
| INCONCLUSIVE | One trial short; or median cost or model calls moved over 30% either way (an effort downgrade shows first as a cost drop); or the baseline is from another model | Three more trials once, locally; on a PR, one line saying why it is acceptable |
| FAIL | Two or more trials short | The change broke the case |

> **Rule:** never raise the trial count, lower a threshold or drop a case to turn a run green. Loosening the gate is its own PR, with the numbers.

## Judge biases we design around

Text (the brief, the audit report) goes to GLM 5.3 Flash on OpenRouter through Duct's own model transport; images (the post's slides) to one Gemini call that reads the pixels. The judge returns scores and rationale; we compute the overall, floors and marker gates, so thresholds stay auditable.

The text judge also learns which sources the project had connected; "cites a source it never had" cannot be judged otherwise.

| Bias | Our answer |
|---|---|
| Verbosity: long, fluent, formatted answers win | The judge prompt forbids rewarding length, formatting or fluency; the rubric scores substance |
| Self-preference: a model favours its own output | GLM judges DeepSeek text. Gemini judges Gemini-made slides (the copy is Claude-made): humans spot-check images; a second-provider image judge is the later option |
| Position: order sways a pairwise verdict | We score pointwise. If A/B regression comes, randomise order and average both |
| Noise: same input, different verdict | Low temperature, structured output, our own threshold math |
| Miscalibration: scores drift from human judgment | Thresholds and weights stay provisional until judge scores correlate with human ratings on a sample |

> **Gotcha:** a persona (the judge "masking as the user", say a sound-off scroller judging a hook) is a cheap proxy: simulated users over-ask, are over-polite and diverge systematically. Catch regressions with it; trust absolute numbers only against real retention, saves and shares.

## Add a case

1. **Write or reuse a rubric** under `tests/eval/rubrics/`: dimensions, binary markers, pass threshold, persona. Its renderer must show the judge the whole deliverable.
2. **Build the world.** Extend Solo's accounts or add a synthetic business; plant the story a good answer must find.
3. **Define the case** in `tests/eval/cases/`: question, context, world, entities to read, totals to quote, markers, caps; register it in `CASES`, a new agent also in `AGENT_PATHS`.
4. **Check the check.** The case fails on the commit that produced the bad session and passes on the fix.
5. **Record a baseline**; a content or audit case also lifts its exclusion in `agent-eval.yml`.

## Re-record a baseline

Only in its own ratchet PR, after a change you mean to keep.

1. **Run enough trials.** Three six-trial runs of one agent spread from 3 to 5 passes, so the current baseline pools 18.
2. **Write it.** `make agent-eval ARGS="-k 18 --write-baseline"` records pass rate, medians, model and date in `tests/eval/baselines.json`.
3. **Put the numbers in the PR body,** and nothing else in the diff.

> **Remember:** yes/no checks gate, scores inform, and a case passes when it passes as often as before.

## Reference

Files in `backend/`:

| File | Holds |
|---|---|
| [`tests/eval/gate.py`](../../backend/tests/eval/gate.py) | `Case`, `Trial`, the verdict rules, caps, figure tracing, the report |
| [`tests/eval/cases/`](../../backend/tests/eval/cases/__init__.py) | The registry (`CASES`, `AGENT_PATHS`), Solo's accounts (`solo_world.py`), the insights cases. The account is installed under the real `fetch_entity`, so envelopes, totals and the payload cut are production code |
| [`tests/eval/rubric.py`](../../backend/tests/eval/rubric.py) | `Rubric`, `Dimension` (weighted 1 to 5, with a `min_score` floor), `Marker` (required or forbidden), `pass_threshold`, `persona` |
| [`tests/eval/verdict.py`](../../backend/tests/eval/verdict.py) | `JudgeVerdict`, the judge's structured output; `Scorecard`, what we compute from it |
| [`tests/eval/judge.py`](../../backend/tests/eval/judge.py) | `evaluate()`: the text judge (Duct's own `resolve_chat_model`, structured output, cheap enough for every agent PR) and the Gemini vision judge (one call: rubric, text and images in, typed JSON out, so legibility and composition are graded on the pixels) |
| [`tests/eval/prompts.py`](../../backend/tests/eval/prompts.py) | The judge's system prompt and persona framing, in one place |
| [`tests/eval/client.py`](../../backend/tests/eval/client.py) | Judge credentials, `TEXT_JUDGE_ROUTING`, `TEXT_JUDGE_REASONING` |
| [`tests/eval/assertions.py`](../../backend/tests/eval/assertions.py) | `assert_scorecard` for pytest |
| [`tests/eval/rubrics/`](../../backend/tests/eval/rubrics/) | `insights_brief.py` (binary markers gate), `content_post.py`, `audit_report.py`. A renderer shows the judge the whole deliverable: the audit judge once failed two reports for an empty-looking roadmap because the renderer printed the phase labels without their tasks |
| [`tests/eval/baselines.json`](../../backend/tests/eval/baselines.json) | One entry per case: pass rate, medians, trials, provider, model, date |
| [`tests/eval/memory_recall.py`](../../backend/tests/eval/memory_recall.py) | The judge-free memory retrieval eval (50 questions, five axes), run by `tests/test_memory_retrieval.py` |
| [`scripts/agent_eval.py`](../../backend/scripts/agent_eval.py) | The CLI behind `make agent-eval`; points `DATABASE_URL` at a throwaway SQLite, never a real database |

Consumers of the harness:

| Consumer | Runs | Judge | Trigger |
|---|---|---|---|
| The eval gate (`agent-eval.yml`, `make agent-eval`) | The insights case on Solo's accounts | Text judge | Agent PRs and merges to main; triggers below |
| [`tests/test_content_post_e2e.py`](../../backend/tests/test_content_post_e2e.py) | The real content agent drafts a post, generates a slide image and is judged. A second test drives plan mode (enrichment, research sub-agents, WebSearch) with no rubric: one real plan must land | Gemini vision judge | `content-eval.yml`, manual, a Claude leg and a Gemini leg (`DUCT_EVAL_PROVIDER`, Claude by default) |
| [`tests/test_audit_eval.py`](../../backend/tests/test_audit_eval.py) | A real audit of a site you own, per candidate model | Text judge, or Gemini without an OpenRouter key | By hand, `-m live` |
| [`tests/test_eval_framework.py`](../../backend/tests/test_eval_framework.py) | Scoring logic, rubric rendering, credential resolution | None | Every PR |

Tier 1 triggers (`.github/workflows/agent-eval.yml`):

| Setting | Value |
|---|---|
| Paths | `backend/agents/**` minus `content/` and `audit/` (no case covers them yet); `service/memory.py`; `service/profile.py`; `poetry.lock`; `tests/eval/**`; `scripts/agent_eval.py`; the workflow itself |
| Draft PRs | Run only with the `run-evals` label |
| Depth | PR: `--no-rerun` (on 2026-09-30 an unchanged agent came back INCONCLUSIVE at 3/6 and 4/6, so a re-run doubled the price of a noisy read); main: `-k 6` |
| Secret | `OPENROUTER_API_KEY`; without it the job says so and passes |
| Shadow | `continue-on-error` until an A/A window on unchanged main shows no false FAIL; making the check required is the owner's decision, in its own PR |

Where a failed trial's evidence is:

| Evidence | Where |
|---|---|
| Each failing trial's reasons | The step summary |
| A trial that wrote no brief | The step summary adds the last thing the agent said in chat and any file it wrote to its scratch filesystem instead |
| Every trial's brief, chat reply, tool calls, scratch files, pulls and judge card | `eval-results.jsonl`, the run's artifact |
| Provenance: the share of figures with three or more significant digits that trace to a pull | The report's Figures traced column; a metric, never a gate |
| A judge verdict that leaves markers out | Asked for again, then counted as a judge outage: the trial is judged on its deterministic checks alone, never failed for it |

CLI flags and settings (`scripts/agent_eval.py`):

| Flag or setting | Default | Does |
|---|---|---|
| `--provider`, `--model` (`DUCT_EVAL_PROVIDER`, `DUCT_EVAL_MODEL`) | `openrouter`, `deepseek/deepseek-v4-flash` | The agent under test |
| `DUCT_JUDGE_PROVIDER`, `DUCT_JUDGE_MODEL` | `openrouter`, `z-ai/glm-5.3-flash` | The text judge |
| `TEXT_JUDGE_ROUTING` | fp8 or better, hosts that take every parameter | Of 33 OpenRouter hosts, seven cannot make the verdict's tool call and five run fp4 |
| `TEXT_JUDGE_REASONING` | low | At default depth GLM thought 11 to 20k tokens per brief, ran past five minutes, and sometimes answered in prose with no verdict |
| `-k` | 3 | Trials per case |
| `--no-rerun` | off | No three more trials after INCONCLUSIVE |
| `--write-baseline` | off | Record this run in `baselines.json` |
| `--no-judge` | off | Deterministic checks only |
| `--budget` (`DUCT_EVAL_BUDGET_USD`) | $3 | Run budget, checked before each batch; judge calls (about a cent) are not counted |
| `--out` | `eval-results.jsonl` | One JSON line per trial |
| `--agent`, `--case` | all | Which cases run |
| Per-case caps | $1, 40 model calls, 15 minutes (the Solo case: $0.60) | Stop a runaway trial. A case's trials run at once, each on its own thread, so a run takes about as long as its slowest trial; one that will not stop is abandoned (a stalled OpenRouter stream once held a run for three hours). The judge gets 5 minutes |

Model history:

| Date | Agent | Judge | Why |
|---|---|---|---|
| 2026-09-28 | DeepSeek V4 Pro | DeepSeek V4 Pro | First gate. A trial cost $0.03 to 0.11, a PR run of 3 to 6 trials about $0.25 |
| 2026-09-29 | | | Every push to a busy PR ran it; the CI key's credits emptied in two days |
| 2026-09-30 | DeepSeek V4 Flash, about a sixth of the cost per trial | GLM 5.3 Flash: a different family, above V4 Pro on Artificial Analysis's Intelligence Index (42 against 36) at a fifth of the price | Cost, and no judge grading its own kind. Re-grading 43 stored briefs, GLM agreed with Pro on 96% of checks; every difference was GLM failing a brief Pro had passed, and on the briefs read by hand GLM was right: Pro passed briefs that never said the tax guide fell |

The baseline today:

| Case | Model | Trials | Passed | Median cost | Median calls | Recorded |
|---|---|---|---|---|---|---|
| `insights/solo-organic-slip` | `deepseek/deepseek-v4-flash` | 18 | 14 (0.778) | $0.0052 | 4 | 2026-09-30 |

Directions not yet built:

| Direction | What it adds |
|---|---|
| Tier 2 | A nightly regression set, a weekly provider matrix (the model admission list), harder capability cases, private replays |
| Trajectory checks | Grade the process from emitted events, not only the outcome: right tools called, banned ones avoided, turn and budget limits kept |
| A/B regression | Pairwise-judge old against new on a fixed topic set, order randomised, to catch drift between prompt or model changes |
| Human calibration | Hand-score a sample periodically; adjust thresholds and weights from the judge-to-human correlation |
| Multi-judge | Average independent judges on high-stakes dimensions. Naive panels amplify shared biases, so keep them independent |
| Phoenix export | Push scorecards into Phoenix, already a dev dependency, for trend and regression views |

Landscape, 2025 to 2026:

| Tier | Tools | Where we sit |
|---|---|---|
| CI gating, lightweight, code-defined | Promptfoo (now part of OpenAI; strong red-teaming), DeepEval, RAGAS | Our harness |
| Platforms: tracing, human annotation, regression, dashboards | Braintrust, LangSmith, Arize Phoenix (already a backend dev dependency), Helicone | The recommended pairing: a light framework for CI plus a platform for annotation and trends |

Sources:

| Source | Supports |
|---|---|
| [LLM-as-a-Judge overview](https://www.emergentmind.com/topics/llm-as-a-judge-evaluations) | The pattern |
| [Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge](https://llm-judge-bias.github.io/) | The bias table |
| [Position Bias in LLM-as-a-Judge (ACL 2025)](https://aclanthology.org/2025.ijcnlp-long.18/) | Position bias |
| [Self-Preference Bias in LLM-as-a-Judge](https://arxiv.org/pdf/2410.21819) | Self-preference |
| [Lost in Simulation: LLM-Simulated Users are Unreliable Proxies](https://arxiv.org/html/2601.17087) | The persona gotcha |
| [Persona-driven user simulation for evaluating conversational agents (EMNLP 2025)](https://aclanthology.org/2025.emnlp-industry.16/) | Persona judging |
| [Evaluating AI agents: lessons from Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/) | Trajectory checks |
| [LLM evaluation platforms comparison (Arize)](https://arize.com/llm-evaluation-platforms-top-frameworks/) | The landscape |
