# Autonomous Insights Agent — design plan

**Status:** Phases 1–5 built, 6 open. Supersedes the request-shaped insights pipeline
(`agents/insights/v1/agent.py` + the six-step wizard at `app/src/app/(app)/generate/page.jsx`).

Companion reading, in this order:
[`agent-ports-and-events.md`](agent-ports-and-events.md) (the boundary this must not break),
[`agent-memory-research.html`](agent-memory-research.html) §07 (memory, Phases 1–3 shipped),
[`agent-memory-on-deepagents.md`](agent-memory-on-deepagents.md) (the harness),
[`intelligent-insights-architecture-plan.md`](intelligent-insights-architecture-plan.md)
(the entity catalog + dashboard blocks, partially built).

---

## 1. The problem, stated precisely

The current insights agent is not an agent. It is a two-call pipeline wearing an
agent's vocabulary:

```
wizard (6 steps, browser)  →  POST /api/insights/generate
                                 ├─ Phase 1: create_agent loop over zero-arg tools (≤6 iters)
                                 └─ Phase 2: one with_structured_output call
                              →  JSON envelope  →  localStorage
```

Every decision worth making has already been made before the model is invoked:

| Decision | Made by | Where |
|---|---|---|
| Which connectors to use | The user, clicking checkboxes | `StepConnections` |
| Which Ads account / GA4 property / GSC site | The user, three dropdowns | `StepAdsAccount` / `StepGa4Property` / `StepGscSite` |
| What the analysis is *for* | The user, picking a goal enum | `StepGoal` + `GOAL_TOOL_ALLOWLIST` |
| Which tools may run | `registry.get_tools_for_request(max_tools=8)` | before the model sees anything |
| What the output looks like | `SynthesisSchema`, fixed | `agents/insights/schema.py` |
| Whether anything gets done about it | Nobody — the run ends at a report | — |

The model's entire remaining agency is *"which of these ≤8 pre-bound, zero-argument
tools are worth calling."* It cannot ask a question, cannot notice a missing
connector, cannot check whether a number is trustworthy, cannot write down what it
learned, and cannot act.

Meanwhile — and this is the finding that shapes the whole plan — **almost every
capability the autonomous version needs already exists in this codebase, built for
audit and content.** The work is overwhelmingly wiring and deletion, not invention.

### What already exists (reuse, do not rebuild)

| Capability | Where | Used by insights today? |
|---|---|---|
| Session lifecycle: create → SSE → messages → conversation persistence → reconnect grace | `routes/agents.py` | ❌ |
| Human-in-the-loop pause/resume on an `asyncio.Future` | `agents/core/session.py::bridge_ask_user_question` | ❌ |
| Bi-temporal memory: table, `remember`/`search`, digest injection, consolidation, timeline UI | `service/memory.py`, `agents/core/memory_tools.py` | digest only, read-only |
| Versioned artifacts: `<duct_artifact>` parser, `ArtifactPersister`, markdown/HTML/JSON content types | `agents/core/stream.py`, `service/artifact_store.py` | ❌ (localStorage) |
| Staged execution: propose → preview → guardrail → approve → apply → rollback, tiered autonomy | `service/execution/`, `agents/tools/execution_tools.py` | ❌ |
| Server-side credential resolution (binding → stored → env) | `service/execution/creds.py` | ❌ (browser tokens) |
| The Gads gotcha corpus, 10 packs | `agents/knowledge/*.md` | audit/content only |
| Entity catalog + prompt serializer | `agents/insights/catalog/` | partially |
| Dashboard block renderers | `app/src/components/insight-blocks/` | ✅ |
| Chat-left / artifact-right shell | `app/src/components/workspace/SplitWorkspace.jsx` | ❌ |
| `deepagents` 0.7.11 pinned, HITL contract gate-tested | `tests/test_deepagents_harness.py` | ❌ — pinned, proven, **unused in production** |

Insights is the only agent that opted out of all of it.

---

## 2. Harness: `create_deep_agent`, and why the rule flips

`backend/CLAUDE.md` records the rule *"pick the lowest rung that works — insights
needs `create_agent`, audit `deepagents`, content the third."* That classification
was correct for the *old* insights shape: one tool loop, one structured call, no
planning, no delegation, no HITL.

The autonomous shape needs exactly the four things `deepagents` adds over
`create_agent`:

1. **A planning loop** — `TodoWrite`-equivalent progress the UI already renders
   (`AuditTodos.jsx`, `AgentEvent.TODO_UPDATE`).
2. **Subagents** — the verification pass (§6) is a separate context with a separate
   job; running it inline pollutes the analyst's context with check plumbing.
3. **Skills** — `agents/knowledge/*.md` is 10 packs and growing. All-in-system-prompt
   does not scale; `SkillsMiddleware` progressive disclosure does. Flagged as a
   "cheap win" in [`agent-memory-on-deepagents.md`](agent-memory-on-deepagents.md) §5
   and this is the port that earns it.
4. **HITL middleware + checkpointer path** — `interrupt_on` is the documented upgrade
   from the in-process Future bridge when runs must survive a restart.

So: **new `agents/insights/v1/runner.py` on `create_deep_agent`**, and update the rung
rule in `backend/CLAUDE.md` rather than quietly contradicting it.

Two properties make this safe, and both should be stated in the runner's docstring
because they are the user-facing guarantee:

- **`deepagents`' filesystem is virtual by default.** `StateBackend` lives in graph
  state, not on disk. The agent gets `read_file`/`ls`/`grep` over *its own scratch
  space and the memory projection*, never the repository. There is no
  `FilesystemBackend`, no `Bash`, no `Read` of real paths.
- **Execution is gated in code, not in prompt.** `service/execution/policy.py` holds
  an absolute destructive gate and a narrow `AUTO_APPLY_ALLOWLIST`, and there is
  deliberately no agent-facing approve/apply tool. An autonomous loop cannot talk
  itself past the review gate — that property must survive this rewrite untouched.

**Cost of the decision:** a second production consumer of a 0.x pin. `deepagents`
changes behaviour in minors (task planning became opt-in in 0.7).
`tests/test_deepagents_harness.py` stays the upgrade gate, and the ports boundary
keeps the blast radius to one runner file.

---

## 3. Shape of the new agent

```
POST /api/agents/insights/sessions   { project_id, prompt?, attachments? }
        │
        ├── system prompt: role + knowledge skills index + block vocabulary + autonomy contract
        ├── user turn:     project memory digest + business context + free-text intent
        │
        └── loop (deepagents)
              ├─ SearchMemory / RememberFact          ← what we already know
              ├─ ListDataSources                      ← what is connected
              ├─ RequestConnection / SelectAccount    ← pauses, asks, resumes
              ├─ AskUserQuestion                      ← only when it changes the answer
              ├─ FetchData(entity_id, …)              ← catalog-driven, creds server-side
              ├─ Task(verify)                         ← subagent: prove the number
              ├─ <duct_artifact> …                    ← markdown by default
              └─ ProposeChanges                       ← autonomy-gated
```

One entry point: **a project and a sentence.** Everything else is discovered,
recalled, or asked for.

---

## 4. Phase 1 — Make insights a session

**Goal:** typing *"why did my CPA jump last week?"* produces a streaming, chatty,
todo-tracked run. No new capabilities yet — just the right shape.

- New `agents/insights/v1/runner.py` (`create_deep_agent`), alongside the existing
  `agent.py`, which stays as the non-interactive synthesis path until Phase 6.
- Register `_start_insights_session` in `routes/agents.py::_dispatch_start`.
- `agents/registry.py`: add `INTERACTIVE_QUESTIONS`, `VERSIONED_OUTPUT`,
  `FILE_UPLOAD` to `_insights_spec()`; rewrite its description.
- Wire the pieces audit already wires: `ConversationRecorder`, `ArtifactPersister`,
  `build_memory_context` (user turn — never the system prompt, per the caching rule),
  `schedule_consolidation` on close.
- Give insights the three memory tools from `agents/core/memory_tools.py`. It is the
  agent with the most durable per-project facts to record (account ids, target CPA,
  which campaigns are seasonal, what we already tried) and it is currently the only
  one that cannot write any of them down.
- Emit the existing `AgentEvent` vocabulary verbatim — the frontend must not be able
  to tell which agent is streaming.

**Exit test:** an insights session and an audit session are indistinguishable to
`app/src/lib/auditEvents.js`.

> **Built 2026-08-31 — and where it diverged.** `tests/test_insights_session.py`
> (21 tests, fake chat model, no network) is the gate. Three departures from the
> list above, all deliberate:
>
> - **`ArtifactPersister` was NOT wired.** It is audit-shaped, not generic:
>   `_persist_report` validates its payload as an `AuditReport` and hardcodes the
>   audit slug, title and filename. Wiring insights into it would mean either
>   faking an `AuditReport` or generalising the persister — and generalising it is
>   Phase 4's actual job, alongside the markdown format it exists to carry. So the
>   runner logs an unexpected `<duct_artifact>` rather than dropping it silently,
>   and `VERSIONED_OUTPUT` stays off the spec until the capability is real.
> - **A shared V1 adapter came first.** `resolve_chat_model`, `stream_agent`,
>   `split_chunk` and `build_ask_user_tool` all lived in `agents/audit/v1/runner.py`.
>   Insights needed every one of them, so they moved to `agents/core/lc.py` — the
>   ports rule's "write the adapter on the second implementation". Audit now calls
>   the shared names directly; no compat shim was kept.
> - **Fixed a real bug on the way through.** `DuctArtifactStreamParser` holds back
>   the last 14 characters of every chunk in case they are a split
>   `<duct_artifact>` open tag, so a turn only completes on `flush()`. Both V3
>   runners flush; **V1 never did**, silently truncating every V1 turn by up to 14
>   characters. Invisible on audit's long reports, fatal for a chat agent — a reply
>   shorter than the tag vanished entirely. `stream_agent` now flushes at the turn
>   boundary; `test_short_replies_are_not_truncated` is the regression.
>
> Also of note: `deepagents`' default filesystem is `StateBackend` (graph state),
> so the mounted `read_file`/`write_file`/`ls`/`grep` cannot reach disk and no
> `Bash` tool exists at all — asserted in
> `test_filesystem_tools_are_virtual_not_the_real_disk`. That is the isolation
> guarantee, held by construction rather than by prompt.
>
> **The agent has no data tools yet** — that is Phase 2/3, and the system prompt
> says so in its own words so it cannot present remembered figures as current
> ones. Until then it is a session that knows the project, asks, plans and
> remembers.

---

## 5. Phase 2 — Connector autonomy (this is what deletes the wizard)

The wizard's steps 1–4 exist because the backend has no way to ask. Give it one.

### 5.1 Read credentials resolve server-side

Today insights takes `refresh_token` / `ga4_refresh_token` / `gsc_refresh_token`
from the browser (`routes/schemas.py`). An agent on a schedule has no browser, and
an autonomous agent that discovers it needs GSC mid-run cannot go back for a token.

Generalize the read side of `service/execution/creds.py` into
`service/connector_access.py`: **project binding → user's encrypted
`connector_credentials` → server env**, identical ladder, membership-gated at every
call site. Reads and writes then resolve credentials the same way, which is also the
only way the two can be reasoned about together.

### 5.2 Three new tools, plain callables with two binders

Per the ports rule, the logic is framework-free and only the binders differ.

| Tool | Returns | Pauses? |
|---|---|---|
| `ListDataSources()` | per connector: bound / stored-but-unbound / available-unconnected, account label, `last_validated_at`, catalog staleness | no |
| `SelectAccount(connector_id)` | the project's bound account, else the caller's accounts to choose from | yes, if ambiguous |
| `RequestConnection(connector_id, reason)` | `{connected, account_id}` or `{skipped}` | yes |

`RequestConnection` is the primitive the brief asks for — *"if not connected, prompt
the user to connect or skip."* Skipping is a first-class answer: the agent proceeds
and the artifact records what it could not see.

### 5.3 Generalize the HITL bridge

`bridge_ask_user_question` hardcodes one event (`QUESTIONS_REQUIRED`) and
`BaseAgentSession.answer_future` is a single slot. Three pause kinds is the second
implementation that justifies the port change (the ports doc's own rule):

```python
bridge_user_input(session, session_id, kind, payload, emit, timeout=…) -> dict
```

with `bridge_ask_user_question` kept as a thin wrapper so audit and content are
untouched. Two new `AgentEvent` members — `CONNECTION_REQUIRED`,
`ACCOUNT_SELECTION_REQUIRED` — appended, never renamed (the enum's contract).
`routes/agents.py`'s messages endpoint learns to resolve them.

### 5.4 Frontend

Render both new events as inline chat cards, reusing `OAuthConnectorCard` — which
commit `21e7537` just consolidated into one card shape. The OAuth round-trip returns
to the session; the pending Future resolves; the run continues. No page transition,
no wizard.

**Exit test:** a project with zero connectors, given *"how is my paid search doing?"*,
walks the user through connecting Google Ads and picking an account **inside the
chat**, then produces a brief.

> **Built 2026-08-31.** `tests/test_connector_access.py` (23 tests) is the gate.
> The wizard's first four steps now have a backend answer. What the build added
> beyond the list above:
>
> - **`service/connectors.py` is self-populating.** Adapter registration was an
>   import side effect, so `CONNECTOR_REGISTRY` was only complete in a process
>   that happened to have imported the right routes — true for the running
>   server, false for an agent tool, a test or a script. `load_connectors()` /
>   `registry()` make it complete for every caller.
> - **`attach_account` writes the row the Connections page would have.** After
>   OAuth there is one account-agnostic credential row; choosing a property
>   upserts an account-specific one carrying the same secret and binds it. The
>   state left behind is indistinguishable from the user having done it by hand,
>   so the two paths cannot drift.
> - **A claimed connection is verified, not believed.** The client only reports
>   that the OAuth tab closed; `RequestConnection` re-reads the database before
>   telling the model it succeeded.
> - **Never ask a question with one possible answer.** A single stored account is
>   bound silently. Being asked to choose from a list of one is how a wizard
>   feels, and re-introducing that would defeat the phase.
>
> Frontend: `insightsEvents.js` (added to the parity gate), `ConnectionRequest`
> and `AccountSelect` cards, `InsightsWorkspace` (chat + stream, reusing
> `SplitWorkspace`, `AuditTodos`, `AuditQuestions`), and the page at
> `/insights/session`. The right pane is a placeholder until the artifact
> contract lands — it says so rather than showing an empty frame.
>
> **The exit test is not fully met, and cannot be until Phase 3.** Everything up
> to "picking an account inside the chat" works; "then produces a brief" needs
> the fetch tools, which are Phase 3. The old wizard is therefore still mounted
> at `/generate` and is still the only path that produces a brief today.

---

## 6. Phase 3 — Data reach, and proving the number

### 6.1 Catalog-driven fetching

Replace the zero-argument pre-bound tools with `FetchData(entity_id, filters, range)`
resolved against `agents/insights/catalog/`. Keep the one genuinely good property of
the current design: **credentials and account identifiers stay closed over at bind
time and are never in the tool schema.** That is what removed the hallucinated-
identifier bug class; do not regress it for the sake of uniformity.

Drop `max_tools=8` and `GOAL_TOOL_ALLOWLIST`. The catalog is the tool surface, and
the model reads it.

Extend catalogs to `gtm` and `stripe` (fetchers exist at `service/stripe/fetch.py`,
`service/google/gtm.py`; neither has a catalog entry).

### 6.2 Knowledge packs become skills

Move `agents/knowledge/*.md` behind `SkillsMiddleware`. Ten packs in the system
prompt is the wrong shape and gets worse with every connector; progressive
disclosure is the right one, and it keeps the cached prefix small — which matters
more here, not less, given the verified caching behaviour.

### 6.3 The verification subagent

This is the part carried over from the Gads retrospective, and it is the product
differentiator rather than a nice-to-have. That engagement's own accounting: **60%
of 93 turns were establishing whether a number could be trusted at all; 16% were
optimization.** Every serious defect found presented as healthy — experiments
"running" with nobody bucketed, tags "firing" that failed at runtime, 23 of 36
"upgrades" from 7 QA accounts.

A `verify` subagent runs before synthesis and emits a `data_integrity` section that
every artifact carries. Ship the checks the connected stack can actually support:

- **Contamination** — internal/QA cluster detection, shared-ad-account tenancy,
  staging hostname leakage.
- **Liveness** — event-volume step changes, conversion-import freshness, key-event
  configuration.
- **Units & semantics** — currency minor units, attribution-window mismatch,
  double-counted conversion actions, API-version drift (the catalog already carries
  `last_audited`).

The section must include **what could not be verified**, not only what failed. A
silent "green" is the exact failure mode this is here to end.

> **Decided: connectors are a separate track.** New connectors (Stripe as a
> first-class insights source, and anything beyond) land on their own schedule, not
> inside this plan. What that requires of Phase 3 is a design constraint, not a
> dependency: **the check library must be connector-agnostic.** A check declares the
> catalog entities it needs and is skipped — visibly, in `data_integrity` — when they
> are absent. Adding a connector then means adding a catalog file and a knowledge
> pack, and the money-truth checks (reconciliation, involuntary churn, decline
> clustering) light up on their own. No check may hardcode a connector id.

### 6.4 Goals demoted

`InsightGenerationGoal` / `OrganicGrowthGoal` stop being required input. A project's
standing objective becomes a **memory entry** the agent recalls and may revise; the
enums survive only to keep saved routines readable.

> **Built 2026-08-31.** `tests/test_insights_data.py` (27 tests) is the gate.
> The agent can now read live data and knows whether to believe it.
>
> - **The catalog is the tool surface.** `FetchData(entity_id, window)` resolves
>   the connector, the account and the credentials server-side;
>   `test_every_catalog_entity_can_actually_be_fetched` fails if a catalog entry
>   has no dispatcher, which is the drift that would otherwise surface as the
>   agent naming an entity and then failing on it. The eight-tool cap and the
>   goal allowlist are gone. Identifiers still never come from the model.
> - **Goals were already demoted in Phase 1** — `InsightsRequest` has no goal
>   field. Nothing further was needed here.
> - **Knowledge packs became a tool, not a skill — a deliberate divergence.**
>   `SkillsMiddleware` requires a `FilesystemBackend`, i.e. a real filesystem
>   rooted on disk, and mounting one would hand the agent's `read_file` a live
>   path into the host. `ReadConnectorNotes` gives the same progressive
>   disclosure (index in the cached prefix, bodies on demand) with no filesystem
>   at all. Revisit if `deepagents` ships a virtual skills backend.
> - **The check library is connector-agnostic, and a test enforces it.** Twelve
>   checks, each declaring the catalog *entities* it needs and never a vendor.
>   Nine run today; the three money-truth checks are declared but unreachable,
>   and `test_a_new_connector_lights_up_its_checks_with_no_code_change` proves
>   they start running the day a billing connector lands. The skipped list is
>   half the output, not a failure report.
> - **A `verify` subagent** runs the checks in its own context — the analyst
>   looks for what matters, the verifier for what is wrong with the data, and
>   mixing the two costs the analyst its window before it writes a word.
>
> **Security finding, fixed.** `deepagents` mounts an `execute` (shell) tool by
> default — present since Phase 1, not introduced here. It was inert, because
> `StateBackend` does not implement `SandboxBackendProtocol`, so the tool
> returned "Execution not available". But *inert because of which backend
> happens to be configured* is not a guarantee: swapping in a sandbox backend
> would have handed this agent a shell silently. The runner now names its
> filesystem tools explicitly, so `execute` never reaches the dispatchable tool
> node. **Phase 1's isolation test asserted the wrong thing** — it checked for
> the name `"Bash"` and passed for the whole of Phase 2 while `execute` sat in
> the tool set. `test_the_agent_has_no_shell` asserts the capability instead.
>
> Frontend: the right pane now lists what was pulled and the window each pull
> covers, driven by one `STEP_FINISHED` per fetch.
>
> Still open: the agent answers in the conversation rather than emitting a
> versioned brief artifact — that is Phase 4, and it is what finally retires
> `/generate`.

---

## 7. Phase 4 — Artifacts, markdown by default

- Add `preferred_artifact_format: "markdown" | "html" | "dashboard"` to
  `agents/preferences.py::UserPreferences`, **default `markdown`**, plumbed into the
  system prompt as a stated preference the agent may override only when the user asks.
- Insights streams `<duct_artifact>`; `ArtifactPersister` versions it — which buys
  the artifacts page, version history, artifact-scoped memory and the AI summary
  digest for free, all of which insights lacks today.
- Content types: `text/markdown` (default), `text/html`, and the existing structured
  insight JSON for the `dashboard` format, which keeps `insight-blocks/` alive as
  *one* renderer rather than the only output.
- Frontend: `SplitWorkspace` — chat left, artifact right. Markdown renderer +
  `InsightDashboard` selected on `content_type`.
- Back-compat: keep reading `duct_local_reports` from localStorage; write nothing new
  there.

> **Built 2026-08-31.** `tests/test_insights_artifacts.py` (23 tests) is the
> gate. The session now produces something that outlives it.
>
> - **`ArtifactPersister` grew an adapter seam — the deferral from Phase 1,
>   paid.** It was audit-shaped: `_persist_report` validated its payload as an
>   `AuditReport` and hardcoded the audit slug, title and filename. It now
>   splits in two — the persister owns *storing* a version (group identity,
>   slug, bytes, activity, summary, findings), an adapter owns *reading* one out
>   of the event a given agent emits. Audit's adapter is the default, so every
>   existing call site is unchanged, and
>   `test_generalising_the_persister_left_audit_where_it_was` pins the slug,
>   filename and content type it produces — a silent rename of everyone's
>   stored reports is the one way this refactor could have gone wrong.
> - **The brief streams; it is not submitted.** It arrives inside
>   `<duct_artifact>`, so the reader watches it being written in the right
>   pane. A submit tool would carry the whole document as one JSON string
>   argument — landing all at once, and losing the lot to a single escaping
>   mistake in a long markdown document.
> - **The price of streaming prose is that the payload has no schema**, so the
>   title travels inside it in a front-matter fence. Nothing trusts the model to
>   comply: a payload with no fence still becomes a brief, with the title taken
>   from the first heading and then from a default. Every parse path degrades
>   rather than raises — losing a brief the model actually wrote is the only
>   outcome `agents/insights/brief.py` exists to prevent.
> - **The content decides the format, never the declaration.** `format:` is
>   recorded as what the model intended and the bytes are believed, because a
>   markdown document served as `text/html` renders as garbage in an iframe and
>   the bytes are the only evidence that cannot be wrong. A disagreement lands
>   in the artifact's `meta` rather than being silently resolved.
> - **The preference is in the user turn, not the system prompt** — a departure
>   from the bullet above, and required: per-user text in the cached prefix
>   gives every customer their own cache. The system prompt carries the
>   *mechanism* (cache-stable, shared); `<deliverable_format>` carries which
>   format this person wants.
>
> **`dashboard` was cut from the format list, deliberately.** The block
> renderers under `app/src/components/insight-blocks/` resolve their rows from
> an assembled source bundle that only the legacy synthesis pipeline produces,
> so an agent-written dashboard artifact today would render mostly-empty
> blocks. It returns with that pipeline in Phase 6, which is where the bundle
> is decided. `preferred_artifact_format` is `markdown | html` until then —
> two formats that work end to end beats three where one is a facade.
>
> Frontend: a Brief/Data tab pair in the right pane, versions accumulating in a
> picker, `MarkdownView` reused from `ArtifactRenderer`, and `lib/brief.js` for
> the streaming half (front matter has to come off before the parsed version
> exists). The format picker is in the profile dialog; `duct_local_insights`
> stays readable and nothing new is written to it.

---

## 8. Phase 5 — Acting, at a configured level of autonomy

### 8.1 The execution tools need a LangChain binder

`agents/tools/execution_tools.py` is `create_sdk_mcp_server`-shaped — Claude SDK
only. V1 needs `build_execution_tools_lc` beside it. Same domain functions, second
binder; this is the ports pattern, and `build_memory_tools_lc` / `_sdk` is the
reference pair to copy.

### 8.2 Three autonomy levels, not two

`models/execution.py` has `manual | assisted`. Extend to a Claude-Code-shaped ladder
that governs **questions, proposals and application** together:

| Level | Clarifying questions | Change sets | Auto-apply |
|---|---|---|---|
| `ask` (default) | freely | proposed | never |
| `assisted` | only when they change the conclusion | proposed | allowlisted, reversible, guardrail-clean (today's behaviour) |
| `auto` | minimal; assumptions recorded in the artifact | proposed | same allowlist — **unchanged** |

The important design point: **`auto` does not widen what may auto-apply.** It reduces
interruption, not oversight. `AUTO_APPLY_ALLOWLIST` and the absolute destructive gate
are untouched, because they are the reason an autonomous agent is safe to ship at all.

Needs: an Alembic migration widening `AUTONOMY_LEVELS`, the picker in
`app/src/app/(app)/execute/page.jsx`, and the level rendered in the session header so
it is never ambiguous which mode a run is in.

### 8.3 Model risk

Autonomy interacts with bring-your-own-model. An autonomous loop with execution tools
driven by a cheap OpenRouter model is a different risk profile from Sonnet.
**Decided:** `auto` is gated behind a model allowlist. The code gates in
`service/execution/policy.py` hold regardless of model — this is about not inviting
the failure, not about relying on the model to avoid it.

> **Built 2026-08-31.** `tests/test_execution_autonomy.py` (33 tests) is the
> gate, and most of it exists to hold one sentence: **`auto` does not widen
> what may auto-apply.**
>
> - **`AUTO_APPLY_ALLOWLIST` and the destructive gate are untouched**, and
>   tested to be identical at `assisted` and at `auto` — including that a
>   destructive op stays ineligible even when its `op_type` is on the
>   allowlist. `should_auto_apply` now takes `level in {assisted, auto}` and
>   nothing else changed in it.
> - **The model gate lowers the posture and touches nothing else.**
>   `effective_autonomy(configured, model)` runs an `auto` project at
>   `assisted` when the model is outside `AUTO_POSTURE_MODEL_PREFIXES` — so it
>   goes back to asking, which is the actual mitigation. A model can lower the
>   posture and never raise it, and `should_auto_apply` deliberately does not
>   take a model argument at all: a test asserts the parameter's absence,
>   because the honest claim is that the code gates hold regardless of who is
>   driving.
> - **No migration was needed, and that is the finding.** The plan called for
>   "an Alembic migration widening `AUTONOMY_LEVELS`" on the assumption of a DB
>   constraint. There is none — `projects.autonomy_level` is free-text with an
>   application-level check — so widening the vocabulary is a code change.
>   `manual` stays an accepted alias for `ask` through `normalize_autonomy`,
>   which every read goes through. Rewriting rows to rename a free-text string
>   is risk for no behaviour change, and on a desktop SQLite install altering
>   `projects` means a table rebuild with live foreign keys pointed at it.
> - **`normalize_autonomy` falls back to `ask`, `is_writable_autonomy` does
>   not.** Reading an unrecognised value as the *least* autonomy is right;
>   writing one silently is not, so a typo is a 422.
> - **`build_execution_tools_lc` came with the extraction the ports rule
>   wanted.** The domain functions moved out of the SDK closures, and both
>   binders now share one set of tool descriptions and arg schemas — so the two
>   harnesses cannot describe different contracts to their models. Tests
>   enumerate the tools from *both* binders (the MCP server is asked, not its
>   source) and assert no name approves or applies anything.
>
> Frontend: `ChangeSetCard` moved out of `AuditChat.jsx` into
> `components/execution/` on its second consumer — two drifting copies of the
> human review gate is the drift most worth preventing. `/execute` gets a
> three-way picker with the invariant stated next to the dial, and the
> insights session header names the level the run is *actually* at, saying so
> when a model stepped it down.

---

## 9. Phase 6 — Delete the old path

- `app/src/app/(app)/generate/page.jsx` (77 KB, ~1,400 lines) deleted; `/generate`
  redirects to the workspace.
- `POST /api/insights/generate` survives as the **non-interactive** entry — scheduled
  briefs and the lead magnet — delegating to the same runner with `interactive=False`,
  where a question that cannot be asked becomes a stated assumption in the artifact.
  This matters: `backend/CLAUDE.md` is explicit that the scheduled brief is the
  product, and it can never block on a human.
- **`agents/insights/v2/` (ADK) stays, frozen.** It is not extended, not ported, and
  not deleted — the standing V2 rule in `backend/CLAUDE.md` applies unchanged. Shared
  changes continue to absorb into V1 and V3 only.

---

## 10. Risks, stated plainly

| Risk | Mitigation |
|---|---|
| `deepagents` 0.x churn, now with two production consumers | exact pin; `test_deepagents_harness.py` as the gate; framework confined to one runner by `test_harness_boundaries.py` |
| Cost and latency per brief rise materially (multi-turn + subagent vs. 1 loop + 1 call) | turn/token budget per session; `verify` subagent on a cheaper model; measure before Phase 6 deletes the fallback |
| Autonomous loop on a weak BYO model | §8.3 model gate; code-level guardrails hold regardless |
| Prompt-cache regression from skills + memory middleware | keep per-project data in the user turn; verify cache-read on the second call as before |
| "Prove the number" over-promises beyond the connected stack | §6.3 — checks declare the catalog entities they need and are visibly skipped without them; connectors land on their own track |
| Six phases is a long time with two insights paths live | Phases 1–2 are independently shippable and already delete the wizard's worst half |

---

## 11. Sequencing

Phases 1 and 2 are the ones that change the product. Everything after is depth.

```
1  session shell            ← insights becomes an agent
2  connector autonomy       ← the wizard dies here
3  data reach + verify      ← the differentiator
4  artifacts / markdown     ← the deliverable
5  execution autonomy       ← acting
6  delete the old path      ← after 1–5 have earned it
```

`agents/insights/v1/agent.py` stays untouched and serving until Phase 6, so there is
no window where insights is broken.
