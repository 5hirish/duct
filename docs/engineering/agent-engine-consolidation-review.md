# Agent engine consolidation review — v1 (LangChain) / v2 (Google ADK) / v3 (Claude Agent SDK)

> **Status:** review + recommendation. No code changes yet.
> **Question:** we run three insight engines behind `GENERATE_ENGINE`. We cannot maintain
> three agent frameworks going forward. Which one survives, what do we lose, and how do
> projects like [Hermes Agent](https://github.com/NousResearch/hermes-agent) solve the same problem?

> ⚠️ **Superseded in part — read [§6](#6-revision--byo-model-changes-the-answer) first.**
> Sections 1–5 were written assuming Duct supplies the model and the agentic loop may stay
> Claude-shaped. It may not: the product intent is **customers bringing their own model**
> (OpenAI / Gemini / Claude / Chinese APIs, via OpenRouter). That moves the portability
> requirement *into* the agent loop and changes the recommendation from "consolidate on v3"
> to "consolidate on a model-agnostic harness". §1–4 (the evidence) stand as written; §5's
> conclusion is revised by §6.

**Original recommendation:** keep **one harness** (`agents/core` + Claude Agent SDK) and
move provider portability **down a layer** — to a transport/model seam, the way Hermes does —
instead of maintaining a whole agent framework per provider.

**Revised recommendation ([§6](#6-revision--byo-model-changes-the-answer)):** one harness
still — but **`deepagents` (LangChain), not the Claude Agent SDK.** Promote v1 rather than
retire it; keep Claude as a *model* option, not as the harness.

---

## 1. What we actually have today

The "three engines" framing is already less true than the config suggests. Only the
**insights** agent has three runners. The two agents we have built since — audit and
content — are v3-only and hardcode it:

```
routes/content.py:132     provider = resolve_engine_provider(Engine.V3, ...)
agents/audit/v3/runner.py:254  effort: AgentEffort = ENGINE_DEFAULT_EFFORT[Engine.V3]
```

There is no `audit/v1`, no `content/v2`. `agents/registry.py` lists three live agent types
(`audit_seo`, `insights`, `tiktok_studio`); two of them can only run on v3.

### Code mass

| Component | LOC | Engine |
|---|---:|---|
| `agents/core/` (sessions, streaming, events, artifacts, tool_schema, persona) | 1,284 | v3 only |
| `agents/audit/v3/` + `agents/content/v3/` | 2,267 | v3 only |
| `agents/insights/v3/` | 644 | v3 |
| `agents/insights/v2/` (ADK) | 877 | v2 |
| `agents/insights/v1/` (LangChain/LangGraph) | 572 | v1 |

The shared harness that everything new is built on — `agents/core/` — is **Claude Agent SDK
plumbing end to end**. v1 and v2 get none of it.

### Where the work is actually going

Commit counts per directory:

| Directory | Commits | Last touched |
|---|---:|---|
| `agents/content/` | 40 | 2026-06-15 |
| `agents/audit/` | 27 | 2026-06-15 |
| `agents/core/` | 17 | 2026-06-15 |
| `agents/insights/v2/` | 11 | 2026-06-18 |
| `agents/insights/v3/` | 9 | 2026-06-18 |
| `agents/insights/v1/` | 6 | 2026-06-14 |

84 of 110 commits landed on the v3-only surface. The multi-engine work is a maintained
museum, not an active investment.

### The uncomfortable detail

`config.py:157` still ships `generate_engine: str = Field(default="v1")`. **The least-invested
engine is the production default for insights.** Whatever we decide, that line is wrong today.

---

## 2. Capability comparison

This is the part that decides the answer. Not "which framework is nicer" — which framework
can express the product we are already shipping.

`agents/registry.py` declares the capabilities our agents advertise. Here is which engine can
actually deliver each one, **in this codebase**:

| Capability (`AgentCapability`) | v1 LangChain | v2 ADK | v3 Claude SDK |
|---|:--:|:--:|:--:|
| `STREAMING` (token/thinking SSE) | ✗ | ✗ (`StreamingMode` wired, unused by routes) | ✓ `core/stream.py` |
| `INTERACTIVE_QUESTIONS` (mid-run HITL) | ✗ | ✗ | ✓ `AskUserQuestion` + `core/session.py` bridge |
| `VERSIONED_OUTPUT` (`<duct_report>` artifacts) | ✗ | ✗ | ✓ `DuctReportStreamParser` |
| `CHAT` (session stays alive for follow-ups) | ✗ | ✗ | ✓ disk-backed JSONL sessions |
| `FILE_UPLOAD` (images in chat) | ✗ | ✗ | ✓ |
| `DATA_CONNECTORS` | ✓ | ✓ | ✓ |
| Subagents / delegation | partial (LangGraph nodes) | ✓ (`LlmAgent` nodes) | ✓ `AgentDefinition` |
| MCP tools | ✗ | ✓ | ✓ `insights/v3/mcp_server.py` |
| Todo/progress surface | ✗ | ✗ | ✓ `TodoWrite` |
| Effort control | ✗ | ✗ | ✓ `AgentEffort` |
| Native structured output | ✓ `with_structured_output(strict)` | ✗ text-parse via `schema_compat.py` | partial — parse `ResultMessage.result` |
| Multi-provider models | ✓ 3 providers | ✓ 3 providers (OpenAI via LiteLLM) | ✗ Claude family only |
| Runs in-process (no subprocess) | ✓ | ✓ | ✗ spawns the `claude` Node CLI |

Two rows carry the argument.

**Row block 1 — the product rows are all v3.** Every capability that makes Duct feel like a
product rather than a batch job (streaming reasoning, asking the operator a question
mid-audit, versioned reports, chat continuation) exists only on v3. v1 and v2 are
request→response synthesis engines. If insights is ever going to match the audit/content
experience, it has to move to v3 regardless of what we do with the others.

**Row block 2 — v3 pays for it.** Claude family only, and it runs the `claude` CLI as a Node
subprocess. `agents/core/claude_sdk.py` is 383 lines that exist *purely* to survive that
subprocess: startup-crash classification, retry with backoff, config-dir isolation from an
interactive `~/.claude`, `NODE_OPTIONS`/`CLAUDE_CODE_SSE_PORT` scrubbing, Sentry tagging.
On a 1 CPU / 1 GiB Railway container (`railway.json`) that is a real operational tax, and it
is honest to name it as the price of the capability list above.

### The v2 verdict is already written in our own code

`tests/eval/client.py` calls `google-genai` directly for the judge, and says why:

> "We call `google-genai` directly rather than Google ADK: in this codebase the ADK/v2 path
> neither accepts image input nor emits native structured output."

We have already routed around v2 for our own QA harness. v2 duplicates v1's provider
portability, adds a second orchestration model to learn, and loses native structured output
(hence `schema_compat.py`, 87 lines of text-scraping JSON out of prose). Externally it is the
newest and smallest-community entrant of the three. It is the clearest deletion.

### Test coverage confirms the same ranking

`tests/test_insights_v2.py` is 158 lines. There is **no** `test_insights_v1.py` and **no**
`test_insights_v3.py`. Meanwhile `test_audit_*.py` + `test_content_*.py` total ~2,500 lines.
We are testing the engines we are not investing in, and not testing the one we are.

---

## 3. Triplicated seams — the actual maintenance cost

The cost is not "three folders". It is that every new capability crosses three
incompatible seams:

| Seam | v1 | v2 | v3 |
|---|---|---|---|
| Tool definition | `StructuredTool` + Pydantic `args_schema` (`insights/tools.py`) | bare typed callables, docstring = description (`v2/tools.py`) | stdio MCP server + hand-written JSON Schema (`v3/mcp_server.py`) |
| Structured output | `with_structured_output(json_schema, strict=True)` | regex/JSON scrape (`schema_compat.py`) | `ResultMessage.result` → `model_validate_json` |
| State | LangGraph `InMemorySaver` checkpoints | ADK `InMemorySessionService` + `state_keys.py` | disk-backed JSONL session |
| Credentials | constructor kwarg via `get_api_key_kwargs` | mutate `os.environ`, restore after | mutate `os.environ` (should be `ClaudeAgentOptions(env=)`) |
| Orchestration | LangGraph `StateGraph` (2 graphs) | ADK dynamic-workflow node + `Context.run_node` | `AgentDefinition` subagents |

One credit where it is due: tool *descriptions* are single-sourced in
`agents/insights/tools.py` (`TOOL_DESCRIPTIONS`) and v2/v3 import them. That instinct — share
semantics, not plumbing — is exactly right, and it is the seed of the recommendation below.

Dependency weight for the privilege: `langchain`, `langchain-openai`,
`langchain-google-genai`, `langchain-anthropic`, `langgraph`, `google-adk`,
`claude-agent-sdk` — **seven agent-framework dependencies**, seven independent release
cadences, on one 1 GiB container. ADK 2.x already forced one migration
(`SequentialAgent` removed → dynamic workflow node, see the `v2/agents.py` docstring). That
bill arrives again on every major of every framework.

The credential seam also hides a live bug, already caught in the BYO-keys plan
(`tauri-desktop-byo-keys-plan.md` §4): `if api_key and not os.environ.get(env_var)` means a
**server key in the env wins and the user's BYO key is silently ignored**, and concurrent
requests with different user keys race on the same global. That bug exists twice (v2 and v3)
because the seam exists twice.

---

## 4. How Hermes-like projects solve this

[Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research) is the useful
comparison because it faces our exact constraint at much larger scale — it is provider- and
model-agnostic across 30+ providers, and it is maintained by a small team.

**It does not have three engines. It has one agent loop and many transports.**

From the architecture docs:

> "Format conversion and HTTP transport are abstracted into `agent/transports/` behind a
> `ProviderTransport` ABC." Concrete transports: `AnthropicTransport`,
> `ChatCompletionsTransport`, `ResponsesApiTransport`, `BedrockTransport`.
> "Streaming, retries, prompt cache, and credential refresh remain on `AIAgent`."

The load-bearing decisions:

1. **Abstract at the wire, not at the framework.** A transport owns exactly four things:
   message-format conversion, tool-call translation, API param assembly, response
   normalization. Everything above it — the loop, tools, memory, streaming, retries — is
   written once.
2. **No vendor agent SDK in the core.** Hermes builds on raw HTTP APIs. It does not adopt
   LangChain's abstractions *and* ADK's *and* Anthropic's; adopting a vendor's agent harness
   means adopting its tool model, its state model, and its migration schedule.
3. **Four concrete transports cover 30+ providers**, because most providers are
   OpenAI-chat-compatible. Provider count and transport count are not the same number — this
   is why our "three providers ⇒ three frameworks" instinct overpays.
4. **Resilience lives above the transport, not per-provider.** Three layers:
   credential pools (rotate keys within a provider), primary model fallback (switch
   provider:model on failure), auxiliary task fallback (vision/compression/extraction resolve
   providers independently). Fallback fires at most once per turn to avoid cascades.
5. **Capability differences are declared, not forked.** Vision, prompt caching, structured
   output are transport capability flags the one loop queries — not a reason to write a
   second loop.

Point 4 maps directly onto something we already do right without naming it: our eval judge
and image generation call `google-genai` **directly**, bypassing every agent framework,
because they are single-shot multimodal/structured calls. That is Hermes' "auxiliary task
fallback" pattern discovered independently. The lesson is that **agentic loops and one-shot
model calls are different problems and deserve different layers** — not different frameworks.

The honest caveat: Hermes reimplements streaming, retries, caching, tool-loop, and memory
itself. That is the trade — you own the harness instead of renting it. Our situation is
different in one important way: we are currently *renting three harnesses and paying for the
seams between them*, which is the worst of both.

---

## 5. Recommendation

**Consolidate on one harness — `agents/core` + Claude Agent SDK — and keep provider
portability at a transport seam below it.**

Consolidating the harness is **not** the same as going single-provider. Those are separate
decisions and we should make them separately:

- **Harness (agent loop, tools, streaming, sessions, HITL):** one. v3/`agents/core`. This is
  where all our capability lives and all our commits go.
- **Model calls (synthesis, judging, vision, image gen, cheap classification):** pluggable.
  This is where BYO keys and cost control actually live.

That split matters because `tauri-desktop-byo-keys-plan.md` commits us publicly to
"Anthropic / OpenAI / Gemini, plus OpenRouter later". That commitment is satisfied by a
transport seam. It does not require LangChain, and it certainly does not require ADK. Note
that **OpenRouter is itself the Hermes answer** — one OpenAI-compatible transport, dozens of
models.

Two constraints to design around, both already partly acknowledged in the code:

- **Auth:** the hosted/multi-user product must use Console API keys. The
  `CLAUDE_CODE_OAUTH_TOKEN` path is a local/self-hosted-operator convenience only —
  Anthropic does not permit subscription auth for third-party products. `routes/engines.py`
  already leads with the compliant method; keep it that way and do not build UI that implies
  otherwise.
- **Claude-family lock on the agentic path.** Bedrock and Vertex are *hosting* options, not
  model diversity. Accept this for the agent loop; recover optionality at the transport seam
  for everything else.

### Phased plan

**Phase 0 — stop the bleeding (small, do now)**
- Flip `config.py` `generate_engine` default `v1` → `v3`; keep `GENERATE_ENGINE` as an escape
  hatch for one release.
- Add `tests/test_insights_v3.py` — we currently ship the intended default untested.
- Fix the BYO-key precedence bug once, on v3: inject via `ClaudeAgentOptions(env={...})`
  instead of mutating `os.environ`. (This unblocks the desktop plan regardless.)

**Phase 1 — delete v2 (highest value, lowest risk)**
- Remove `agents/insights/v2/`, drop `google-adk`, drop `Engine.V2` from `agents/engines.py`
  and `/api/engines/status`.
- Removes ~877 LOC, one framework, and the `schema_compat.py` text-scraping path.
- Nothing depends on it: audit, content, and the eval judge all bypass it already.

**Phase 2 — move insights onto `agents/core`**
- Port the insights v3 runner to the shared harness so insights gains streaming, sessions,
  chat, and `<duct_report>` versioning — the capabilities audit and content already have.
- Replace `insights/v3/mcp_server.py`'s hand-written JSON Schema with `core/tool_schema.py`
  so tool definition is one seam across all agents.

**Phase 3 — retire v1 as an "engine", keep it as a transport**
- v1's only remaining unique value is native strict structured output on non-Claude models.
- Replace it with a ~200 LOC direct-SDK synthesis path (`google-genai` / Anthropic Messages /
  OpenAI-compatible) behind a `SynthesisTransport` protocol — the same pattern
  `tests/eval/client.py` already uses successfully.
- Drops five `langchain*`/`langgraph` deps from the runtime.

**Phase 4 — formalize the seam**
- Introduce `agents/core/transports/` with a `ProviderTransport`-style protocol:
  `AnthropicAgentTransport` (Claude Agent SDK, the agentic path) and
  `MessagesTransport` / `GeminiTransport` / `OpenAICompatTransport` (one-shot structured and
  multimodal calls).
- Repurpose `agents/engines.py`: it becomes a **provider/model/capability registry**, which is
  what it is genuinely good at, rather than an engine registry. `/api/engines/status` becomes
  provider status and directly serves the BYO-keys UI.
- Add Hermes-style resilience where it pays: per-provider key rotation and one-shot fallback
  on rate limits. `core/claude_sdk.py` already detects rate limits (`RATE_LIMIT_HINTS`) but
  can only report them — a transport seam lets it fail over instead.

### What we lose, stated plainly

- **Model-choice benchmarking across frameworks.** We lose the ability to A/B a full
  LangGraph pipeline against an ADK one. We keep the ability to A/B *models*, which is the
  question that actually affects cost and quality.
- **A hedge against Anthropic.** Real, and worth naming. It is mitigated, not eliminated, by
  Phase 3/4: prompts, tools, schemas, and goals stay framework-neutral, so the agentic loop is
  the only Claude-shaped component. Rebuilding that loop against another vendor is weeks of
  work — but it is weeks we are currently paying *continuously* to avoid.
- **ADK's A2A support.** ADK has first-class A2A alongside MCP. We use neither today, and MCP
  is available on v3.

### Objection: "if we drop v2 we lose model choice and are married to Anthropic"

This is the first objection the plan gets, and it conflates two separate things. Four facts
from the code:

**1. Dropping v2 costs zero provider coverage.** `ENGINE_SUPPORTED_PROVIDERS` gives v1 and v2
the *identical* frozenset — `{OPENAI, GOOGLE_GENAI, ANTHROPIC}`. v2 is a second copy of the
same portability, and the worse copy: no native structured output, no image input. After
deleting v2 we still run all three providers, on v1, unchanged. **The multi-provider question
is entirely about v1** — and nothing is deleted before its replacement exists (v1 stays frozen
and callable until Phase 3 lands the synthesis transport).

**2. We are already married, for two of three agents.** Audit and content are v3-only today.
Retaining v2 does not create optionality for them; it only gives insights an escape hatch
nothing else in the product has.

**3. Insights barely uses the LLM.** In `insights/v3/runner.py`, Phase 1 is `asyncio.gather()`
over pre-credentialed Python callables (`:135`) — no LLM tool loop; the MCP server is not
wired into that path. The only LLM-shaped step is Phase 2 synthesis: a single structured-output
call (`:233`). One structured call is the most portable thing in the codebase, and
`tests/eval/client.py` already demonstrates the replacement in ~30 lines of `google-genai`.

**4. The pattern being defended is already in production, inside a Claude agent.** The content
agent is a Claude Agent SDK loop whose `generate_image` tool calls Gemini directly
(`agents/content/tools.py:1200` → `service/gemini/client.py`). Claude orchestrates, Gemini
renders — two providers in one agent, with no LangChain and no ADK in the path.

Conclusion: **model diversity does not live in the engine layer. It lives at the model-call
layer, and we already have it there.** What genuinely stays locked is the agentic loop for
audit and content — a lock that exists today and that retaining ADK does nothing to loosen.
The only real hedges are keeping prompts/tools/schemas framework-neutral (they already are)
or owning the loop ourselves, which is the Hermes trade in full.

### What we keep

`agents/engines.py` is good work and should survive the consolidation — the resolver
functions, provider defaults, per-provider env var mapping, and `PROVIDER_CONFIG_ATTR` are
exactly the registry a transport layer needs. Single-sourced `TOOL_DESCRIPTIONS`, the goal
registry, `SynthesisSchema`, and the prompt modules are all already framework-neutral. The
consolidation deletes runners and adapters, not domain logic.

---

## 6. Revision — BYO model changes the answer

**New requirement:** Duct is to be offered to other people who already pay for a model —
OpenAI, Gemini, Claude, or a Chinese API — and use *their* credentials. That is why
OpenRouter was in the BYO-keys plan.

This is not the requirement §1–5 were answered against. If the customer supplies the model,
**the agentic loop itself must be provider-portable**, not just the synthesis call. Every
"the loop can stay Claude-shaped" conclusion in §5 fails.

### 6.1 First, a product correction: subscriptions are not API access

The plan says "folks who have an OpenAI subscription or Gemini or Claude subscription". For
all three, a consumer subscription does **not** grant programmatic access:

| Vendor | Can a third-party app use the customer's *subscription*? |
|---|---|
| OpenAI | **No.** ChatGPT Plus/Pro is the web app; the API is separate billing, separate keys. Not a policy quirk — a different product. |
| Google | **No.** A consumer Gemini subscription is not an AI Studio / Vertex API credential. |
| Anthropic | **Unstable.** Banned for third-party agents 4 Apr 2026; reinstated 13 May under a *separate* Agent SDK credit pool (Pro $20 / Max5x $100 / Max20x $200) effective 15 Jun; that change was then paused on 15 Jun. Three reversals in three months. |

**Implication:** in practice every customer hands us an **API key**, and for the long tail
(Chinese models, open-weight) that key will usually be an **OpenRouter** key — 500+ models,
60+ providers, one OpenAI-compatible endpoint, with its own BYOK passthrough at 5% of
upstream cost. DeepSeek, Qwen, Kimi, MiniMax and GLM are all reachable over OpenAI-compatible
endpoints, directly or via LiteLLM.

This is good news for the architecture: the target surface is "OpenAI-compatible + native
Anthropic + native Gemini", which is exactly the four-transport shape Hermes settled on. It
also means the Anthropic subscription question resolves itself — **do not build the business
on subscription auth**, whatever the policy says this quarter.

### 6.2 Will Anthropic open the Agent SDK to other models? No.

Asked and answered upstream:
[`anthropics/claude-agent-sdk-python` #410](https://github.com/anthropics/claude-agent-sdk-python/issues/410)
— *"Is it possible to use Non-Anthropic models with Claude Agent SDK via LiteLLM or
otherwise?"* — **closed as `not planned`.** Bedrock and Vertex remain hosting options for
Claude models, not model diversity. The Claude Agent SDK is a provider-native harness by
design and there is no roadmap to change that.

So v3 cannot be the harness for a BYO-model product. That is now a documented fact, not an
inference.

### 6.3 Capability parity — both alternatives moved a long way since we wrote v1/v2

Our v1 and v2 runners are frozen snapshots of frameworks that have since shipped most of what
we went to the Claude Agent SDK for.

**LangChain — `deepagents` 0.7.6 (13 Aug 2026), released on a ~weekly cadence (0.6.0 May →
0.7.0 Jul → 0.7.6 Aug).** Billed as "the batteries-included agent harness", sitting on
`create_agent`/LangGraph:

- sub-agents with isolated context windows; skills loaded on demand; built-in todos
- HITL — approve / edit / reject tool calls before they run, plus an auto-approval classifier
  with review timeouts, and rejection reasons phrased for the model
- pluggable filesystem backends (local / sandboxed / remote), shell in a sandbox of choice
- context compaction, tool-output offload to disk, prompt caching, `DeltaChannel`
  checkpointing so long threads stay cheap
- MCP client (any MCP server) plus your own functions
- streaming, persistence and checkpointing inherited from LangGraph
- hooks v2 GA + plugin loading; per-session cost thresholds; `CodeInterpreterMiddleware`
- **harness profiles** — per-provider/per-model bundles (system-prompt tweaks, tool
  overrides, middleware, subagent defaults) applied automatically when a model is selected.
  This is precisely the "different models need different harness tuning" problem BYO creates.
- **model-agnostic by design:** "any LLM that supports tool calling — frontier, open-weight,
  or local", incl. OpenAI/Anthropic/Google, Baseten/Fireworks, Ollama/vLLM/llama.cpp

The parity evidence that matters: LangChain's own `deepagents-code` CLI went from outside the
Top 30 to **Top 5 on Terminal-Bench 2.0, 52.8 → 66.5**, with the **model held fixed** — pure
harness engineering. A model-agnostic harness reaching Claude-Code-class agentic behaviour is
no longer theoretical.

**Google ADK 2.7.0 (13 Aug 2026)** has also moved well past what our v2 uses: graph-native
workflows, resumable HITL for standalone nodes and `NodeTool`, state-based resumption, skill
registries, remote sandboxes (Cloud Run, Daytona), A2A 1.x, exposing an ADK agent *as* an MCP
server, tools returning media across Gemini/Anthropic/LiteLLM, and native Anthropic thinking +
effort configuration. Model breadth comes via LiteLLM (100+ providers incl. DeepSeek).

Both are credible. My §2 verdict on v2 was about *our implementation*, which is genuinely
weak; it was not a fair verdict on ADK 2.7.

### 6.4 Verdict: `deepagents` (LangChain), and for Duct it is not close

| | deepagents / LangGraph | Google ADK 2.7 | Claude Agent SDK |
|---|---|---|---|
| Model-agnostic loop | ✅ native, any tool-calling LLM | ✅ via LiteLLM adapter | ❌ `not planned` |
| OpenRouter / OpenAI-compatible BYO | ✅ first-class | ✅ via LiteLLM | ❌ |
| Subagents / skills / todos | ✅ | ✅ | ✅ |
| HITL mid-run | ✅ approve/edit/reject + classifier | ✅ resumable | ✅ `AskUserQuestion` |
| MCP client | ✅ | ✅ (+ serve as MCP) | ✅ |
| Streaming + checkpoint/resume | ✅ LangGraph | ✅ | ✅ (JSONL sessions) |
| Per-model harness tuning | ✅ harness profiles | partial | n/a |
| Runs in-process | ✅ | ✅ | ❌ Node CLI subprocess |
| Already a Duct dependency | ✅ `langchain ^1.0`, `langgraph ^1.1` | ✅ `google-adk ^2.2` | ✅ |

Deciding factors, specific to us:

1. **v1 is not legacy — it is the closest thing we have to the destination.** We already ship
   `langchain ^1.0` + `langgraph ^1.1`; `deepagents` sits directly on `create_agent`. The
   migration is an upgrade of the engine we were about to delete, not a fourth rewrite.
   *This reverses §5 Phase 3.*
2. **Widest model coverage, which is now the product requirement** — and the only option
   whose harness is itself the product being benchmarked.
3. **ADK's portability is an adapter (LiteLLM) bolted to a GCP-shaped framework.** Choosing it
   trades Anthropic's harness for Google's; the complaint that started this review applies
   again in softer form.
4. **Losing the `claude` Node subprocess is a bonus** — `core/claude_sdk.py`'s 383 lines of
   startup-crash handling largely evaporate, which matters on a 1 CPU / 1 GiB container.

Honest caveats: ADK 2.7 is strong and ahead on A2A and resumable HITL — if we were GCP-native
this would be a real contest. And `deepagents` is 0.x on a weekly cadence; pin exactly and
budget for churn. (A lighter third option, Pydantic AI, is model-agnostic but is a typed
agent library, not a harness — we would be back to building `agents/core` ourselves.)

### 6.5 What the migration actually costs

We lose the Claude Agent SDK *harness*, not Claude the *model* — Claude stays a first-class
provider through the new harness. `agents/core` maps over rather than dies:

| `agents/core` today | deepagents equivalent |
|---|---|
| `session.py` registry + `BaseAgentSession` | LangGraph checkpointer + thread ids |
| `AskUserQuestion` future bridge | `interrupt()` / HITL tool configs |
| `stream.py` `pump_stream_event` | LangGraph `stream_mode` events |
| `DuctReportStreamParser` (`<duct_report>`) | **stays ours** — framework-neutral already |
| `artifacts.py` | filesystem backend |
| `claude_sdk.py` (subprocess survival) | **deleted** |
| `AgentDefinition` subagents | `subagents=` |
| `TodoWrite` | built-in todos |
| `AgentEffort` | harness profiles / per-model config |

### 6.6 Revised sequencing

1. **Spike first, decide on evidence.** Port **insights** to `deepagents` — it is the cheapest
   real test (Phase 1 is already `asyncio.gather` over plain callables; only synthesis is
   LLM-shaped). Run it against Claude, GPT, Gemini and one OpenRouter-hosted Chinese model
   through the existing eval harness. That produces a scorecard, not an opinion.
2. **Still delete v2.** Not because ADK 2.7 is bad — because we will not run two
   model-agnostic harnesses, and v1's family is where we already have code, deps and skills.
3. **Add `Provider.OPENROUTER`** to `agents/models.py` / `agents/engines.py` and make it the
   default BYO path. One OpenAI-compatible transport covers the entire Chinese/open-weight
   long tail.
4. **Port audit, then content.** Content last — it is the largest runner (1,298 LOC) and its
   Gemini image tooling already sits outside the harness, so it moves cleanly.
5. **Gate models with evals, per model.** Tool-calling reliability varies sharply across
   open-weight and Chinese models. `backend/tests/eval/` already exists; make a per-model
   scorecard the admission test for the model picker, and only expose models that pass.
6. **Keep `agents/engines.py`** — it becomes the provider/model/capability registry the BYO
   picker reads, which is what §5 wanted anyway.

Unchanged from §5: prompts, tools, schemas, goals and the `<duct_report>` contract are
framework-neutral and survive all of this. The rewrite is runners and adapters.

## 7. Desktop-first changes the product shape more than the engine choice

**New intent:** ship Duct as a **desktop product like Hermes** first, and add cloud only if the
desktop sells. §6's engine conclusion survives this — it gets *stronger* — but the desktop
plan we have on file does not.

### 7.1 The committed desktop plan is the opposite of Hermes

`tauri-desktop-byo-keys-plan.md` §2/§4 is explicit:

> "The desktop app is a *thin client* — it renders our existing Next frontend and calls the
> existing Railway API." … "❌ **No on-device agent execution.** That would force bundling
> prompts/runners into the binary, where `strings binary | grep` recovers them. Agents stay
> on Railway."

Hermes is the inverse — "an autonomous agent that lives on your machine or a server… All data
stays on your machine. No telemetry, no tracking, no cloud lock-in."

**The decisive problem is not philosophical, it is financial.** The thin-client plan does not
defer cloud spend at all: every customer's agent run still burns our Railway compute, and
scales with adoption. "Desktop now, cloud if it makes money" only works if the agent actually
runs on the customer's machine. As written, the plan gives us desktop *packaging* with cloud
*economics* — the worst pairing for a pre-revenue launch.

### 7.2 What Hermes actually monetizes — worth knowing before copying it

Hermes Agent is **MIT-licensed and free**: `pip install`, an `install.sh`, or a native
installer (desktop app shipped 2 Jun 2026). Nous does not sell the desktop app. They sell
**Nous Portal** (launched 27 Apr 2026) — a subscription bundling 300+ models and built-in
tools behind one login — while BYO-key users "skip Portal entirely".

So the reference model is *give away the harness, sell the inference bundle*. Selling the app
**and** having customers BYO keys takes neither margin. That is a viable indie model, but it
is not the Hermes model, and it should be a deliberate choice rather than an inherited
assumption. The realistic third path — and probably the right one later — is our own Portal
equivalent: a hosted key for users who do not want to manage one, priced above cost.

### 7.3 Distribution channel is now the decisive technical call

A local-first agent needs subprocess/sidecar execution, self-update, broad filesystem access
and arbitrary network egress. All four fight the Mac App Store sandbox, and our own
`desktop/CLAUDE.md` already records the blocker:

> "**Never enable `tauri-plugin-updater` for the macOS build.** App Store apps may not
> self-update; it would be rejected. Auto-update is only an option if macOS moves to
> Developer ID / DMG distribution."

Add the known failure mode that sandboxing a PyInstaller-built binary on macOS crashes with
illegal-instruction faults, and the current TestFlight/App-Store track is structurally hostile
to the thing we now want to build. Hermes ships native installers outside the App Store for
exactly these reasons.

**Recommendation: if we go Hermes-like, leave the App Store track** — Developer ID +
notarized DMG + `tauri-plugin-updater`. That unblocks sidecars and auto-update in one move.
Keep TestFlight only if the thin-client shape is what we actually ship.

### 7.4 Correction: the Claude Agent SDK packages fine for desktop

§2 and §6.4 counted the `claude` Node subprocess against v3. For a *server* on a 1 GiB
container that stands. For *desktop* it is largely wrong and should not be used as an
argument: both the npm and the Python `claude-agent-sdk` packages **bundle the Claude Code
binary**, so there is no separate CLI install for end users, and shipping it inside a desktop
app is a supported pattern under Anthropic's Commercial Terms.

v3 remains disqualified — but on **model lock alone** (issue #410, `not planned`), which is
the requirement that matters. Packaging is not the reason.

### 7.5 Desktop-first makes the deepagents case stronger

- **BYO keys stop being a security problem.** Local execution means the customer's key never
  leaves their machine — no per-request key transit, no in-memory server custody, no
  "encrypted at rest / never logged" burden. The hardest part of the BYO-keys plan disappears.
- **Local and open-weight models become a real feature.** `deepagents` supports Ollama, vLLM
  and llama.cpp natively. On a desktop product that is a headline capability — zero-cost,
  fully-private runs — and it is flatly impossible on v3.
- **A TypeScript option appears.** `deepagentsjs` (npm `deepagents`, **v1.12.3**) is the same
  harness for Node: subagents via `task`, filesystem tools, `write_todos`, streaming and
  LangGraph checkpointing confirmed. HITL, MCP and skills parity with the Python package is
  **not** confirmed from its README — treat that as a spike question, not a given.
- **But our domain logic is Python.** Crawling (`selectolax`, `extruct`, `trafilatura`),
  Google Ads / GA4 / GSC clients, `dlt`, SQLModel. A TS harness means porting or IPC-ing all
  of that. Python sidecar almost certainly wins despite the packaging friction.

### 7.6 The good news: we are already 90% of the way to local-first

Duct is a FastAPI server plus a web frontend that talks to it over HTTP. "Desktop" is mostly
*where that server runs*:

| Today | Local-first desktop |
|---|---|
| Next app → `api.getduct.ai` (Railway) | Next app → `127.0.0.1:PORT` (sidecar) |
| FastAPI on Railway | FastAPI as a Tauri sidecar (PyInstaller / uv) |
| Postgres on Railway | SQLite (SQLModel + Alembic already abstract the driver) |
| Keys in Railway memory per request | Keys in OS keychain, never leave the device |
| Prompts server-side only | **Prompts ship in the bundle** — accepted trade |

The same FastAPI app becomes the cloud product later, unchanged. One codebase, two deployment
targets. The only genuinely new decision is the last row.

**On prompt IP:** this is the reason §4 of the desktop plan forbade local execution, and going
Hermes-like means reversing it. Worth reversing: Hermes and OpenClaw are fully open source and
compete fine. Our moat is the domain logic — SEO scoring weights, connector normalization,
the report contract — plus distribution and UX, none of which are protected by prompt secrecy
anyway once a user can read the rendered output.

### 7.7 Revised sequencing for desktop-first

1. **Decide the channel.** App Store/TestFlight (thin client, cloud economics) vs Developer ID
   + DMG (local agent, zero marginal infra). Everything below assumes the latter. This is the
   one call that cannot be deferred.
2. **Decide the monetization shape** — paid app + BYO keys, or free app + hosted-key upsell
   (the Portal model). It determines whether the model picker is a feature or the product.
3. **Run the §6.6 spike anyway** — port insights to `deepagents` and score it across Claude,
   GPT, Gemini and an OpenRouter-hosted model. Desktop does not change this step; it raises
   its value, because on desktop the model picker is customer-facing.
4. **Prove the sidecar early.** PyInstaller-package the existing FastAPI app, point the Tauri
   webview at `127.0.0.1`, run one agent end to end. Do this *before* porting the other
   agents — if Python packaging on macOS proves untenable, that flips us to `deepagentsjs`
   and the whole plan changes.
5. **SQLite path** for local persistence; keep Postgres for the eventual cloud deployment.
6. **Only then** port audit and content off v3.

## 8. Channel decision — Developer ID + notarized DMG

**Decided inputs:** BYO keys + paid app now; a cloud product later where Duct supplies the
model and users need no keys.

**Recommendation: leave the Mac App Store track. Ship Developer ID + notarized DMG with
`tauri-plugin-updater`, sold direct through a merchant of record.**

### 8.1 The channel is not an independent choice

It is downstream of a decision already made in §7:

| | App Store / TestFlight | Developer ID + DMG |
|---|---|---|
| Agent runs | on Railway (thin client) | on the customer's machine |
| Cloud cost at launch | **full** — scales with customers | **zero** marginal |
| Self-update | ❌ prohibited | ✅ `tauri-plugin-updater` |
| Python sidecar | ❌ see 8.2 | ✅ |
| Platforms | macOS only | macOS, Windows, Linux |
| Commission | 15% (Small Business Program) | ~5% + 50¢ (MoR) |

The rows move together. "Desktop first, cloud only if it makes money" **requires** the right
column; picking the App Store silently re-selects the thin client and puts full cloud economics
back at launch. That is the whole decision.

### 8.2 The App Store cannot host the product we described

Not a preference — three independent walls, any one of which is fatal:

1. **PyInstaller sidecar vs the sandbox.** Onefile executables do not work when signed and
   notarized with the sandbox enabled, and the sandbox is mandatory for App Store
   distribution. The onedir workaround (nest the PyInstaller `.app` in Xcode, invoke via
   `NSTask`) is a documented minefield of code-signing and illegal-instruction failures.
   PyInstaller's own tracker carries the issue titled *"Deploying Python PyInstaller App to
   Mac App Store. A lost cause?"*
2. **Embedded interpreters get rejected.** Apps embedding a Python interpreter have been
   rejected under App Review, typically over non-public or deprecated API use.
3. **No self-update.** Already recorded in `desktop/CLAUDE.md`. For a 0.x product sitting on a
   harness that ships weekly (`deepagents` 0.6.0 May → 0.7.6 Aug), shipping fixes only at
   App Review's pace is a serious handicap.

Even if all three were solved, the App Store is **macOS-only**. `tauri.conf.json` already sets
`bundle.targets: "all"` and ships a Windows `.ico`; the moment Windows ships we need the
direct pipeline — installer, licensing, updater — anyway. Building both is double the
release surface for no gain.

### 8.3 Commercials favour direct too

- **App Store:** 15% under the Small Business Program (<$1M/yr). Apple handles payment, global
  tax, refunds.
- **Direct via merchant of record:** Lemon Squeezy at 5% + 50¢, or Polar/Paddle, all of which
  are merchants of record — they handle worldwide VAT/sales tax and carry a license-key API.
  So we do **not** give up tax handling by leaving; that is precisely what a MoR buys.

One thing not to plan around: App Store external-link commissions are actively in flux — US
link-outs sit at 0% after the Epic ruling, while Apple filed a proposal on **13 Aug 2026** for
15% (5% for Small Business) on external-link purchases, pending court approval. Do not build
pricing on that arbitrage in either direction.

### 8.4 What we give up, and why it is acceptable

- **App Store discovery.** Real, but weak for our shape: Duct is B2B growth tooling sold to
  operators who arrive via the marketing site, blog and SEO — a channel we already own and run
  (`site/`). We are not competing for casual store browsing.
- **The trust badge.** Recovered mostly by Developer ID signing + notarization + stapling,
  which removes Gatekeeper warnings entirely. Hermes ships native macOS and Windows installers
  outside any store and it has not held them back.
- **Apple handling billing.** Recovered by the MoR.

### 8.5 The TestFlight work is not wasted

Retire `src-tauri/tauri.appstore.conf.json`, `Entitlements.appstore.plist` and the
`desktop-testflight.yml` App Store leg. Keep everything else — the Apple developer account,
signing certificates, the universal-binary build, icons, the deep-link scheme, and the
`MAJOR.MINOR.PATCH` versioning discipline in `desktop/CLAUDE.md` all carry over. The migration
is roughly: swap the Developer ID cert in, add notarize + staple, enable
`tauri-plugin-updater` (now permitted), and publish a signed update manifest.

Also revisit two `desktop/CLAUDE.md` rules that were App-Store-specific: the updater ban
(lifts) and the version-suffix ban — Apple's rejection of `-beta` no longer applies, so
prerelease tags become available again.

### 8.6 Where the App Store comes back

If the cloud product ships and we later want a companion app for it, that app *is* a thin
client — no sidecar, no self-update needed (the web app updates server-side) — and the App
Store fits it cleanly. Revisit then, on its own merits. The current decision does not close
that door.

## 9. Port map — what actually moves where

"Port v1 to deepagents" is the wrong shape, and acting on it would put the work in the
cheapest place instead of the riskiest one. Two corrections.

### 9.1 LangChain 1.x is layered — pick a layer per agent, not one for everything

`deepagents` is not *the* LangChain API; it is the top of a stack, and each Duct agent needs a
different rung:

| Layer | Adds | Duct agent that needs it |
|---|---|---|
| `init_chat_model` + `.with_structured_output()` | one typed model call | **insights** |
| `create_agent` | tool loop, middleware, HITL interrupts, structured output | **audit** |
| `deepagents` | + subagents, filesystem, skills, compaction, harness profiles | **content** |

Reaching for `deepagents` everywhere would wrap a single synthesis call in a filesystem and a
subagent runtime it never uses.

### 9.2 Insights needs almost no harness — v3 already proved it

`insights/v1` is two `StateGraph`s: Phase 1 is an LLM tool-calling loop, Phase 2 is a single
structured-output node whose own docstring admits the graph is ceremony ("wrapping in a
StateGraph gives checkpointing and streaming parity"). Phase 1's LLM picks tools from
`GOAL_TOOL_ALLOWLIST`, which has *already* filtered them by goal — so the model is choosing a
subset of a list that is deterministic anyway. `insights/v3` replaced that whole loop with
`asyncio.gather()` over the same callables and works.

So insights collapses to: existing goal-filtered `gather()` for fetch, plus
`init_chat_model(...).with_structured_output(SynthesisSchema)` for synthesis. That is
**deleting** `v1/graph.py` (179) and most of `v1/agent.py` (390), not porting them.

### 9.3 What survives untouched

The domain layer was never framework-specific and does not move: `insights/goals/`,
`insights/prompts/`, `insights/schema.py`, `insights/registry.py`, `TOOL_DESCRIPTIONS` and the
fetch functions in `insights/tools.py`, the audit scoring model, the content templates, and the
`<duct_report>` contract. Only the `StructuredTool` wrapper in `insights/tools.py` is
LangChain-shaped — and it is already the *right* shape.

### 9.4 The MCP layer disappears

`agents/audit/tools.py` builds a `create_sdk_mcp_server("duct_crawl", …)`; content does the
same for `duct_content`; insights has `v3/mcp_server.py` (176 LOC) with hand-written JSON
Schema. All of it exists only because the Claude Agent SDK consumes tools over MCP.

LangChain takes plain Python callables via `@tool`. The crawl and content tools become
in-process functions and the MCP servers, bootstrap scripts and schema duplication are deleted
outright. MCP remains available as a *client* for third-party servers if we ever want it.

### 9.5 Revised effort map

| Component | LOC | Action |
|---|---:|---|
| `insights/v2/` (ADK) | 877 | delete |
| `insights/v1/graph.py` + most of `agent.py` | ~569 | delete — replaced by one structured call |
| `insights/v3/mcp_server.py` | 176 | delete — tools become `@tool` callables |
| `audit/v3/runner.py` | 968 | **port** → `create_agent` (HITL + streaming + tools) |
| `content/v3/runner.py` | 1,298 | **port** → `deepagents` (subagents + HITL + images) |
| `agents/core/` | 1,284 | partly replaced by LangGraph primitives (see §6.5) |

Net: the insights work is subtraction; the actual porting is **audit and content coming off the
Claude Agent SDK**.

### 9.6 Consequence for the spike

§6.6 proposed spiking insights first. Keep it — it is a day's work and it proves **model
portability** and gives per-model eval scores — but be clear that it does **not** prove
**harness parity**, because insights barely uses a harness.

The real risk lives in audit: mid-run `AskUserQuestion` bridged to SSE, token/thinking
streaming, and the `<duct_report>` artifact state machine. So run two narrow spikes, not one:

1. **Model spike (insights)** — swap the synthesis call, score Claude / GPT / Gemini / one
   OpenRouter model through `tests/eval/`.
2. **Harness spike (audit slice)** — do *not* port all 968 lines. Prove only:
   `create_agent` + one crawl tool + a LangGraph `interrupt()` surfacing through our existing
   SSE stream + token streaming. If HITL-over-SSE works, the rest is mechanical.

Spike 2 is the one that can still invalidate the plan, so it should not run last.

## 10. Google ADK vs deepagents — capability comparison

Both shipped on **13 Aug 2026**: `google-adk` **2.7.0**, `deepagents` **0.7.6**. Neither is
stagnating and neither is a safe "it'll be abandoned" bet.

**Method and its limit:** the ADK column below is introspected from **2.2.0**, the version
pinned in `pyproject.toml`; deepagents is introspected from 0.7.6. Rows marked *(2.3–2.7)* come
from release notes, not from running code — ADK's newest work is therefore described more
generously than it was verified. Read accordingly.

### 10.1 Where ADK is genuinely ahead

| Capability | Detail |
|---|---|
| **Live / bidirectional multimodal** | `RunConfig` carries `speech_config`, `response_modalities`, `avatar_config`, input/output `audio_transcription`, `realtime_input_config`, `enable_affective_dialog`, `proactivity`, `save_live_audio`. `StreamingMode.BIDI`. deepagents has **nothing** comparable — this is a real category gap, not a nuance. |
| **A2A (agent-to-agent)** | A2A 1.x, with production deployments at Microsoft, AWS, Salesforce, SAP, ServiceNow. |
| **Serve as an MCP server** | ADK can *expose* an agent over MCP. deepagents is MCP **client** only. |
| **Explicit orchestration graph** | `Workflow`, `Node`, `FunctionNode`, `JoinNode`, `Edge`, `RetryConfig`, `NodeTimeoutError`. Per-node retry and timeout are first-class; in deepagents they are your problem. |
| **Declarative agents** | `LlmAgentConfig`, `SequentialAgentConfig`, `LoopAgentConfig`, `ParallelAgentConfig` — agents definable as config, not only code. |
| **Planners** | `BuiltInPlanner`, `PlanReActPlanner` as swappable strategies. |
| **Native compositional agents** | `SequentialAgent`, `ParallelAgent`, `LoopAgent` as primitives. |
| **GCP deployment** | Cloud Run / Vertex / Agent Engine, Daytona remote sandboxes *(2.3–2.7)*. |
| **Context-window compression** | `context_window_compression` in `RunConfig` *(vs deepagents' summarization middleware — comparable, different shape)*. |

### 10.2 Where deepagents is ahead

| Capability | Detail |
|---|---|
| **Model-agnostic by default** | `init_chat_model` covers every provider natively. In ADK, non-Gemini goes through **`LiteLlm`, which is an optional extra** — `google.adk.models` raises ImportError until `google-adk[extensions]` is installed. Multi-provider is core in one and an add-on in the other. |
| **Per-model harness tuning** | `HarnessProfile` / `ProviderProfile` / `register_provider_profile` apply prompt, tool, middleware and subagent overrides automatically when a model is selected. This is precisely the BYO-model problem; ADK has no direct equivalent. |
| **HITL granularity** | `interrupt_on={tool: config}` with `approve` / `edit` / `reject` / `respond`, a `when` predicate, and inheritance into subagents. ADK's HITL is node/`NodeTool` resumption *(2.3–2.7)* — coarser and newer. **Verified running** (`tests/test_deepagents_harness.py`). |
| **Filesystem + context offload** | `backends` (state / local / remote), `FilesystemMiddleware`, `FilesystemPermission`, tool-output offload to disk. The "deep agent" pattern is the product here, not an add-on. |
| **Subagent variety** | Declarative `SubAgent`, `CompiledSubAgent` (pre-built runnable), `AsyncSubAgent` (remote/background). |
| **Persistence ecosystem** | LangGraph checkpointers — memory, **SQLite**, Postgres — interchangeable. SQLite matters directly for our desktop build (§7.6). |
| **Middleware composition** | `SubAgentMiddleware`, `MemoryMiddleware`, `RubricMiddleware`, summarization, prompt-caching; provider-specific ones auto-install and no-op elsewhere. |
| **Harness benchmarked in public** | `deepagents-code` went 52.8 → 66.5 on Terminal-Bench 2.0 with the **model held fixed**. No equivalent public number for ADK's harness. |
| **Dependency weight** | Relevant to the desktop bundle — see 10.3. |

### 10.3 Packaging note, from installing both

In this repo's environment, ADK 2.2.0 has three import failures out of the box:

```
google.adk.tools          -> ImportError: cannot import name 'discoveryengine_v1beta'
google.adk.models         -> ImportError: `LiteLlm` requires an optional dependency
google.adk.code_executors -> ImportError: ContainerCodeExecutor requires additional dependencies
```

Not bugs — optional extras. But it means ADK's surface is fragmented across `google.cloud.*`
packages, which is extra hidden-import work and bundle weight for the PyInstaller desktop
build (§8.2). deepagents imported and ran with no extras.

### 10.4 Verdict for Duct specifically

ADK is a stronger framework than §2 of this document gave it credit for — that verdict was
about *our v2 implementation*, which is weak, not about ADK 2.7.

The choice still goes to deepagents, on three axes that happen to be exactly our requirements:

1. **BYO model is core, not an extra.** Customers arriving with OpenAI / Gemini / Chinese /
   OpenRouter keys are the product (§6.1); `HarnessProfile` addresses per-model tuning directly.
2. **HITL-over-SSE is verified**, and it is the primitive audit depends on.
3. **Desktop packaging** favours the lighter, extras-free dependency graph, and LangGraph's
   SQLite checkpointer lines up with the local data dir.

ADK would win if Duct were GCP-native, needed A2A interop, or built **voice/live multimodal**
agents. The last is the one capability deepagents cannot match at all — if a talking assistant
ever becomes a Duct feature, this decision should be revisited rather than worked around.

## Sources

- [Hermes Agent — NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- [Hermes Agent docs — provider transports and architecture](https://github.com/mudrii/hermes-agent-docs)
- [Hermes Agent — credential pools](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-pools)
- [Hermes Agent — fallback providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers)
- [Claude Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [AI agent frameworks 2026 — provider-native vs independent SDKs](https://www.morphllm.com/ai-agent-framework)
- [Google ADK vs LangGraph — ZenML](https://www.zenml.io/blog/google-adk-vs-langgraph)
- [Anthropic policy on subscription auth for third-party products](https://alternativeto.net/news/2026/2/anthropic-officially-bans-using-subscription-authentication-for-third-party-claude-use)

Added for §6:

- [claude-agent-sdk-python #410 — non-Anthropic models, closed `not planned`](https://github.com/anthropics/claude-agent-sdk-python/issues/410)
- [Anthropic reinstates third-party agent usage on Claude subscriptions — with a catch](https://venturebeat.com/technology/anthropic-reinstates-openclaw-and-third-party-agent-usage-on-claude-subscriptions-with-a-catch)
- [langchain-ai/deepagents — the batteries-included agent harness](https://github.com/langchain-ai/deepagents)
- [deepagents on PyPI — 0.7.6, 13 Aug 2026](https://pypi.org/project/deepagents/)
- [Deep Agents 0.6 — harness profiles, DeltaChannel, code interpreter](https://www.langchain.com/blog/deep-agents-0-6)
- [Improving Deep Agents with harness engineering — Terminal-Bench 2.0, 52.8 → 66.5](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)
- [google/adk-python releases — v2.7.0, 13 Aug 2026](https://github.com/google/adk-python/releases)
- [ADK — LiteLLM model support](https://adk.dev/agents/models/litellm/)
- [OpenRouter — bring your own API keys](https://openrouter.ai/blog/announcements/bring-your-own-api-keys/)
- [ChatGPT Plus does not include API access](https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus)
- [OpenAI-compatible endpoints for DeepSeek, Qwen, Kimi, MiniMax, GLM](https://www.atlascloud.ai/blog/guides/openai-compatible-api-provider-supports-deepseek-qwen-kimi-minimax-glm)

Added for §7:

- [Hermes Agent — installation (pip, install.sh, native installers)](https://hermes-agent.nousresearch.com/docs/getting-started/installation)
- [Hermes Agent desktop app + Nous Portal subscription](https://www.digitalapplied.com/blog/hermes-agent-desktop-app-complete-guide-2026)
- [`@anthropic-ai/claude-agent-sdk` — bundles the Claude Code binary](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)
- [Claude Agent SDK overview — commercial terms and bundled CLI](https://code.claude.com/docs/en/agent-sdk/overview)
- [langchain-ai/deepagentsjs — the TypeScript harness](https://github.com/langchain-ai/deepagentsjs)
- [Tauri v2 — embedding external binaries (sidecars)](https://v2.tauri.app/develop/sidecar/)
- [Tauri v2 + Python sidecar example (PyInstaller)](https://github.com/dieharders/example-tauri-v2-python-server-sidecar)

Added for §8:

- [PyInstaller #7123 — "Deploying Python PyInstaller App to Mac App Store. A lost cause?"](https://github.com/pyinstaller/pyinstaller/issues/7123)
- [Apple Developer Forums — Mac app embedding a Python interpreter rejected](https://developer.apple.com/forums/thread/758567)
- [PyInstaller usage — onefile vs signing/sandboxing](https://pyinstaller.org/en/v6.11.0/usage.html)
- [App Store Small Business Program — 15%](https://developer.apple.com/app-store/small-business-program/)
- [Apple proposes up to 15% on external-link purchases (13 Aug 2026)](https://techcrunch.com/2026/08/14/apple-proposes-to-take-a-15-cut-of-purchases-made-outside-the-app-store/)
- [Tauri v2 — macOS code signing](https://v2.tauri.app/distribute/sign/macos/)
- [Merchant-of-record options for indie desktop licensing](https://www.buildmvpfast.com/blog/lemon-squeezy-vs-polar-paddle-merchant-of-record-2026)
