# Building and changing agents

**Author:** Shirish Kadam · **Updated:** 2026-10-26

Duct's agent rulebook on LangChain 1.x, LangGraph and `deepagents`: 34 rules,
each naming its primitive and its enforcing test, plus 12 ranked open gaps.
Read it before adding an agent or changing a prompt, tool, model default,
middleware or pin.

## At a glance

- **A rule is a test.** Each names its enforcer; the rest are gaps.
- **One assembly, two rungs.** Every session graph comes from one file, one
  middleware list.
- **Authority is code.** No agent can approve or apply; the irreversible waits
  for a click.
- **Context is engineered.** Stable blocks first, project text in the user
  turn, Duct's arithmetic, outside text as data.
- **Changes are judged.** k trials against a baseline before a prompt, model or
  harness change merges.

## Rules here are tests, because notes get skipped

A study of 481 public `CLAUDE.md` files found 4–16% of their prose security
rules backed by a real control (arXiv 2608.23550). So where a rule can be a
test, it is one, and the [Reference](#reference) names it under "Enforced by";
what cannot be tested yet is ranked under [Open gaps](#open-gaps).

The rules are Duct's reading of the harness-engineering literature, indexed in
[agent-harness-references.md](agent-harness-references.md); the records behind
them are under Sources.

## The harness is five files

| Term | Plain meaning |
|---|---|
| Rung | How much framework an agent uses, from one call up to `deepagents` |
| Runner | The one file that owns an agent: tools, prompts, limits, hooks |
| Binder | Wraps a Python function as a tool the model can call |
| Middleware | A guard around every model or tool call |
| Sub-agent | A child agent on a bounded side job; keeps the parent's context small |

| File, in `backend/agents/core/` | Owns |
|---|---|
| [`deep_session.py`](../../backend/agents/core/deep_session.py) | **Assembly** (`build_deep_session_agent`, `build_session_agent`, one `session_middleware` list) and **the loop** (`DeepSession`: turns, pauses, steers, compaction, failure posture) |
| [`lc.py`](../../backend/agents/core/lc.py) | LangChain adapter: `resolve_chat_model`, `stream_agent`, `interrupt_pause`, `prompt_caching_middleware`, and Duct's middleware (`ReportedRetryMiddleware`, `SteerMiddleware`, `SeenImagePruneMiddleware`) |
| [`turn.py`](../../backend/agents/core/turn.py) | How every user turn is built: `ContextSpec`, `BLOCK_ORDER` (stable first) |
| [`errors.py`](../../backend/agents/core/errors.py) | One classifier: a failure is a code before it is a message |
| `*_tools.py` | Binders: framework-free domain functions behind thin LangChain wrappers |

A runner (`agents/<type>/v1/runner.py`) owns tools, prompts, limits and hooks;
`tests/test_harness_boundaries.py` keeps frameworks out.

## Add an agent in nine steps

Each step ends with its Reference rule group.

1. **Run it through the prioritize skill.** Building is free; maintenance is
   forever.
2. **Pick the rung.** The runner docstring says which `deepagents` features it
   spends. Shape.
3. **Build it through the shared assembly**; anywhere else fails its test.
   Shape.
4. **Declare run limits and a context spec.** The loop; Context and caching.
5. **Name every sub-agent's tools**, the general-purpose one included,
   read-only. Shape.
6. **Wire `activity_hooks` and record the CONTEXT row** for session review
   (`tests/test_tool_activity.py`). Evals.
7. **Classify failures** through the one error classifier. Tools.
8. **Render and judge it.** `make dump-prompts`, a rubric in
   `backend/tests/eval/rubrics/`, a case in `backend/tests/eval/cases/`. Evals.
9. **Run `make check`.**

## Change one thing, then prove it

| You change | Rule groups, then the eval gate |
|---|---|
| A prompt | Context and caching; Evals |
| A tool | Tools |
| A model or tier default | Maintenance |
| Middleware | Shape; The loop |
| A dependency pin | Maintenance |

Exact names and two pricing gotchas: Reference, "Changing an agent, in full".

## Open gaps

Ranked by failure prevented or money saved, over effort. Each becomes an issue
(prioritize skill) before code, then is struck through here. Numbers are
stable: `models.py` cites gap 3.

| # | Gap | Change | Effort |
|---|---|---|---|
| 1 | ~~Insights' auto-added `general-purpose` sub-agent carries every tool, `ProposeChanges`, `RollbackChangeSet` and `RememberFact` included~~ | done 2026-10-25: `agents/insights/subagents/general_purpose.py` supplies a read-only one on the verifier's model; `test_agent_assembly.py` holds every deep runner's sub-agent lists writer-free. Retry and limits for sub-agents remain gap 5 | S |
| 2 | ~~SDK retries stack under `ReportedRetryMiddleware`, invisible to the UI and the quota cooldown~~ | done 2026-10-25: `max_retries=0` (Gemini `1`) in `resolve_chat_model`, a test per provider. A per-request timeout is still open: the SDK defaults are ten minutes and a thinking call can legitimately run long, so it needs a measurement first | S |
| 3 | ~~Deep-rung summarisation fires at ~850k on the current Claude models~~ | done 2026-10-25: `resolve_chat_model` writes `context_window_for(model)` into the model profile's `max_input_tokens`, so every fraction deepagents derives is a fraction of Duct's budget; `tests/test_summarisation_trigger.py` holds it across the catalogue. Still open: a 128k-window model's trigger (109k) sits under the insights prune trigger (120k), as it did before — pruning per window is its own change | S–M |
| 4 | ~~Fallback fires on auth, bad-request and overflow errors~~ | done 2026-10-25: `ClassifiedFallbackMiddleware` falls back only on a failure `is_retryable` classes as transient | S |
| 5 | ~~Sub-agents run without retry or limits; a sub-agent exception ends the parent turn~~ | done 2026-10-25: `subagent_middleware(limits)` on every spec of both runners (run limits, the reporting retry, the tool-error middleware), `ToolErrorMiddleware` in `session_middleware`; `test_agent_assembly.py` and `test_deep_session.py` hold both | S–M |
| 6 | `deepagents` can append to Duct's system prompt per model | half done 2026-10-25: `tests/test_system_prompt_ownership.py` fails a bump that suffixes a catalogue model unannounced (Haiku 4.5 is the one accepted suffix today). Still open: render the suffix in `make dump-prompts` | S |
| 7 | Tool definitions are unreviewed prompt | Render tools in `make dump-prompts`; widen `prompts.yml` paths | S–M |
| 8 | Execution policy hardening: auto-apply allowlist, agent-initiated rollback, drift check on rollback | G1 and G2 of the [execution approvals record](2026-09-27-execution-approval-ux-research.md) | S |
| 9 | Execution policy hardening, part two | Tracked with the maintainer, not here | M |
| 10 | ~~The memory digest says "present" for any open state, however old~~ | Done 2026-09-28: `seen · Nd · verify`, re-read before asserting, refresh on re-remember | S |
| 11 | ~~No gate runs a harness change against real models~~ | Done 2026-09-28: tier 0 offline, tier 1 in shadow (`agent-eval.yml`) | M |
| 12 | No dollar ceiling per run | A cost guard on `RunLimits` | M |

Runners-up:

- **Eval tier 2.** Nightly, a weekly provider matrix, audit and content cases.
- **A cache key for content.** Audit got one 2026-09-27.
- **Tool spans at one choke point.** Five binders span today.
- **Checkpoint deletion** when a project is deleted.
- **The LangChain stack** out of the grouped Dependabot PR.

> **Remember:** a rule with no test is a note. A gap closes with its test.

## Reference

The full rule tables, grouped as the harness-engineering list groups them.
"Primitive" is the LangChain, LangGraph or `deepagents` piece that implements
the rule. "Enforced by" is the test, check or review that holds it; test paths
are relative to `backend/`.

### Shape

| Rule | Primitive | Enforced by |
|---|---|---|
| Lowest rung that works: one structured call, then a fixed workflow, then `create_agent`, then `deepagents` only for what it adds (sub-agents, scratch filesystem, planning). Say in the runner docstring which of those the agent spends, and re-justify when one is switched off. | `init_chat_model`, `create_agent` (1.x, semver-stable), `create_deep_agent` (0.x, pinned exactly) | review; [`backend/AGENTS.md`](../../backend/AGENTS.md), "Pick the lowest rung that works" under "Agent ports" |
| **Build every session graph in one place.** The rung is chosen; the middleware is not. | `build_session_agent` / `build_deep_session_agent` | `tests/test_agent_assembly.py` (a graph built elsewhere fails) |
| A sub-agent exists to isolate context for a bounded side job. Name its tools; never let `deepagents` default them. The auto-added `general-purpose` sub-agent gets **every** parent tool unless one by that name is supplied. | `SubAgent` dicts with explicit `tools` | `test_agent_assembly.py::test_no_sub_agent_of_either_runner_carries_a_writer`; content: `test_sub_agents_never_get_the_writer_tools` |

### Tools

| Rule | Primitive | Enforced by |
|---|---|---|
| Few, workflow-level tools with meaningful ids. Insights reaches every connector entity through one `FetchData(entity_id)`, and every tool on a connected MCP server through `ListConnectedTools` / `CallConnectedTool`, never one definition per server tool. | `StructuredTool` + Pydantic `args_schema` | review; `tests/test_mcp_tools.py` (mounted only when a server is connected) |
| Bound every result, and never cut mid-structure: fold losslessly first. | `agents/core/compaction.py` (called by the insights data binder and the MCP binder); `FilesystemMiddleware` eviction on the deep rung | `tests/test_insights_data.py` (compaction keeps every number a brief could quote); `tests/test_mcp_tools.py` (an oversized result is capped at `MAX_RESULT_CHARS`) |
| An error is a result that says what to do next, with a code. Never `str(exc)` to a client. | `classify_error`; `ToolErrorMiddleware` with `tool_error_message` (a raise becomes an error result the model reads on) | `tests/test_agent_errors.py`; `test_deep_session.py` |
| Tool definitions are prompt: they head the cached prefix, so review them like prompt and keep their order deterministic. | none | gap 7 (`make dump-prompts` renders no tools yet) |
| Anything a tool returns from outside Duct (a search query, a page, an ad) is data, never instructions. Label it in the prompt. | none | each agent's system prompt (insights: `BOUNDARIES`) |
| Arithmetic over rows is Duct's, not the model's. A row report carries `totals`, `rates` (ratios of totals, or weighted means, never a mean of rates) and per-dimension `subtotals`, computed from the catalog's `agg`, `ratio` and `weight`, and says what they cover. | `agents/insights/totals.py`, called by `fetch_entity` | `tests/test_insights_totals.py`; `tests/test_insights_catalog_contract.py`; the eval gate's `must_quote` check |

### Context and caching

| Rule | Primitive | Enforced by |
|---|---|---|
| Per-user and per-project text goes in the USER turn, never the system prompt. Stable blocks first. | `ContextSpec`, `BLOCK_ORDER` | `tests/test_turn.py` |
| Every graph asks for caching. Anthropic caches only a request that says so; Gemini caches implicitly; OpenAI routes by `prompt_cache_key`. | `AnthropicPromptCachingMiddleware` (appended by `create_deep_agent`, by `build_session_agent`, and by `prompt_caching_middleware()` for a one-shot pass); `resolve_chat_model(cache_key=thread)` | `tests/test_agent_assembly.py`; cache share on `TOKEN_USAGE` |
| Duct owns the final system prompt byte for byte. `deepagents` harness profiles append text per model: 0.7.15 shipped coding-agent guidance ("Never speculate about code you have not opened…") for Haiku 4.5, Sonnet 4.6 and Opus 4.7, plus profiles for OpenAI Codex models; the 0.7.23 pin still does and adds an NVIDIA Nemotron profile. Packages can register more. | `register_harness_profile` | gap 6 |
| Prune before you summarise, and batch the pruning so each cache break buys something. | `ContextEditingMiddleware` + `ClearToolUsesEdit(clear_at_least=…)` | `RunLimits.__post_init__` (prune trigger below the summarisation floor); `tests/test_deep_session.py`; `tests/test_insights_middleware.py` |
| Set the summarisation trigger from `CONTEXT_WINDOW`, not the library's model profile (0.85 × the profile's `max_input_tokens` is ~850k on Opus 5.5 and Sonnet 5.5, where Duct budgets 200k). | `_within_ducts_window` in `resolve_chat_model` writes the budget into the profile deepagents reads | `tests/test_summarisation_trigger.py` |
| One emergency compaction and one retry on a real overflow; a second overflow is the ordinary failure. | `compact_thread` (`agents/core/lc.py`), called from `DeepSession` | `tests/test_insights_session.py` (compacted once and retried; a second overflow is the ordinary failure) |

### The loop

| Rule | Primitive | Enforced by |
|---|---|---|
| Every agent declares `RunLimits`: model and tool calls per run and per thread. Recursion is derived, never picked. | `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware` | `RunLimits.__post_init__`, `tests/test_deep_session.py` |
| Retry in exactly one layer, the one that reports each attempt and honours `Retry-After`. Provider SDKs retry underneath by default (Gemini up to 6 times), invisibly. | `ReportedRetryMiddleware`; SDK `max_retries=0` | gap 2 |
| Fall back only on transient failures. `ModelFallbackMiddleware` falls back on every exception, auth and overflow included. | `ClassifiedFallbackMiddleware` in `deep_session.py` | `tests/test_deep_session.py` (rejected key stays rejected; a 429 falls back) |
| Input typed mid-turn is steered or queued, never refused. | `SteerMiddleware` + the session's `steer_queue` | `tests/test_insights_session.py`; `tests/test_stream_translation.py` |
| A pause is a checkpointed `interrupt()` and survives a redeploy. Work before the interrupt is idempotent, because the node reruns on resume. | `langgraph.types.interrupt`, `Command(resume=…)` | `tests/test_deepagents_harness.py` |
| A thread is keyed on the conversation, never the session. | checkpointer `thread_id` | [`backend/AGENTS.md`](../../backend/AGENTS.md) |
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
| Nothing that moves money, goes live, or cannot be fully undone applies without a click on that set. | the auto-apply allowlist (`AUTO_APPLY_ALLOWLIST`) | `tests/test_execution_policy.py`; the allowlist is under review (gap 8) |
| The agent acts with the user's delegated credentials, scoped to the project at build time. Non-members get 404. | binders take a membership-checked `project_id` | `tests/test_route_auth_boundaries.py` |
| Only an explicit Stop cancels a run. A page that leaves mid-turn detaches: the run finishes and is written down, the grace close and the pruner wait for the turn, and a returning tab reattaches from the segment after the rows it hydrated. | `_close_after_grace`, `_stale_session_ids`, `after_segment` on the stream (`routes/agents.py`); the recorder's segment stamp; `hooks/useAgentSession.js` | `tests/test_runs_survive_navigation.py`; `lib/__tests__/liveRuns.test.js`, `agentHistory.test.js` |

### Evals and observability

| Rule | Primitive | Enforced by |
|---|---|---|
| Offline tests drive the real harness with a canned model and assert events, tool names and payloads, never prompt prose. | `ToolCallingFake`, `emitted` | `make test` |
| What is *sent* to the model is tested too: byte-stable prefix across calls, history and reasoning kept, effort passed. The Claude Code regressions of April 2026 were exactly these. | `RecordingFake` (`tests/fakes.py`); the "Model defaults" section of [`make dump-prompts`](agent-prompts.md) | `tests/test_request_invariants.py` (both rungs and the insights runner); `prompts.yml` fails a default changed without the dump |
| A prompt, model default, effort or harness change is judged k times against a baseline, on synthetic accounts, before it merges. Binary markers gate; 1–5 scores are logged. | `tests/eval/gate.py`, `tests/eval/cases/`, `make agent-eval` (DeepSeek V4 Flash on OpenRouter, GLM 5.3 Flash judging) | `agent-eval.yml` on harness PRs, in shadow until an A/A window; `tests/test_eval_gate.py` holds the gate's own logic. One provider today; the per-provider matrix is tier 2 |
| One span per model call and one per tool call, at one choke point. | `ReportedRetryMiddleware` (model); `awrap_tool_call` middleware (tool) | five binders span their own tools today (gap, runner-up) |

### Maintenance

| Rule | Enforced by |
|---|---|
| Bump the LangChain stack alone, never inside a grouped Dependabot PR; `poetry install --with dev` locally the same day, or local tests run other versions than CI. | `tests/test_deepagents_harness.py`, `tests/test_agent_assembly.py` |
| A new model is a table migration: `PRICING`, `CONTEXT_WINDOW`, `MODEL_FALLBACK`, tiers, thinking, and a check of the LangChain profile and `deepagents` harness profiles for that id. | `tests/test_stream_translation.py` (`PRICING` and `CONTEXT_WINDOW` cover the same ids) |
| Every harness component names the failure it compensates for, and is re-measured when the model changes. `planning=False` on insights is the worked example: two of five turns were checklist rewrites. | [`STYLE.md`](../../STYLE.md) (comments carry reasoning) |

### Middleware: what we mount and why

| Middleware | Mounted | Verdict |
|---|---|---|
| `ContextEditingMiddleware` + `ClearToolUsesEdit` | `session_middleware` | keep; `clear_at_least` is `RunLimits.tool_results_clear_at_least`, a quarter of the trigger, since 2026-10-25 — without it every call past the trigger cleared one more result and broke the cached prefix there |
| `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware` | `session_middleware` | keep; per-tool caps are `RunLimits.per_tool_run_limits` (content caps `generate_video` at 3 a turn), still to add for `ProposeChanges` and `task` |
| `ModelFallbackMiddleware` | `session_middleware`, as `ClassifiedFallbackMiddleware` | keep; classified since 2026-10-25 |
| `ReportedRetryMiddleware` (ours) | `session_middleware` | keep: `ModelRetryMiddleware` has no per-attempt hook and ignores `Retry-After` |
| `SteerMiddleware`, `SeenImagePruneMiddleware` (ours) | `session_middleware` | keep; no prebuilt equivalent |
| `AnthropicPromptCachingMiddleware` | every graph | keep; measure a 1h TTL for idle chats |
| `TodoListMiddleware` | content only | keep as measured |
| `FilesystemMiddleware` | deep rung, no `execute` | keep; never the shell |
| `SubAgentMiddleware` | deep rung | keep; always supply `general-purpose` yourself |
| `SummarizationMiddleware` (deepagents) | deep rung | keep; its trigger comes from `CONTEXT_WINDOW` since 2026-10-25 (gap 3) |
| `PatchToolCallsMiddleware` | deep rung | keep |
| `ToolErrorMiddleware` | `session_middleware` and every sub-agent | keep; mounted 2026-10-25 |
| `HumanInTheLoopMiddleware` | not mounted | skip: change-set cards and `policy.py` do this |
| `PIIMiddleware` | not mounted | skip; `remember()` redacts. Revisit for traces |
| `LLMToolSelectorMiddleware`, `ProviderToolSearchMiddleware` | not mounted | skip: changing tools per call breaks the cache; tool tokens are small |
| `ModelRetryMiddleware`, `ToolRetryMiddleware`, `LLMToolEmulator` | not mounted | skip: ours reports; `service/rest.py` retries; fakes exist |
| `ShellToolMiddleware`, `FilesystemFileSearchMiddleware`, Claude-native tool middleware | never | never on a server; a capability the model may lack is a Duct tool |

### Changing an agent, in full

| Change | Do |
|---|---|
| Prompt | `make dump-prompts` and read the diff as prose (`prompts.yml`). Nothing volatile above the stable blocks. Replay the bundles that motivated it (`make session-replay`) on two providers, and run `make agent-eval` (`agent-eval.yml` runs it on the PR): FAIL does not merge; INCONCLUSIVE needs a line in the PR saying why it is acceptable |
| Tool | Bound its output; errors carry a code and a next step; decide its activity card; keep writers off every sub-agent list; batch tool changes, since each one invalidates the cache |
| Model or tier default | Update `PRICING`, `CONTEXT_WINDOW`, `MODEL_FALLBACK` and the tier map together, and add a `RETIRED_MODELS` row for any id the new one replaces. Classify it in `CLAUDE_BOUND_THINKING` and `takes_temperature`. Check the LangChain profile exists for that id, not just its window (langchain-anthropic 1.7.4 had none for `claude-sonnet-5-5`, which meant `max_tokens=4096` with thinking inside it), and any `deepagents` harness profile. Run the live web-search matrix. For an OpenRouter slug, price it at the model vendor's own endpoint (`/api/v1/models/<slug>/endpoints`), not the one price `/api/v1/models` shows, and read the vendor's changelog: a slug pins a build the vendor may already have retired |
| Middleware | Change `session_middleware`, nowhere else. Re-measure `SUPERSTEPS_PER_MODEL_CALL` (`tests/test_deep_session.py`). Comment the failure it prevents |
| Dependency bump | Alone; `poetry install --with dev`; `tests/test_deepagents_harness.py` and `tests/test_agent_assembly.py`; diff `create_deep_agent`'s stack order and `deepagents/profiles/` against the previous version |

### Sources

- **LangChain source.** The 1.x and `deepagents` docs and the installed packages.
- **LangChain posts.** "The Anatomy of an Agent Harness", "How Middleware Lets You Customize Your Agent Harness", "Organizing Context in a Multi-Agent Harness", "Agent Evaluation Readiness Checklist".
- **Anthropic.** "Building Effective Agents", "Writing Effective Tools for Agents", "Effective Context Engineering", "Harness Design for Long-Running Application Development", "An Update on Recent Claude Code Quality Reports", "Demystifying Evals".
- **Others.** OpenAI "A Practical Guide to Building Agents"; Böckeler, "Harness engineering"; Willison, "The lethal trifecta"; OWASP Top 10 for Agentic Applications 2026.
- **Duct's own records, 2026-09-27.** [Eval gating](2026-09-27-agent-eval-gating-design.md), [insights code execution](2026-09-27-insights-code-execution-design.md), [execution approvals](2026-09-27-execution-approval-ux-research.md) and [memory freshness](2026-09-27-memory-freshness-design.md) hold the research behind the larger rules, with full source lists and URLs.

The index of everything read is
[agent-harness-references.md](agent-harness-references.md).
