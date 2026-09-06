# Agent ports and the event contract

**Status:** implemented · Source of truth is the code, not this page —
[`backend/agents/core/ports/__init__.py`](../../backend/agents/core/ports/__init__.py)
declares the ports and
[`backend/agents/core/events.py`](../../backend/agents/core/events.py) holds the
event vocabulary and the AG-UI map.

Duct rents an agent harness; it does not marry one. This document explains the
seam that makes that true, and publishes the event contract that crosses it.

---

## 1. Why a seam and not a framework

Agent harnesses are the fastest-churning, least-differentiated layer in this
stack. At the time of writing: `deepagents` is 0.7.x on a weekly cadence,
`claude-agent-sdk` is 0.2.x, `google-adk` ships roughly bi-weekly and its 2.x
line already forced one breaking migration on us. Meanwhile `langchain` 1.x is
an LTS release under semver, with no breaking changes promised until 2.0.

The durable assets are elsewhere: prompts, tools, schemas, goals, scoring, the
artifact contract. Those are framework-neutral and survive any harness swap. So
the useful question is not "which SDK is best" but **"how small is the surface
through which an SDK touches us, and which SDK keeps that surface smallest?"**

### The anti-pattern we deliberately avoid

There is no `AgentHarness` interface in this codebase, and there should never
be one. Harnesses differ in *capability*, not just API shape:

- Take the **intersection** and you lose subagents, filesystem, skills, HITL
  granularity and compaction — the entire reason to rent a harness.
- Take the **union** and you are writing a framework, plus adapters for it,
  which is strictly worse than the three-engine problem this replaced.

So the harness stays harness-shaped *inside a runner*, and only its boundary is
standardized. The evidence that this works is already in the repo: the
LangChain audit runner is 376 lines against the Claude SDK runner's 1,175, not
because LangChain is terser but because the boundaries were already in place
and only the middle had to be rewritten.

### Pick the lowest rung that works

LangChain 1.x is layered, and the layers carry different stability guarantees.
That makes "how much framework do I adopt" a risk decision, not just a
convenience one:

| Rung | Stability | Duct agent |
|---|---|---|
| `init_chat_model` + `.with_structured_output()` | 1.x LTS, semver | conversation compaction, artifact digests |
| `create_agent` | 1.x LTS, semver | audit v1, content's enrichment pass |
| `deepagents` | 0.x, no policy, weekly | insights session, content session (planning, sub-agents, scratch space) |

The first-party LangChain surface is still small — `create_agent`,
`init_chat_model`, `StructuredTool`, the middleware classes and the message
classes, all on the LTS tier. `deepagents` is now load-bearing for the two
session agents, which is why it is pinned exactly and gated by
`tests/test_deepagents_harness.py`.

The test that matters: *if `deepagents` were abandoned tomorrow, what breaks?*
The two session runners' middle — assembly and the stream loop. Their tools,
prompts, schemas and events are framework-free and the boundary test keeps
them so, so the fallback is a rung down onto `create_agent`, not a rewrite.
That asymmetry is the case for this design.

---

## 2. The ports

| Port | Contract | Adapters |
|---|---|---|
| **Tools** | plain domain callable + a description single-sourced beside it | `build_memory_tools_lc`, `build_artifact_tools_lc`, `build_execution_tools_lc` — each had an SDK twin, retired with v3 |
| **Events out** | `AgentEvent` / `EventKind` + an `Emitter` | v1 LangChain stream; the SDK's `pump_stream_event` was the second, until v3 went |
| **Human-in-the-loop** | `PauseFn` — `await pause(event, payload)` returns the user's answer | `make_future_pause` (in-process Future; audit v1, the slide-render bridge), `interrupt_pause` (LangGraph `interrupt()`; insights v1, content v1) |
| **Artifacts** | `<duct_artifact>` + `DuctArtifactStreamParser` + `ArtifactPersister` | harness-neutral by construction |
| **Session / state** | `BaseAgentSession` registry for the live process; the conversation id as the durable thread | in-process registry; LangGraph checkpointer keyed on the conversation, driven by the shared `DeepSession` loop (`agents/core/deep_session.py`; insights v1, content v1) |
| **Model transport** | `Provider` / `ModelName` / `Engine` registries | OpenAI-compatible, native Anthropic, native Gemini |

**The rule for adding one: write the adapter on the second implementation, not
the first.** A port with one implementation is a guess; with two it is a fact.
The pause port is the worked example. `bridge_user_input` was the only way a
run could park until the insights runner moved its pauses onto LangGraph's
`interrupt()`; the `PauseFn` protocol was declared at that point, from two
real implementations, and the tool bodies (`agents/core/connector_tools.py`)
stopped knowing which one they had been handed.

What the checkpointed implementation buys, and the in-process one cannot: a
pause lives in the thread's checkpoint, so it survives a redeploy, has no
timeout, and a session opened later on the same conversation is shown the
question it is still waiting on (`GET …/conversations/{id}/state`, and the
`replay` flag on the re-emitted event). The frontend contract is unchanged —
the same three events, one answer endpoint, plus an `interrupt_id` the client
passes back so two pauses raised in one turn are resolved separately.

### The external standard behind each port

Ports point at contracts with multi-vendor backing, not at Duct inventions:

| Port | Standard | Maturity |
|---|---|---|
| Tools | **MCP** — under the Linux Foundation's Agentic AI Foundation since Dec 2025 (OpenAI, Anthropic, Google, Microsoft, AWS, Block) | the most durable of the four |
| Model transport | **OpenAI-compatible chat completions** | de facto universal |
| Events out | **AG-UI** | credible, younger, single-vendor origin |
| Observability | **OpenTelemetry GenAI semantic conventions** | `gen_ai.client` settled, `gen_ai.agent` still experimental |

The protocols are outliving the SDKs, which is the reason to express contracts
in their terms even when we do not take the dependency.

### Enforcement

[`backend/tests/test_harness_boundaries.py`](../../backend/tests/test_harness_boundaries.py)
fails if a framework import appears outside the declared adapter allowlist, if
an allowlist entry goes stale, if a domain module grows a framework import, or
if an event is missing from the AG-UI map. That is what makes "modular" a
property of the codebase rather than an intention in a document.

The allowlist also records three files as **boundary debt** — `routes/chat.py`,
`service/artifact_store.py` and `service/memory_consolidation.py` import a
harness from the wrong layer. They are named rather than silently blessed.

---

## 3. The event contract

Duct's SSE vocabulary predates AG-UI and largely agrees with it —
`step_started` / `step_finished` are already name-for-name identical.

**We map rather than rename**, deliberately. Renaming `agent_message_chunk` to
`text_message_content` would break every consumer to buy nothing; the wire
value is an internal contract, and what has to be portable is the *meaning*.
And roughly half of these are domain events that no protocol will ever cover —
AG-UI's answer for those is `Custom`, so "aligning" them would flatten real
meaning into a generic envelope. Contorting domain events to fit a standard is
the same mistake as contorting them to fit an SDK.

The map below is the entire AG-UI adapter. A future AG-UI endpoint is a ~30-line
translation over it, not a refactor.

### Live SSE events

| Duct event | AG-UI | Meaning |
|---|---|---|
| `pipeline_started` | `RunStarted` | a run began |
| `pipeline_finished` | `RunFinished` | a run completed |
| `pipeline_failed` | `RunError` | a run failed |
| `step_started` | `StepStarted` | a workflow stage began |
| `step_finished` | `StepFinished` | a workflow stage completed |
| `step_failed` | `StepFinished` | AG-UI has no StepFailed; failure rides in `status` |
| `agent_message_chunk` | `TextMessageContent` | prose token |
| `agent_message` | `TextMessageChunk` | a complete message |
| `message_stop` | `TextMessageEnd` | turn boundary |
| `thinking_chunk` | `ReasoningMessageContent` | extended-thinking delta |
| `synthesis_chunk` | `TextMessageContent` | insights synthesis stream (legacy on audit) |
| `todo_update` | `ActivitySnapshot` | full todo list; snapshot, never a delta |
| `questions_required` | `Custom` | HITL — the agent needs an answer to continue; carries `interrupt_id` on a checkpointed run, `replay: true` when re-emitted on resume |
| `connection_required` | `Custom` | HITL — a connector the project lacks; answer `{connected}` or `{skipped}` |
| `account_selection_required` | `Custom` | HITL — which account/property/site; answer `{account_id, account_name}` |
| `slide_render_requested` | `Custom` | agent asks the browser to rasterize a slide |
| `artifact_chunk` | `Custom` | token inside `<duct_artifact>` |
| `artifact_version` | `Custom` | new **version** of the primary artifact, full payload |
| `artifact_updated` | `Custom` | compact artifact **card** for the transcript |
| `plan_generated` | `Custom` | content: a plan |
| `post_draft_updated` | `Custom` | content: a post draft |
| `execution_proposed` | `Custom` | staged-execution change set; upsert by `change_set_id` |
| `memory_written` | `Custom` | entries this turn stored, with undo |
| `memory_recalled` | `Custom` | entry ids this turn was primed with |
| `model_retrying` | `Custom` | a model call failed and is being retried: `attempt`, `max_attempts`, `code`, `retry_in` (seconds until the next attempt — a duration, so the client anchors it to its own clock and counts down). Status, not failure — the next token clears it |
| `token_usage` | `Custom` | one model call's bill: `input_tokens`, `output_tokens`, `cache_read_tokens`, `context_window`, `model`, `scope` (`thread`, `subagent`, or `compaction` for the summariser — all three are on the bill, only `thread` drives the gauge), `cost_usd` (from `agents/models.PRICING`; `null` for an unpriced model, never a guess) |
| `context_compacting`, `context_compacted` | `Custom` | the harness is summarising old history to make room, then did. The summariser's own tokens never reach the transcript. Also emitted by the insights runner around an emergency compaction: a request the provider rejected as too long is summarised once (`compact_thread`) and retried from its checkpoint; a second rejection is the ordinary `context_window` failure |
| `user_input_consumed` | `Custom` | a message sent mid-turn has reached the model; carries the `client_message_id` the client stamped on it |

### Failures carry a code, never the exception

`step_failed` (no `step_id`) and `pipeline_failed` carry `code`, `retryable`
and a one-sentence `error`. The code is `agents/core/errors.ErrorCode`, decided
once by `classify_error` from the exception's class names and status codes,
looking through whatever wraps it. The same classifier is the `retry_on` of
the model-call retry (`agents/core/lc.ReportedRetryMiddleware`), so a rate
limit retries with backoff and a rejected key fails on the first attempt; and
the frontend maps the code — not the message text — to copy and to the action
it offers (`lib/agentSession.js` `errorAction`: retry, open model settings,
open connections, start fresh). `str(exc)` never reaches the browser: it has
carried request ids, and once a URL with a key in it.

The failure is also durable. `ConversationRecorder` appends a `failure` event
where the turn died and writes `agent_conversations.run_status` (`RunStatus`:
idle / running / paused / failed / cancelled) and `run_error` with the same
`{code, retryable, error}`; a session closed mid-turn is recorded as
`cancelled`. The conversation list and the state route carry `run_status` and
`run_error`, so a thread list can badge "Needs you" or "Failed" before anyone
opens the thread, and a reloaded transcript shows the failure as the same row
the live client did — with the same action under it. The status is derived
from the stream in that one place on purpose: a runner that also wrote it
would be a second opinion about one column.

### Input while a turn runs: steer or queue, never refuse

The chat route never answers 409 to a message. If the session's harness can
inject a message at its next model call — `BaseAgentSession.steer_queue` is
set, which the insights runner does through `agents/core/lc.SteerMiddleware`,
a `before_model` hook so the injected message is checkpointed with the
thread — a message that arrives mid-turn or while parked on a card is steered:
the model reads it right after the tool result it was waiting on. Otherwise it
waits on `chat_queue` for the next turn. Either way the client marks the row
"queued" until `user_input_consumed` names it. A steer that lands after the
turn's last model call becomes the next turn (`_leftover_steers` in the
insights runner), not a surprise at the top of whatever the user asks next.

### Persisted conversation kinds

| Kind | AG-UI |
|---|---|
| `user`, `assistant` | `MessagesSnapshot` |
| `thinking` | `ReasoningMessageContent` |
| `tool_use` | `ToolCallStart` |
| `tool_result` | `ToolCallResult` |
| `question`, `answer` | `Custom` |
| `failure` | `RunError` — `{code, retryable, error}` where a turn or run died; `code: cancelled` for a stop |

---

## 4. Artifacts, not reports

The streaming tag is `<duct_artifact>`. It used to be `<duct_report>`, which
stopped being accurate the moment content started emitting plans and post
drafts through the same mechanism and the artifact store began versioning all
of them alike. "Report" was audit vocabulary sitting on a shared primitive.

Two wire values changed with it:

| Was | Is |
|---|---|
| `report_chunk` | `artifact_chunk` |
| `report_updated` | `artifact_version` |

**Migration:** the parser accepts *both* tags, so conversations recorded before
the rename still replay and a turn in flight against a cached system prompt
does not strand its payload. The frontend accepts both event strings; the
backend emits only the new ones. An older app meeting a newer backend is the
only broken pairing, so:

> **Deploy the app first, then the backend.**

Drop the frontend's `LEGACY_*` branches once both are out. The Python aliases
`AgentEvent.REPORT_CHUNK` / `REPORT_UPDATED` are gone — nothing referenced them,
and a deprecated alias nobody uses is just a second name to keep true.

### What deliberately did *not* change: `artifacts.kind`

`kind` on the `artifacts` row stays `"report"` for audit output, and that is not
an oversight. It is a **semantic discriminator** — `report | document | ticket |
image` ([`models/artifact.py`](../../backend/models/artifact.py)) — so it names
what an artifact *is*, not the mechanism carrying it. Renaming it to `"artifact"`
would make every artifact's kind be "artifact": the column would carry zero
information, and it would take a data migration to get there.

The distinction that matters:

| Layer | Vocabulary | Why |
|---|---|---|
| Mechanism — tag, events, parser, persister | **artifact** | shared by every agent |
| Value — `artifacts.kind`, `AuditReport`, `summarize_report` | **report** | this artifact really is a report |

`tests/test_harness_boundaries.py::test_no_live_event_uses_report_vocabulary`
pins the first row. The second is left alone on purpose.

---

## 5. Model transport and bring-your-own-model

`Provider.OPENROUTER` is not a fourth SDK — it is the OpenAI-compatible chat
completions shape pointed at a different base URL. Adopting the shape rather
than the vendor is the point: the endpoint is a config value
(`openrouter_base_url`), so the same code path reaches OpenRouter, a local
Ollama, vLLM, llama.cpp, or a self-hosted gateway.

Two details worth knowing:

- **The model list is curated, not a whitelist.** OpenRouter fronts hundreds of
  models, so an unrecognised `vendor/slug` is passed through verbatim rather
  than silently replaced by a default — substituting would discard the model a
  BYO-key customer explicitly chose, which is the whole feature. A bare name
  with no slash is treated as a typo and does fall back.
- **Only v1 supports it.** The Claude Agent SDK is provider-locked by design
  (upstream issue #410, closed `not planned`), so v3 asked for OpenRouter
  degrades to Anthropic rather than appearing to work. That asymmetry is the
  argument for v1 as the target harness, stated in code.

### Open-source gateways work already — that is the point

Because the port is the *shape* and not the vendor, every self-hostable
OpenAI-compatible gateway is reachable today by setting `openrouter_base_url`.
No new provider, no code change:

| Gateway | License | Runtime | Notes |
|---|---|---|---|
| **LiteLLM** | MIT | Python | 100+ providers, virtual keys, spend control. The default choice. |
| **Bifrost** | open source | Go | ~11µs routing overhead at 5k RPS; LiteLLM's Python path climbs sharply past ~500 RPS |
| **Portkey Gateway** | MIT | Node | adds guardrails + observability |
| **LLM Gateway** | **AGPLv3** | Docker | closest OSS equivalent to OpenRouter's whole platform (dashboard, caching, analytics) — but check the licence before embedding |
| **Envoy AI Gateway** | open source | Kubernetes | for a cluster that already runs Envoy |
| Ollama / vLLM / llama.cpp | open source | local | not gateways — model servers, same OpenAI-compatible path |

**The honest limit.** These replace OpenRouter's *interface and key management*,
not its **commercial aggregation**. Self-hosting LiteLLM does not get you
DeepSeek — it gets you a uniform way to call DeepSeek once you hold a DeepSeek
account. OpenRouter's distinct value is that one commercial relationship reaches
60+ providers, which for a bring-your-own-key product is the difference between
a customer pasting one key and pasting fifteen.

So the two are complements, not substitutes: OpenRouter as the default for
"paste one key and go", a self-hosted gateway for anyone who wants no third
party in the request path, local model servers for fully-private runs. All three
are the same code path.

If a second endpoint ever ships as a first-class option, the clean shape is to
split `Provider.OPENROUTER` into a generic `Provider.OPENAI_COMPATIBLE` (base
URL required, no default) with OpenRouter as one preset. That is a second
implementation of the port, so build it when it exists — not before.

---

## 6. Observability

The harness gives us nothing. LangChain's own tracing goes to LangSmith, a
second vendor and a second place to look. The one harness that carried OTel
built in was the Claude Agent SDK — its subprocess inherited Sentry's OTLP
endpoint from an env var — and it went, taking that plumbing with it.
"Observability comes free with the harness" was never true of the harness we
kept.

So [`backend/agents/core/telemetry.py`](../../backend/agents/core/telemetry.py)
emits the OpenTelemetry GenAI conventions from our side of the boundary:
`model_span` around model calls, `tool_span` around tool execution — the latter
placed at the choke point *both* binders share, so one span shape covers
LangChain and the Claude Agent SDK alike.

The conventions are still experimental and moved to their own repository in
June 2026, so the attribute names are **pinned as our own copy** rather than
imported from the package's private `_incubating` module, and
`tests/test_telemetry.py` diffs the copy against the installed package. Drift
surfaces as a failing test instead of as silently wrong telemetry.

`opentelemetry-api` is a declared dependency rather than one inherited
transitively from `google-adk` — otherwise retiring the frozen v2 engine would
have silently stopped the spans. The import is still guarded and degrades to a
no-op regardless, because telemetry must never be why an agent run fails.
