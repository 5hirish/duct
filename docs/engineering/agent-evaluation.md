# Agent output QA — the LLM-as-judge eval harness

How we test agents whose output is **subjective** (a TikTok post, an SEO audit, a
brief), why we do it this way, and where to take it next. The harness lives in
`backend/tests/eval/`; the first consumer is the content agent
(`backend/tests/test_content_post_e2e.py`).

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
  its own rubric (`rubrics/content_post.py`). Audit/insights can add theirs.
- **`JudgeVerdict` (structured output) + a deterministic `Scorecard`** — the
  judge returns scores + rationale; *we* compute the weighted overall, the
  per-dimension floors, and the marker gates. Scoring lives on our side so
  thresholds are auditable and stable across judge runs.
- **`judge.py`** — one **Gemini** `generate_content` call: rubric + artifact text
  + **images as parts**, with `response_schema=JudgeVerdict` (typed output — no
  JSON-shape prompting). Gemini is chosen precisely for native multimodality:
  image dimensions (composition, legibility at a glance, on-brand styling) are
  graded on the actual pixels, in the same request as the copy.
- **`prompts.py`** — the judge's system prompt + persona framing, in one place to
  review and tune.
- **Live e2e** runs the real agent → generates an image → judges it; **offline
  tests** (`test_eval_framework.py`) lock the scoring logic and run on every PR.

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
