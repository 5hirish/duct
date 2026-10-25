# Agent ports and the event contract

**Author:** Shirish Kadam, Claude · **Updated:** 2026-10-26

**Status:** implemented. Source of truth is the code: [`ports/__init__.py`](../../backend/agents/core/ports/__init__.py) declares the ports; [`events.py`](../../backend/agents/core/events.py) holds the vocabulary and the AG-UI map.

Duct rents an agent framework and does not marry one. This page explains the six seams that keep that true and publishes the event contract the app reads. For anyone adding a runner, changing an event or swapping frameworks.

## At a glance

- **Six ports, one framework behind them.** Tools, events, pauses, artifacts, session state and model transport.
- **The durable assets never see a framework.** Prompts, tools, schemas and the artifact contract are plain Python.
- **Events are mapped to AG-UI, failures travel as a code.** The wire names are the app's contract; exception text never reaches a browser.
- **One test holds the line.** A framework import outside the adapters, or an event with no AG-UI meaning, fails the build.

## A framework touches Duct through six ports

Inside a port the framework is as framework-shaped as it likes; what crosses it has Duct's shape and follows a multi-vendor standard.

| Port | What crosses it | Today |
|---|---|---|
| **Tools** | A plain function plus its description | A thin binder per framework |
| **Events out** | Duct's event vocabulary, via an emitter | The LangChain stream translator |
| **Human in the loop** | Pause, ask, return the answer | An in-process future (audit); a checkpointed interrupt (insights, content) |
| **Artifacts** | A streaming tag, a parser, a persister | Framework-neutral by construction |
| **Session and state** | A live registry; the conversation id as the thread | A LangGraph checkpointer (Postgres, SQLite, memory) |
| **Model transport** | Provider, model and engine registries | Five native packages; one compatible shape for gateways |

## A port is earned on the second implementation

> **Rule:** write the adapter on the second implementation, not the first. One implementation is a guess; two are a fact.

The pause port is the example. For a year the only way to park a run was an in-process future that dies with its worker. When insights moved onto LangGraph's interrupt, the protocol was declared from two real implementations, and the tools stopped knowing which one they held.

The checkpointed one survives a redeploy and re-shows the waiting question on resume. Every port now has one adapter; two frameworks have already left through these seams.

## Why a seam, not a framework

Agent frameworks are the fastest-churning, least-differentiated layer. The deep-agent library Duct rents is 0.x with no stability policy, so it is pinned exactly and gated by a test.

There is deliberately no shared "harness interface". Frameworks differ in capability, not only in API shape: take the intersection and you lose sub-agents, a filesystem, skills and compaction; take the union and you are writing a framework.

So the question is how small a surface the framework touches. LangChain is layered: the lower the rung, the firmer the promise.

| Rung | Runs |
|---|---|
| Long-term support (1.x) | Audit |
| Deep-agent library (0.x, pinned) | Insights, content |

Abandon the top rung tomorrow and one file breaks, the shared session loop; the fallback is one rung down, not a rewrite.

## Events are mapped to AG-UI, never renamed

Duct's event names predate AG-UI and mostly agree. Renaming them would break every consumer to buy nothing, so a table maps each event to its AG-UI meaning; domain events no protocol covers map to `Custom`.

That table is the whole adapter: an AG-UI endpoint is a short translation over it, and the boundary test fails when an event is missing.

## Failures travel as a code, never an exception

A failed step or run carries a code, a retryable flag and a one-sentence error. One classifier assigns the code from the exception's class and status, looking through wrappers, and decides retries: a rate limit backs off, a rejected key fails at once.

The app maps the code to copy and an action; the recorder writes run status and error on the conversation, so a thread list badges "Needs you" or "Failed" before anyone opens it.

> **Why:** the raw message has carried request ids, and once a URL with a key in it. It goes to the log, never the browser.

## Mid-turn messages are steered or queued, never refused

A session that can steer hands the message to the model at its next call, checkpointed with the thread; one that cannot holds it for the next turn. The app marks the row "queued" until an event names it consumed.

## Artifacts, not reports

The streaming tag is named for artifacts, not reports: content streams plans and post drafts through the same tag, and the store versions them all alike.

The mechanism (tag, events, parser, persister) says artifact; the value layer (the `kind` column, the audit schema) says report, because that artifact really is one. Renaming `kind` would carry no information and cost a data migration.

## Any OpenAI-compatible gateway is a config entry

OpenRouter now runs on its own first-party package, for routing preferences and a reasoning parameter the bare shape cannot carry. The compatible shape is still the port: any other gateway is served as chat completions at its base URL, a config value.

A self-hosted gateway replaces OpenRouter's interface and key management, not its commercial aggregation. One key reaches dozens of providers; a gateway reaches accounts you already hold. They are complements on one code path.

## Observability is Duct's job

LangChain's tracing goes to its own vendor, so Duct emits the OpenTelemetry GenAI spans itself: one per model call, one per tool call, at the choke point all binders share. The attribute names are a pinned copy of an experimental convention; a test keeps the copy honest.

> **Remember:** the framework is a tenant. Six ports and one test keep it one.

## Reference

Tables only; the linked code is the source of truth.

### Ports in code

| Port | Contract | Adapters |
|---|---|---|
| Tools | A plain callable plus its description; `ToolBinder` in [`ports/__init__.py`](../../backend/agents/core/ports/__init__.py) | `build_memory_tools_lc`, `build_artifact_tools_lc`, `build_execution_tools_lc`, `build_mcp_tools_lc`, and the connector, web, audit, content and insights binders listed in [`test_harness_boundaries.py`](../../backend/tests/test_harness_boundaries.py) |
| Events out | `AgentEvent` / `EventKind` plus `Emitter` | `stream_agent` in [`lc.py`](../../backend/agents/core/lc.py) |
| Human in the loop | `PauseFn`: `await pause(event, payload)` returns the answer ([`session.py`](../../backend/agents/core/session.py)) | `make_future_pause`: in-process future, 120 s timeout (audit v1; the slide-render bridge uses its own future). `interrupt_pause`: LangGraph `interrupt()`, no timeout (insights v1, content v1) |
| Artifacts | `<duct_artifact>` tag, `DuctArtifactStreamParser`, `ArtifactPersister` | [`stream.py`](../../backend/agents/core/stream.py), [`artifact_store.py`](../../backend/service/artifact_store.py) |
| Session and state | `BaseAgentSession` registry (in-process); conversation id as the thread | [`checkpoint.py`](../../backend/agents/core/checkpoint.py): Postgres, SQLite or in-memory, chosen from `DATABASE_URL`, degrading to in-memory. `DeepSession` loop in [`deep_session.py`](../../backend/agents/core/deep_session.py) |
| Model transport | `Provider` / `ModelName` / `Engine` plus `get_api_key_kwargs` | [`models.py`](../../backend/agents/models.py), [`engines.py`](../../backend/agents/engines.py); `resolve_chat_model` in `lc.py` |

### LangChain rungs

| Rung | Stability | Used for |
|---|---|---|
| `init_chat_model` plus `with_structured_output` | 1.x, long-term support under semver | Compaction summaries (`compact_thread`), memory consolidation, typed one-shot answers (enrichment research, audit draft inference, content reference diagnosis) |
| `create_agent` | 1.x, long-term support | The audit runner (`build_session_agent`), the enrichment research loop (`research.py`) |
| `deepagents` | 0.x, no stability policy; pinned exactly in `pyproject.toml`, gated by `test_deepagents_harness.py` | The insights and content sessions (`build_deep_session_agent`): planning, sub-agents, scratch space |
| First-party surface in use | All on the 1.x tier | `create_agent`, `init_chat_model`, `StructuredTool`, the middleware classes, the message classes |

### Standard behind each port

| Port | Standard | Maturity |
|---|---|---|
| Tools | MCP, under the Linux Foundation's Agentic AI Foundation since Dec 2025 (OpenAI, Anthropic, Google, Microsoft, AWS, Block) | The most durable of the four |
| Model transport | OpenAI-compatible chat completions | De facto universal |
| Events out | AG-UI | Credible, younger, single-vendor origin |
| Observability | OpenTelemetry GenAI semantic conventions | `gen_ai.client` settled, `gen_ai.agent` experimental |

### Live SSE events (`AgentEvent` to AG-UI)

| Duct event | AG-UI | Meaning and payload |
|---|---|---|
| `pipeline_started` | `RunStarted` | A run began |
| `pipeline_finished` | `RunFinished` | A run completed |
| `pipeline_failed` | `RunError` | A run failed: `code`, `retryable`, `error` |
| `step_started` | `StepStarted` | A workflow stage began (`step_id`, `status`) |
| `step_finished` | `StepFinished` | A workflow stage completed |
| `step_failed` | `StepFinished` | AG-UI has no StepFailed; failure rides in `status` (`error`). Carries `code`, `retryable`, `error` |
| `agent_message_chunk` | `TextMessageContent` | Prose token |
| `agent_message` | `TextMessageChunk` | A complete message |
| `message_stop` | `TextMessageEnd` | Turn boundary |
| `thinking_chunk` | `ReasoningMessageContent` | Extended-thinking delta |
| `synthesis_chunk` | `TextMessageContent` | Insights synthesis stream (legacy alias on audit) |
| `todo_update` | `ActivitySnapshot` | The full todo list; a snapshot, never a delta |
| `questions_required` | `Custom` | Pause: the agent needs an answer. `interrupt_id` on a checkpointed run; `replay: true` when re-emitted on resume |
| `connection_required` | `Custom` | Pause: a connector the project lacks. `connector_id`, `label`, `auth_kind`, `authorize_path`, `reason` |
| `account_selection_required` | `Custom` | Pause: which account, property or site. `connector_id`, `label`, `candidates` |
| `tool_approval_required` | `Custom` | Pause: a connected MCP tool its server does not mark read-only. Server, tool, reason, argument preview |
| `slide_render_requested` | `Custom` | The agent asks the browser to rasterize a slide |
| `artifact_chunk` | `Custom` | Token inside `<duct_artifact>` |
| `artifact_version` | `Custom` | New version of the primary artifact: full payload, `version_id`, label |
| `artifact_updated` | `Custom` | Compact artifact card for the transcript; no payload |
| `project_draft` | `Custom` | Onboarding: fields learned about the site, each with provenance |
| `plan_generated` | `Custom` | Content: a plan |
| `post_draft_updated` | `Custom` | Content: a post draft |
| `execution_proposed` | `Custom` | Staged-execution change set; upsert by `change_set_id` |
| `tool_activity` | `Custom` | One allowlisted tool call, emitted as `running` then `success` or `error`; upsert by `activity_id`. Fields `title`, `subtitle`, `source`, `meta`; never the output ([`activity.py`](../../backend/agents/core/activity.py)) |
| `memory_written` | `Custom` | Entries this turn stored, with undo |
| `memory_recalled` | `Custom` | Entry ids this turn was primed with |
| `model_retrying` | `Custom` | Status, not failure; the next token clears it. `attempt`, `max_attempts`, `code`, `retry_in` (seconds; a duration the client anchors to its own clock) |
| `token_usage` | `Custom` | One model call's bill: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `context_window`, `model`, `scope`, `cost_usd`. Scope is `thread`, `subagent` or `compaction`; all three are billed, only `thread` drives the gauge. Cost comes from `PRICING`; `null` for an unpriced model, never a guess |
| `context_compacting`, `context_compacted` | `Custom` | The session is summarising old history, then did. The summariser's tokens never reach the transcript. Also emitted around the one emergency compaction: a request the provider rejects as too long is summarised once and retried from its checkpoint; a second rejection is the ordinary `context_window` failure |
| `user_input_consumed` | `Custom` | A message sent mid-turn reached the model; carries its `client_message_id` |

### Pause answers

One answer endpoint for every pause. `interrupt_id` is passed back on a checkpointed run; omitted, the only pending pause is assumed. An empty answer always means "carry on without it".

| Event | Answer |
|---|---|
| `questions_required` | Answers keyed by question |
| `connection_required` | `{"skipped": true}` to decline; anything else after the sign-in, and the server re-reads the connector rather than trusting the answer |
| `account_selection_required` | `{"account_id": ...}`; empty is a skip |
| `tool_approval_required` | `{"approved": true}`; anything else is a skip |

### Failure code

| Field | Value |
|---|---|
| `code` | `ErrorCode` in [`errors.py`](../../backend/agents/core/errors.py): `rate_limited`, `overloaded`, `upstream_error`, `timeout`, `network` (retryable); `auth`, `permission`, `context_window`, `bad_request`, `model_not_found`, `connector_expired`, `connector_forbidden`, `reference_unavailable`, `cancelled`, `unknown` |
| `retryable` | Whether the same request may succeed if sent again shortly |
| `error` | One code-specific sentence; never the exception text |
| Classifier | `classify_error`, also the retry decision in `ReportedRetryMiddleware` ([`lc.py`](../../backend/agents/core/lc.py)) |
| App side | `errorAction` in [`agentSession.js`](../../app/src/lib/agentSession.js); codes mirrored in [`agentEvents.js`](../../app/src/lib/agentEvents.js) |

### Run status (`RunStatus` on `agent_conversations`)

Written only by `ConversationRecorder` ([`persistence.py`](../../backend/agents/content/persistence.py)), derived from the stream; `run_error` carries `{code, retryable, error}`. Both ride on the conversation list and the state route.

| Value | Meaning |
|---|---|
| `idle` | Waiting for the user's next message |
| `running` | A turn is in flight |
| `paused` | Parked on a question, a connect offer or an account pick |
| `failed` | The last turn ended in a failure (see `run_error`) |
| `cancelled` | The session closed while a turn was running |

### Persisted conversation kinds (`EventKind` to AG-UI)

| Kind | AG-UI | Note |
|---|---|---|
| `user`, `assistant` | `MessagesSnapshot` | |
| `thinking` | `ReasoningMessageContent` | |
| `tool_use` | `ToolCallStart` | Name plus full input |
| `tool_result` | `ToolCallResult` | Paired by `tool_use_id`; output plus `is_error` |
| `question`, `answer` | `Custom` | |
| `failure` | `RunError` | `{code, retryable, error}` where a turn or run died; `code: cancelled` for a stop |
| `context` | `Custom` | What the model was given: composed turn, blocks, model, system-prompt fingerprint |
| `compacted` | `Custom` | The thread was summarised in place: `{summary}` |
| `memory_recalled`, `memory_written` | `Custom` | What memory gave the run and what the run gave memory |

### Mid-turn input

| Harness can steer | Delivery | Where |
|---|---|---|
| Yes (`steer_queue` set) | `SteerMiddleware`, a `before_model` hook, so the message is checkpointed with the thread | [`lc.py`](../../backend/agents/core/lc.py) |
| No | `chat_queue`; waits for the next turn | [`session.py`](../../backend/agents/core/session.py) |
| Steer after the last model call | Becomes the next turn (`_leftover_steers`) | [`deep_session.py`](../../backend/agents/core/deep_session.py) |

### Artifact vocabulary by layer

| Layer | Word | Why |
|---|---|---|
| Mechanism: tag, events, parser, persister | artifact | Shared by every agent; `test_no_live_event_uses_report_vocabulary` pins it |
| Value: `artifacts.kind`, the `AuditReport` schema | report | This artifact really is a report |

### Renamed wire values

| Was | Is | Migration |
|---|---|---|
| `<duct_report>` | `<duct_artifact>` | The parser accepts both tags |
| `report_chunk` | `artifact_chunk` | The app accepts both strings (`LEGACY_*` in `agentEvents.js`); the backend emits only the new ones, so deploy the app first, then the backend. Python aliases are gone |
| `report_updated` | `artifact_version` | As above |
| `artifacts.kind` | unchanged: `report`, `document`, `ticket`, `image` | [`models/artifact.py`](../../backend/models/artifact.py) |

### Model transport

| Provider | Package | Note |
|---|---|---|
| `openai` | langchain-openai | |
| `google_genai` | langchain-google-genai | |
| `anthropic` | langchain-anthropic | |
| `openrouter` | langchain-openrouter | Native gateway: routing preferences, unified reasoning parameter. Base URL overridable via `openrouter_base_url`. A `vendor/slug` not in the curated list passes through verbatim; a bare name resolves by prefix |
| `xai` | langchain-xai | First-party vendor, not a gateway |
| Any other gateway | OpenAI chat-completions shape at its own base URL | `GATEWAY_BASE_URL` and `NATIVE_GATEWAY_PROVIDERS` in `models.py`; what Ollama, vLLM or LiteLLM would get |

### Self-hosted gateways on the same code path

| Gateway | Licence | Runtime | Note |
|---|---|---|---|
| LiteLLM | MIT | Python | 100+ providers, virtual keys, spend control; the default choice |
| Bifrost | Open source | Go | About 11 µs routing overhead at 5k requests/s; LiteLLM's Python path climbs sharply past about 500 |
| Portkey Gateway | MIT | Node | Adds guardrails and observability |
| LLM Gateway | AGPLv3 | Docker | Closest to OpenRouter's whole platform (dashboard, caching, analytics); check the licence before embedding |
| Envoy AI Gateway | Open source | Kubernetes | For a cluster that already runs Envoy |
| Ollama, vLLM, llama.cpp | Open source | Local | Model servers, not gateways; same compatible path |

### Enforcement

| Test | Fails when |
|---|---|
| [`test_harness_boundaries.py`](../../backend/tests/test_harness_boundaries.py) | A framework import appears outside `ADAPTERS`; an `ADAPTERS` entry no longer imports one; a `FRAMEWORK_FREE` module (events, prompts, schemas, registries, the three runners) imports one; an event is missing from the AG-UI maps; an app event mirror names an unknown event, or marks a live one `LEGACY_`; a live event uses report vocabulary |
| Boundary debt, named in that allowlist | `routes/chat.py` and `service/memory_consolidation.py` import LangChain from the wrong layer |
| [`test_deepagents_harness.py`](../../backend/tests/test_deepagents_harness.py) | The `deepagents` pin changes what `interrupt()` raised inside a tool does |
| [`test_telemetry.py`](../../backend/tests/test_telemetry.py) | The pinned GenAI attribute names drift from the installed package |

### Telemetry

| Item | Where |
|---|---|
| `model_span`, `tool_span` | [`telemetry.py`](../../backend/agents/core/telemetry.py); attribute names pinned to `SEMCONV_VERSION`, not imported from the package's private module |
| Exporter | `OTEL_EXPORTER_OTLP_ENDPOINT`; unset means tracing off |
| Dependency | `opentelemetry-api` declared directly, no longer transitive; import guarded, degrades to a no-op |
