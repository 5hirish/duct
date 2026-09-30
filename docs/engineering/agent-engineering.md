# Building and changing agents

**Author:** Shirish Kadam · **Updated:** 2026-09-30

How an agent is built and maintained here, on LangChain 1.x, LangGraph and
`deepagents`. Read it before adding an agent or changing one: a prompt, a tool,
a model default, a middleware, a dependency pin. Each rule names the LangChain
primitive that implements it and what enforces it. **A rule with no test is a
note, and notes get skipped** (a study of 481 public `CLAUDE.md` files found
4–16% of their prose security rules backed by a real control; arXiv 2608.23550).
So where a rule can be a test, it is one, and the "Enforced by" column says
which.

The rules are Duct's reading of the harness-engineering literature, indexed in
[`agent-harness-references.md`](agent-harness-references.md). The research
behind the larger items is in four dated records of 2026-09-27: eval gating,
insights code execution, execution approvals and memory freshness.

## The harness, in five files

| File | Owns |
|---|---|
| `backend/agents/core/deep_session.py` | **Assembly** (`build_deep_session_agent`, `build_session_agent`, one `session_middleware` list) and **the loop** (`DeepSession`: turns, pauses, steers, compaction, failure posture) |
| `backend/agents/core/lc.py` | The LangChain adapter: `resolve_chat_model`, `stream_agent`, `interrupt_pause`, `prompt_caching_middleware`, and Duct's own middleware (`ReportedRetryMiddleware`, `SteerMiddleware`, `SeenImagePruneMiddleware`) |
| `backend/agents/core/turn.py` | How every user turn is built: `ContextSpec`, `BLOCK_ORDER` (stable first) |
| `backend/agents/core/errors.py` | One classifier: a failure is a code before it is a message |
| `backend/agents/core/*_tools.py` | Binders: framework-free domain functions, thin LangChain wrappers |

A runner (`agents/<type>/v1/runner.py`) owns tools, prompts, `RunLimits` and
hooks, and imports no framework (`tests/test_harness_boundaries.py`).

## Rules

### Shape

| Rule | Primitive | Enforced by |
|---|---|---|
| Lowest rung that works: one structured call, then a fixed workflow, then `create_agent`, then `deepagents` only for what it adds (sub-agents, scratch filesystem, planning). Say in the runner docstring which of those the agent spends, and re-justify when one is switched off. | `init_chat_model`, `create_agent` (1.x, semver-stable), `create_deep_agent` (0.x, pinned exactly) | review; `backend/AGENTS.md` "Pick the lowest rung" |
| **Build every session graph in one place.** The rung is chosen; the middleware is not. | `build_session_agent` / `build_deep_session_agent` | `tests/test_agent_assembly.py` (a graph built elsewhere fails) |
| A sub-agent exists to isolate context for a bounded side job. Name its tools; never let `deepagents` default them. The auto-added `general-purpose` sub-agent gets **every** parent tool unless one by that name is supplied. | `SubAgent` dicts with explicit `tools` | content: `test_sub_agents_never_get_the_writer_tools`; insights: **gap 1** |

### Tools

| Rule | Primitive | Enforced by |
|---|---|---|
| Few, workflow-level tools with meaningful ids. Insights reaches every connector entity through one `FetchData(entity_id)`. | `StructuredTool` + Pydantic `args_schema` | review |
| Bound every result, and never cut mid-structure: fold losslessly first. | `agents/core/compaction.py`; `FilesystemMiddleware` eviction on the deep rung | per-binder oversized-fixture tests |
| An error is a result that says what to do next, with a code. Never `str(exc)` to a client. | `classify_error`; `ToolErrorMiddleware` (LangChain 1.4, not yet mounted: gap 5) | `tests/test_agent_errors.py` |
| Tool definitions are prompt: they head the cached prefix, so review them like prompt and keep their order deterministic. | — | gap 7 (`make dump-prompts` renders no tools yet) |
| Anything a tool returns from outside Duct (a search query, a page, an ad) is data, never instructions. Label it in the prompt. | — | each agent's system prompt (insights: `BOUNDARIES`) |
| Arithmetic over rows is Duct's, not the model's. A row report carries `totals`, `rates` (ratios of totals, or weighted means, never a mean of rates) and per-dimension `subtotals`, computed from the catalog's `agg`, `ratio` and `weight`, and says what they cover. | `agents/insights/totals.py`, called by `fetch_entity` | `tests/test_insights_totals.py`, the catalog contract test; the eval gate's `must_quote` check |

### Context and caching

| Rule | Primitive | Enforced by |
|---|---|---|
| Per-user and per-project text goes in the USER turn, never the system prompt. Stable blocks first. | `ContextSpec`, `BLOCK_ORDER` | `tests/test_turn.py` |
| Every graph asks for caching. Anthropic caches only a request that says so; Gemini caches implicitly; OpenAI routes by `prompt_cache_key`. | `AnthropicPromptCachingMiddleware` (appended by `create_deep_agent`, by `build_session_agent`, and by `prompt_caching_middleware()` for a one-shot pass); `resolve_chat_model(cache_key=thread)` | `tests/test_agent_assembly.py`; cache share on `TOKEN_USAGE` |
| Duct owns the final system prompt byte for byte. `deepagents` harness profiles append text per model: 0.7.15 ships coding-agent guidance ("Never speculate about code you have not opened…") for Haiku 4.5, Sonnet 4.6 and Opus 4.7, plus profiles for OpenAI Codex models, and packages can register more. | `register_harness_profile` | gap 6 |
| Prune before you summarise, and batch the pruning so each cache break buys something. | `ContextEditingMiddleware` + `ClearToolUsesEdit(clear_at_least=…)` | `RunLimits.__post_init__` (trigger below the summarisation floor) |
| Set the summarisation trigger from `CONTEXT_WINDOW`, not the library's model profile (0.85 × the profile's `max_input_tokens` is ~850k on Opus 5.5 and Sonnet 5.5, where Duct budgets 200k). | `deepagents` `SummarizationMiddleware` with `trigger=("tokens", N)` | gap 3 |
| One emergency compaction and one retry on a real overflow; a second overflow is the ordinary failure. | `compact_thread` in `DeepSession` | `tests/test_deep_session.py` |

### The loop

| Rule | Primitive | Enforced by |
|---|---|---|
| Every agent declares `RunLimits`: model and tool calls per run and per thread. Recursion is derived, never picked. | `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware` | `RunLimits.__post_init__`, `tests/test_deep_session.py` |
| Retry in exactly one layer, the one that reports each attempt and honours `Retry-After`. Provider SDKs retry underneath by default (Gemini up to 6 times), invisibly. | `ReportedRetryMiddleware`; SDK `max_retries=0` | gap 2 |
| Fall back only on transient failures. `ModelFallbackMiddleware` falls back on every exception, auth and overflow included. | classified `ModelFallbackMiddleware` subclass | gap 4 |
| Input typed mid-turn is steered or queued, never refused. | `SteerMiddleware` + the session's `steer_queue` | `tests/test_insights_session.py` |
| A pause is a checkpointed `interrupt()` and survives a redeploy. Work before the interrupt is idempotent, because the node reruns on resume. | `langgraph.types.interrupt`, `Command(resume=…)` | `tests/test_deepagents_harness.py` |
| A thread is keyed on the conversation, never the session. | checkpointer `thread_id` | `backend/AGENTS.md` |
| Run status comes from the stream, in the recorder. A dead process's `running` rows are cancelled at the next boot. | `ConversationRecorder`, `cancel_orphaned_runs` | `tests/test_conversation_run_status.py` |

### Memory

| Rule | Primitive | Enforced by |
|---|---|---|
| One write path (`remember()`), one read path (`search()`), recalled into the USER turn. No `MemoryMiddleware`, no LangGraph `Store`. | `service/memory.py` | `tests/test_memory*.py` |
| A remembered state of an outside system (a campaign's status, a budget, a redirect) is a claim with a date, not a fact. Show its age and re-read it before asserting it. | `volatility()` / `freshness()` in `service/memory.py`; the `seen · Nd · verify` digest line; `MEMORY_DISCIPLINE` | the freshness axis of `tests/test_memory_retrieval.py` (stale-assertion and false-alarm rates held at 0) |

### Humans and authority

| Rule | Primitive | Enforced by |
|---|---|---|
| Authority lives in code, never the prompt. No agent-facing approve or apply tool, in either harness. | `service/execution/policy.py` | `tests/test_execution_policy.py` |
| Nothing that moves money, goes live, or cannot be fully undone applies without a click on that set. | the auto-apply allowlist | `tests/test_execution_policy.py`; the allowlist is under review (gap 8) |
| The agent acts with the user's delegated credentials, scoped to the project at build time. Non-members get 404. | binders take a membership-checked `project_id` | `tests/test_route_auth_boundaries.py` |

### Evals and observability

| Rule | Primitive | Enforced by |
|---|---|---|
| Offline tests drive the real harness with a canned model and assert events, tool names and payloads, never prompt prose. | `ToolCallingFake`, `emitted` | `make test` |
| What is *sent* to the model is tested too: byte-stable prefix across calls, history and reasoning kept, effort passed. The Claude Code regressions of April 2026 were exactly these. | `RecordingFake` (`tests/fakes.py`); the "Model defaults" section of `make dump-prompts` | `tests/test_request_invariants.py` (both rungs and the insights runner); `prompts.yml` fails a default changed without the dump |
| A prompt, model default, effort or harness change is judged k times against a baseline, on synthetic accounts, before it merges. Binary markers gate; 1–5 scores are logged. | `tests/eval/gate.py`, `tests/eval/cases/`, `make agent-eval` (DeepSeek V4 Flash on OpenRouter, GLM 5.3 Flash judging) | `agent-eval.yml` on harness PRs, in shadow until an A/A window; `tests/test_eval_gate.py` holds the gate's own logic. One provider today; the per-provider matrix is tier 2 |
| One span per model call and one per tool call, at one choke point. | `ReportedRetryMiddleware` (model); `awrap_tool_call` middleware (tool) | four binders span tools today (gap, runner-up) |

### Maintenance

| Rule | Enforced by |
|---|---|
| Bump the LangChain stack alone, never inside a grouped Dependabot PR; `poetry install --with dev` locally the same day, or local tests run other versions than CI. | `tests/test_deepagents_harness.py`, `tests/test_agent_assembly.py` |
| A new model is a table migration: `PRICING`, `CONTEXT_WINDOW`, `MODEL_FALLBACK`, tiers, thinking, and a check of the LangChain profile and `deepagents` harness profiles for that id. | the `PRICING`/`CONTEXT_WINDOW` equality test |
| Every harness component names the failure it compensates for, and is re-measured when the model changes. `planning=False` on insights is the worked example: two of five turns were checklist rewrites. | `STYLE.md` (comments carry reasoning) |

## Middleware: what we mount and why

| Middleware | Mounted | Verdict |
|---|---|---|
| `ContextEditingMiddleware` + `ClearToolUsesEdit` | `session_middleware` | keep; add `clear_at_least` |
| `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware` | `session_middleware` | keep; per-tool caps are `RunLimits.per_tool_run_limits` (content caps `generate_video` at 3 a turn) — still to add for `ProposeChanges` and `task` |
| `ModelFallbackMiddleware` | `session_middleware` | keep, classified (gap 4) |
| `ReportedRetryMiddleware` (ours) | `session_middleware` | keep: `ModelRetryMiddleware` has no per-attempt hook and ignores `Retry-After` |
| `SteerMiddleware`, `SeenImagePruneMiddleware` (ours) | `session_middleware` | keep; no prebuilt equivalent |
| `AnthropicPromptCachingMiddleware` | every graph | keep; measure a 1h TTL for idle chats |
| `TodoListMiddleware` | content only | keep as measured |
| `FilesystemMiddleware` | deep rung, no `execute` | keep; never the shell |
| `SubAgentMiddleware` | deep rung | keep; always supply `general-purpose` yourself |
| `SummarizationMiddleware` (deepagents) | deep rung | keep; set the trigger (gap 3) |
| `PatchToolCallsMiddleware` | deep rung | keep |
| `ToolErrorMiddleware` | — | **adopt** (gap 5) |
| `HumanInTheLoopMiddleware` | — | skip: change-set cards and `policy.py` do this |
| `PIIMiddleware` | — | skip; `remember()` redacts. Revisit for traces |
| `LLMToolSelectorMiddleware`, `ProviderToolSearchMiddleware` | — | skip: changing tools per call breaks the cache; tool tokens are small |
| `ModelRetryMiddleware`, `ToolRetryMiddleware`, `LLMToolEmulator` | — | skip: ours reports; `service/rest.py` retries; fakes exist |
| `ShellToolMiddleware`, `FilesystemFileSearchMiddleware`, Claude-native tool middleware | — | never on a server; a capability the model may lack is a Duct tool |

## Checklists

### Adding an agent

1. Run it through the `prioritize` skill.
2. Pick the rung and write down which `deepagents` features it spends.
3. Build it with `build_session_agent` or `build_deep_session_agent` (`tests/test_agent_assembly.py`).
4. Declare its `RunLimits` and a `ContextSpec` (`tests/test_deep_session.py`, `tests/test_turn.py`).
5. Supply every sub-agent, `general-purpose` included, with a named, read-only tool list.
6. Wire `activity_hooks`, and record a `CONTEXT` row so the session can be audited (`tests/test_tool_activity.py`).
7. Classify failures through `agents/core/errors.py`.
8. `make dump-prompts`; write its rubric under `backend/tests/eval/rubrics/` and a synthetic case under `backend/tests/eval/cases/`.
9. `make check`.

### Changing an agent

- **Prompt:** `make dump-prompts` and read the diff as prose (`prompts.yml`). Nothing volatile above the stable blocks. Replay the bundles that motivated it (`make session-replay`) on two providers, and run `make agent-eval` (`agent-eval.yml` runs it on the PR): FAIL does not merge; INCONCLUSIVE needs a line in the PR saying why it is acceptable.
- **Tool:** bound its output; errors carry a code and a next step; decide its activity card; keep writers off every sub-agent list; batch tool changes, since each one invalidates the cache.
- **Model or tier default:** update `PRICING`, `CONTEXT_WINDOW`, `MODEL_FALLBACK` and the tier map together, and add a `RETIRED_MODELS` row for any id the new one replaces; classify it in `CLAUDE_BOUND_THINKING` and `takes_temperature`; check the LangChain profile exists for that id, not just its window (langchain-anthropic 1.7.4 had none for `claude-sonnet-5-5`, which meant `max_tokens=4096` with thinking inside it), and any `deepagents` harness profile; run the live web-search matrix. For an OpenRouter slug, price it at the model vendor's own endpoint (`/api/v1/models/<slug>/endpoints`), not the one price `/api/v1/models` shows, and read the vendor's changelog: a slug pins a build the vendor may already have retired.
- **Middleware:** change `session_middleware`, nowhere else. Re-measure `SUPERSTEPS_PER_MODEL_CALL` (`tests/test_deep_session.py`). Comment the failure it prevents.
- **Dependency bump:** alone; `poetry install --with dev`; `tests/test_deepagents_harness.py` and `tests/test_agent_assembly.py`; diff `create_deep_agent`'s stack order and `deepagents/profiles/` against the previous version.

## Open gaps

Ranked by failure prevented or money saved, over effort. Each goes through
`prioritize` into an issue before code; this list is struck through as they
land.

| # | Gap | Change | Effort |
|---|---|---|---|
| 1 | Insights' auto-added `general-purpose` sub-agent carries every tool, `ProposeChanges`, `RollbackChangeSet` and `RememberFact` included, with no retry or limits | supply a read-only one, as content does; generalise content's test into `test_agent_assembly.py` | S |
| 2 | SDK retries stack under `ReportedRetryMiddleware`, invisible to the UI and the quota cooldown | `max_retries=0` (Gemini: `retries=1`) and a timeout in `resolve_chat_model`; a test per provider | S |
| 3 | Deep-rung summarisation fires at ~850k on the current Claude models | trigger from `context_window_for(model)`; test across the catalogue | S–M |
| 4 | Fallback fires on auth, bad-request and overflow errors | classified fallback subclass | S |
| 5 | Sub-agents run without retry or limits; a sub-agent exception ends the parent turn | `subagent_middleware(limits)`; `ToolErrorMiddleware` in `session_middleware` | S–M |
| 6 | `deepagents` can append to Duct's system prompt per model | test the final prompt per model; render it in `make dump-prompts` | S |
| 7 | Tool definitions are unreviewed prompt | render tools in `make dump-prompts`; widen `prompts.yml` paths | S–M |
| 8 | Execution policy hardening: the auto-apply allowlist, agent-initiated rollback, a drift check on rollback | G1–G2 of the execution-approvals record | S |
| 9 | Execution policy hardening, part two | tracked with the maintainer, not here | M |
| 10 | ~~The memory digest says "present" for any open state, however old~~ | done 2026-09-28: `seen · Nd · verify`, re-read before asserting, refresh on re-remember | S |
| 11 | ~~No gate runs a harness change against real models~~ | done 2026-09-28: tier 0 offline, tier 1 in shadow (`agent-eval.yml`) | M |
| 12 | No dollar ceiling per run | a cost guard on `RunLimits` | M |

Runners-up: eval tier 2 (nightly, a weekly provider matrix, audit and content
cases); `cache_key` for content (audit got it 2026-09-27); tool spans at one
choke point; checkpoint deletion when a project is deleted; the LangChain stack
out of the grouped Dependabot PR.

## Sources

Primary: LangChain 1.x and `deepagents` docs and installed source; LangChain
"The Anatomy of an Agent Harness", "How Middleware Lets You Customize Your
Agent Harness", "Organizing Context in a Multi-Agent Harness", "Agent
Evaluation Readiness Checklist"; Anthropic "Building Effective Agents",
"Writing Effective Tools for Agents", "Effective Context Engineering",
"Harness Design for Long-Running Application Development", "An Update on
Recent Claude Code Quality Reports", "Demystifying Evals"; OpenAI "A Practical
Guide to Building Agents"; Böckeler, "Harness engineering"; Willison, "The
lethal trifecta"; OWASP Top 10 for Agentic Applications 2026. Full lists with
URLs are in the four records; the index is
[`agent-harness-references.md`](agent-harness-references.md).
