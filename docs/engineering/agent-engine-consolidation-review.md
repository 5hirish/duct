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
