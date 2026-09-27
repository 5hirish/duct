# Analysing data with code in the insights agent

**Author:** Shirish Kadam · **Date:** 2026-09-27

Should the insights agent analyse connector data by writing code ("CodeAct",
programmatic tool calling, code mode) instead of reading rows into its
context? **Yes, but for accuracy, not speed.** On Duct's workload (tabular
marketing metrics, one to twenty fetches per brief) the measured wins that
transfer are arithmetic ones: a replay of a real brief reasoned correctly and
added wrong (2,504 against 2,681 sessions). Token and latency savings are real
only for large pulls. So the first step needs no sandbox at all: **Duct computes
the totals itself, on the server**, and model-written code follows for what no
catalog rule anticipates.

## Evidence

| Source | Result | Transfers? |
|---|---|---|
| Anthropic, *Code execution with MCP* (2025-11) | 150k → 2k tokens piping a document between tools | Mostly no: Duct never passes rows tool to tool. "Filter in the sandbox before the model sees it" applies to big pulls only |
| Claude docs, programmatic tool calling | +11% score, −24% input tokens on search tasks; **~8% more cost** on τ²-bench (1–2 calls per turn) | The τ²-bench row is the one shaped like Duct; the docs call few, small calls a weak fit |
| Microsoft Agent Framework, CodeAct (2026-04) | −52% latency, −64% tokens on one synthetic 5-tool chain, one run pair | An upper bound; Microsoft says keep tool calling at 1–2 calls per turn, and Duct already fetches in parallel |
| CodeAct (ICML 2024) | up to +20 points success, 30% fewer actions | Direction right, 2024 models |
| Program of Thoughts (TMLR 2023) | ~+12% on numeric reasoning over tables (FinQA, TAT-QA) | **Yes**: the same class of error as the replay |
| Cloudflare *Code Mode* (2025-09) | no numbers | The security shape: no outbound network, capabilities handed in, credentials kept by the supervisor |

Sandboxes: `langchain-sandbox` is archived and not for production; smolagents
says no local Python sandbox is fully secure; Anthropic's code-execution
container is not zero-data-retention eligible and keeps data up to 30 days.

## Where Duct is today

- One tool, `FetchData(entity_id, date_from, date_to)` (`agents/insights/data_tools.py`). The result is compacted losslessly (`agents/core/compaction.py`, folded CSV, verified structurally), then cut mid-structure past 60k characters.
- Row caps before that: GA4 landing pages 250, Ads `LIMIT 100`. Search Console pages through up to 50,000 rows, computes totals over all of them, then shows the top 300 — already a handle-shaped fetcher, except the rest are discarded.
- The session cache is keyed on the strings the model typed, so a relative window and the same dates written out are two entries; the verifier shares it but reads a second full copy of every body.
- `TOOL_RESULT` rows store the body after cutting, never the raw rows, so a replay freezes the original output format.
- The catalog already carries what server-side arithmetic needs: per-field `unit` and `agg: sum|avg`. The prompt says "totals before rows"; the model still does the adding.
- **The RunPython prototype** (`.worktrees/insights-analysis-depth`, uncommitted, well behind `main`): a per-session table store fed by FetchData, code and rows sent inline to a Pyodide worker in the browser, locked down to a pinned package prefix, per-device limits. It does not show code more rows than the model sees, does not reach the verifier, cannot run in replays (`interactive=False`), waits out its full timeout on a dropped connection, and cold-starts on first use.

## Design

### Two kinds of arithmetic

1. **Duct-written, deterministic, on the server:** totals of `agg: sum` fields, row counts, weighted rates where the catalog names the weight, coverage shares. Trusted code, every provider, scheduled briefs included. This alone fixes the replay's error.
2. **Model-written, sandboxed (RunPython):** classification rules, medians and tails, concentration, weekly shape, joins across pulls. Never in the API process.

### Pulls and handles

A framework-free `agents/insights/pulls.py` holds a per-session `PullStore`.
Every `ok` fetch becomes a `Pull`: a readable id
(`ga4_landing_pages:2026-08-28:2026-09-26`, plus the entity id as an alias for
the latest), connector, **resolved** window, typed columns from the catalog,
all rows, a `sha256` of the canonical rows, and the fetcher's own totals.
Fetchers return every row they fetched; the top-K cut moves into the view
builder. In process, capped, least-recently-used; not in graph state, which is
checkpointed every step. A handle whose pull is gone after a restart answers
`expired`, and the next fetch refills it.

### What the model sees

```
{status, entity_id, window, pull: "ga4_landing_pages:2026-08-28:2026-09-26",
 schema: [{name, type, unit, agg}], row_count: 250,
 totals: {sessions: 2681, conversions: 41},
 rates: {bounce_rate: {weighted_by: "sessions", value: …}},
 rows: "[250]{…}"   | top-K with rows_shown and coverage,
 note: "Quote totals from `totals`; never re-add rows."}
```

Small pulls keep every row inline, so nothing regresses and a model with no
executor still reads every number. `agg: avg` fields get no unweighted mean
(averaging per-page rates is its own error); the catalog gains `weight`, held by
the catalog contract test.

### What code sees

`RunPython(code, pulls=[…])` loads the named pulls as full DataFrames. The
event carries references and hashes, not rows; the app fetches each pull from
an owner- and membership-checked route and hands the buffer to the worker, so
the worker never talks to Duct. The worker starts when the workspace mounts
and reports readiness; with no live executor RunPython answers `unavailable`
at once. Pending runs sit on the session-state route beside pending pauses, so
a reconnect picks them up.

### The verifier

It reads views through the same store instead of second copies. Its
deterministic checks (spend without conversions, totals that should reconcile,
step changes) become Duct functions in `agents/insights/checks.py`; the LLM
verifier keeps the judgement. That is aimed at its 66 seconds of a 198-second
brief.

### Citations

Every derived figure comes from a tool output: a `totals` field or a RunPython
`result`. The brief lists the runs it used. A provenance check before publish
extracts every figure of three or more significant digits and looks it up in
the session's outputs: a metric first, a gate later.

### Executors

One framework-free interface, `Executor.run(code, frames, limits)`:

- **Browser** — interactive sessions, every provider.
- **Replay** — the same pinned Pyodide under Node or Deno with no network, behind `session_replay.py`, so replay numbers are the numbers a user would see.
- **None** — scheduled briefs today: server totals and deterministic checks still apply.
- **Anthropic accelerator** — optional and opt-in: `code_execution` plus a `LoadPull` tool callable only from code, which is also a no-browser path on Anthropic keys. Not a security boundary (a direct call returns the view, never full rows), not ZDR-eligible, and whether `langchain-anthropic` passes `allowed_callers` through a LangGraph loop is unverified: spike first.
- **Cloud** — a micro-VM behind the same interface for the no-browser case, planned separately.

## Phases

| Phase | Change | Measured by |
|---|---|---|
| 0 | Replay set: 10–20 bundles with ground-truth figures; `session_replay.py` re-renders stored bodies and writes tokens, calls, time, cost and figure errors | baseline, 3 runs per bundle |
| 1 | Server `totals`/`rates` from catalog `agg`/`weight`; handles on the resolved window; one prompt line. ~150 lines, no sandbox | total-type errors → 0; tokens ±5%; time unchanged |
| 2 | RunPython by reference: rebase the prototype, the store and route, early worker, readiness, reconnect, replay executor | derived-figure errors; added time p50 under ~5 s |
| 3 | Fetchers return all rows; top-K views with coverage; verifier checks in code | verifier time (66 s baseline); tokens on Search Console-heavy briefs |
| 4 | No-browser executors: the Anthropic spike, then cloud | scheduled vs interactive figure errors |

If Phase 1 removes most baseline errors, Phase 2 is a smaller bet than it
looks. Each phase is an issue through `prioritize` first.

## Risks

- **Injection steering the code:** code sees only the rows it was handed and prints; the worker lockdown holds its outbound traffic and should also remove `indexedDB`, `caches` and `BroadcastChannel`.
- **Browser memory:** device row limit, a size estimate before running, the worker killed on timeout.
- **Round-trip latency:** warm the worker at mount, fail fast on readiness, cache pulls by hash, one script per step.
- **Wrong but running code:** the method note, the code on the activity card, the provenance check, and a verifier reading the same views.
- **Desktop:** the shell loads the hosted app, so the hosted worker headers apply; workers and WebAssembly were checked in Playwright WebKit, not yet in the shell.
- **Store memory on one API process:** a per-session cap and freeing on close.

## Sources

- Anthropic, Code execution with MCP, 2025-11-04 — https://www.anthropic.com/engineering/code-execution-with-mcp
- Claude docs, Programmatic tool calling — https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling
- Claude docs, Code execution tool — https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
- Anthropic, Writing effective tools for agents, 2025-09-11 — https://www.anthropic.com/engineering/writing-tools-for-agents
- Cloudflare, Code Mode, 2025-09-26 — https://blog.cloudflare.com/code-mode/
- Microsoft Agent Framework, CodeAct, 2026-04-23 — https://devblogs.microsoft.com/agent-framework/codeact-with-hyperlight/
- Wang et al., Executable Code Actions Elicit Better LLM Agents, ICML 2024 — https://arxiv.org/abs/2402.01030
- Chen et al., Program of Thoughts Prompting, TMLR 2023 — https://arxiv.org/abs/2211.12588
- smolagents, Secure code execution — https://huggingface.co/docs/smolagents/tutorials/secure_code_execution
- langchain-sandbox (archived) — https://github.com/langchain-ai/langchain-sandbox
- PRO-LONG, arXiv 2607.20064 — https://arxiv.org/abs/2607.20064
- headroom — https://github.com/chopratejas/headroom
- Pyodide constraints — https://pyodide.org/en/stable/usage/wasm-constraints.html
