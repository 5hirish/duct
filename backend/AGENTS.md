# Duct Backend — agent instructions

Python reporting and synthesis backend for Duct.

## Product role

Per the MVP plan (duct-cloud, private), this backend is the actual product engine:

- read from client-owned destinations with read-only access
- normalize data into typed internal models
- compute signals and comparisons
- synthesize findings into structured output
- deliver via email and alerts

The web app owns HTML rendering. The backend produces JSON payloads only — it does not render HTML.

## MVP architecture

### Current stack

- **AI synthesis:** Insights and content run on V1 (LangChain 1.x / `deepagents`) only.
  Audit carries both V1 and V3 runners and defaults to V1. Engine selection is per
  request, defaulting from the `generate_engine` env var.

  **Consolidating on V1.** Per the engine consolidation review (duct-cloud, private), all
  agents are moving to one harness — LangChain 1.x / `deepagents` — because customers bring
  their own model (OpenAI / Gemini / Claude / xAI / OpenRouter) and the Claude Agent SDK is
  Anthropic-only by design (upstream issue #410, closed `not planned`).
  Each engine has a different status, and they imply different rules:

  - **V1 — the target, and now the only session harness.** Insights
    (`agents/insights/v1/runner.py`) and content (`agents/content/v1/runner.py`) are
    `deepagents` sessions; audit's V1 runner is `create_agent`. New agent work goes here.
  - **V3 — audit only, maintained.** `agents/audit/v3/runner.py` stays reachable via
    `engine: "v3"` and is the one path that can authenticate from a Claude subscription.
    Shared-code changes (`agents/core/`, `agents/audit/`, `schema.py`, `agents/models.py`)
    must keep it at parity; `agents/core/claude_sdk.py` and `pump_stream_event` exist for
    it. Retiring it means Claude requires an ANTHROPIC_API_KEY everywhere — the Messages
    API rejects `sk-ant-oat…` tokens (Anthropic disabled third-party OAuth in Feb 2026).
    Measured cost of that: ~$0.04 per insights synthesis.

    **Content V3 was removed** once the port landed. What moved, and where it went:
    the SDK's `Agent` tool became `deepagents` sub-agents dispatched through `task`
    (`agents/content/subagents/`, now framework-free dicts); the in-process MCP server
    became the LangChain binder `build_content_tools_lc` with the tool bodies
    unchanged; the CLI's `WebSearch` / `WebFetch` became `agents/core/web_tools.py`
    — both as Duct tools, on the rule image generation already set: **a capability
    the running model may not have is a Duct tool, not a provider feature every
    model must support.** The one exception is a built-in that survives a real
    tool-calling loop, and Anthropic's is the only one that does, so it is bound
    there (versioned per model — Opus 5 and Sonnet 5 take `web_search_20260209`,
    the rest the basic variant). Every other provider gets Duct's own `WebSearch`,
    an ordinary function tool over an isolated grounded Gemini call
    (`service/google/gemini/search.py`), because Gemini refuses `google_search`
    alongside function declarations on 2.5 outright and on 3.x without a
    `tool_config` flag that langchain-google-genai drops whenever `tool_choice` is
    set. `tests/test_web_search.py` holds that matrix, measured, as `live` tests;
    `AskUserQuestion` became a checkpointed `interrupt()`, so a question survives a
    redeploy; and the thread is keyed on the conversation, so a resume continues it
    rather than re-priming from the transcript (the DB re-prime remains for
    conversations recorded before the thread was durable).

    Two consequences, stated rather than discovered later. **Content on Claude now
    needs an API key** — `routes/content.py` refuses the subscription credential with
    the same 402 the browser already handles. And **the model only sees the images it
    generates on Anthropic**: image blocks inside a tool result are accepted there and
    rejected by the OpenAI chat API, so `VISION_PROVIDERS` decides whether the tools
    return pictures or URLs, and the system prompt says which.

    **Insights V3 was removed** earlier for a different reason: nothing dispatched it.
    Both live routes (`routes/generate.py`, `routes/agents.py`) drive
    `AutonomousInsightsRunner`, while the V3 runner still claimed parity with the older
    `GenerateInsightsAgent` fetch/synthesize pair — an interface the routes had already
    left behind.

    **`GenerateInsightsAgent` and its tool registry were removed too**, for the third
    time for the same reason: no route dispatched them. With it went
    `agents/insights/tools.py` (per-connector `StructuredTool` factories) and
    `agents/insights/registry.py` (`goal_relevance` scoring that ranked a set of 12
    entities down to 8 — selection pressure that never existed). The autonomous runner
    reaches every entity through `FetchData(entity_id=…)` against the catalog, so the
    catalog's dispatch key was renamed `tool` → `fetch_fn`: it names an internal
    function, and only looked like a tool reference while those tools existed.

    One consequence, deliberately recorded rather than discovered later: **nothing now
    wires a ChatGPT subscription into an insights run.** `should_use_codex` /
    `build_codex_chat` were branched only inside the deleted `agent.py`;
    `agents/core/codex.py` and its tests remain, but no live path calls them. Re-wiring
    that belongs in `agents/core/lc.resolve_chat_model`, where every runner would get it.

  So a shared change may need doing twice (V1 + audit V3), never more.
  Claude remains a first-class *model* through V1, so retiring V3 later costs no capability.

  **Which model, on whose key, is one function.** `agents/engines.resolve_run_model`
  is engine → provider → model → key for every V1 runner — including the rule that a
  lone bring-your-own key chooses its own provider. It lived in
  `agents/insights/setup.py` until content became the second runner that needed it;
  a second copy of that rule is the copy that eventually spends the wrong key.

  **V2 (Google ADK) was removed.** Not on framework merit — ADK is actively developed and
  Google-backed — but because nothing dispatched its runner: `routes/generate.py` had been
  hardcoded to V1, so selecting "v2" in the UI silently served V1 while claiming otherwise.
  Its differentiators (Vertex Agent Engine deploy, `adk web`, native A2A, built-in evals)
  do not intersect this stack, and its weakest axis — provider breadth — is exactly what V1
  exists for. Its defaults were identical to V1's, so `resolve_engine` folding a stored
  `"v2"` back to V1 changed no behaviour. `agents/insights/schema_compat.py` outlived it
  for a while — it was never ADK-specific — but it went with insights V3, its last caller.
  V1 asks the provider for a typed object via `with_structured_output`, so nothing needs
  to parse a synthesis out of raw text any more.
- **Ingestion:** Direct Google API clients (`google-ads`, `google-analytics-data`, `google-api-python-client`). Async concurrent fetching in `service/pipeline.py`.
- **Normalization:** Lightweight Python pipeline — raw API response → typed Pydantic/SQLModel brief models. No query layer or transforms yet.
- **Database:** PostgreSQL on Railway — SQLModel ORM, Alembic migrations, `psycopg` driver.
- **Auth:** JWT for users; Google OAuth for connector linking (Ads, GA4, GSC, Sign-In). Project access is by membership (`project_members`), not by `projects.user_id` — always go through `service/membership.py`.

  **`validate_api_key` is not an authorization boundary.** `DUCT_API_KEY` ships to
  the browser as `NEXT_PUBLIC_DUCT_API_KEY`, so it proves "this is the Duct app"
  and never "this caller owns that row". A router mounted behind it *looks*
  protected and is not. Any endpoint that reads or writes a project-scoped row
  therefore needs `get_current_user` **plus** a membership check on top:

  - a project named in the request → `get_project_for_user`
  - a row addressed by its own id → `get_project_row_for_user`, which reads the
    project off the **row**. An endpoint that takes a row id and trusts a
    `project_id` from the request is letting the caller vouch for themselves.
  - a listing → scope it to the caller (`accessible_projects`), never to an
    unfiltered query parameter.

  404, not 403, for a non-member, so the reply is not an oracle for which ids
  exist. `routes/artifacts.py` is the reference; `routes/content.py` declares
  `get_current_user` **on the router** so endpoint 45 cannot be written without
  it, and `tests/test_content_access.py` asserts that property directly.
- **Email:** `service/email/` — Resend when `RESEND_API_KEY` is set, otherwise a logging console backend so dev/CI need no vendor account.
- **Observability:** Sentry error tracking; optional OpenTelemetry tracing (V1 emits its own GenAI spans, `agents/core/telemetry.py`; audit V3 gets them from the Claude Agent SDK).
- **Hosting:** Railway — auto-deploys from `main` via GitHub integration; `railway.json` defines Railpack build + uvicorn start.
- **CI:** GitHub Actions (`backend.yml`) — Ruff lint + pytest on every PR and push to `main`.
- **Tests:** `make test` must stay offline and under two minutes; it is the
  gate on every merge and the thing an agent runs after every change. Two
  rules keep it that way. A test that needs a provider key, a network, or a
  binary on `PATH` is marked `live` — a `skipif` on the key alone is not a
  gate, because `get_configs()` reads `backend/.env.local`, so a developer with
  a key there fires a paid, minutes-long call from a plain `pytest`. And the
  V1 agent loop is driven by the fakes in `tests/fakes.py` (`ToolCallingFake`
  and its failing variants, `fake_llm`, `tool_names`) plus the `emitted`
  fixture in `conftest.py`: the real harness runs, only the model is canned.
  Assert on events, tool names and payloads, not on prompt prose — a wording
  test fails on every copy edit and catches nothing an eval would not.

### Desktop (local sidecar) mode

The backend runs in two shapes from one codebase. Railway is unchanged; the
desktop build runs the same FastAPI app as a sidecar on the user's machine —
see the engine consolidation review (duct-cloud, private) §7–8.

- **Entrypoint:** `local_server.py`. Sets `DUCT_LOCAL=1`, resolves the per-user
  data dir, binds **127.0.0.1** on an OS-assigned port, and prints a single JSON
  handshake line on stdout before starting uvicorn:
  `{"duct_sidecar":1,"url":...,"port":...,"api_key":...,"data_dir":...}`.
  The Tauri shell must read the port from that line — never assume one.
- **Data dir** (`utils/appdirs.py`): macOS `~/Library/Application Support/ai.getduct.desktop`,
  Windows `%APPDATA%\Duct`, Linux `$XDG_DATA_HOME/duct`. Created `0700`.
  Override with `--data-dir` or `DUCT_DATA_DIR`.
- **Local mode defaults** (`Configs._apply_local_mode_defaults`): SQLite at
  `<data_dir>/duct.db`, uploads at `<data_dir>/uploads`, `init_db_on_startup=True`
  (no Alembic on a laptop). Each is only filled when unset, so
  `DATABASE_URL=postgresql://…` still works for a developer running local mode.
- **Local API key:** generated once, persisted `0600` at `<data_dir>/local-api-key`,
  and exported as `DUCT_API_KEY` so the existing `validate_api_key` gate applies
  unchanged. It only stops other local processes driving the sidecar.
- **JSON columns must use `models/columns.py::json_column()`**, never
  `postgresql.JSONB` directly — raw JSONB fails to compile on SQLite. The variant
  still renders JSONB on Postgres, so it produces no Alembic diff.
- **Never name a module `models/types.py`** — it shadows the stdlib `types`.

### Database migrations

Schema changes are applied **manually** with Alembic — a normal local dev step,
distinct from an app deploy (the global "deploys go through CI/CD" rule is about
shipping app code, not running migrations). Nothing runs migrations
automatically: `railway.json` only starts uvicorn and there is no CI migration job.

- Apply: from `backend/`, run `alembic upgrade head`. The DB URL resolves from
  `backend/.env.local` (the Railway TCP proxy) via `config.get_configs()`.
- Inspect: `alembic current`, `alembic heads`, `alembic history`.
- The proxy host is not resolvable inside the command sandbox, so migration
  commands run with the sandbox disabled — they need outbound network to the
  managed database's proxy domain.
- New models must be imported in `models/__init__.py` so `SQLModel.metadata`
  picks them up for autogenerate.
- Migrations should be additive/reversible — always provide a working `downgrade`.

### Roadmap (not in codebase yet)

- **Ingestion framework:** PyAirbyte for early pilots → client-managed Airbyte later
- **Query layer:** DuckDB + Ibis
- **Transforms:** dbt
- **Orchestration:** Dagster
- **Delivery:** Resend (email) + Slack webhooks

## Product-shape constraints

- Do not build a dashboard-first product here.
- The primary value is the brief and alert output.
- The backend should support a thin onboarding app, not depend on a rich frontend.
- Design all outputs for operator clarity: what changed, why it matters, what to do next.

## Current directory structure

- `service/google/brief.py` — Google Ads brief normalization (loads demo from `data/<connector_id>/`, default `google_ads`)
- `service/google/schema.py` — typed Google Ads brief payload (dataclasses / JSON contract)
- `agents/insights/prompts.py` — synthesis system + user prompts (e.g. Google Ads weekly insight brief)
- `routes/auth.py` — OAuth by connector (`/auth/connectors/{connector_id}/oauth/...`)
- `routes/generate.py` — `POST /api/insights/generate` for interactive brief + LangChain synthesis envelope
- `routes/project_members.py` — project members + email invitations (`docs/engineering/project-collaboration-plan.md`)
- `service/membership.py` — project access checks (owner vs collaborator) and invite token handling
- `data/google_ads/` — `google-ads-report.json` (demo brief), `raw/demo_raw_payload.json`

## Agent-type architecture

The `agents/` directory is organised by agent type. Each type is independent and has its own goals, tools, prompts, schema, and versioned runners.

```
agents/
├── engines.py          — engine/provider/model registry + resolve_run_model (shared)
├── models.py           — Provider, ModelName enums (shared)
├── core/               — the ports: session registry, events, LangChain adapter (lc.py),
│                         checkpointer, memory/connector/web tool binders, SDK shims
├── insights/           — Insights agent (paid ads + organic growth intelligence)
│   ├── v1/             — deepagents runner (the only insights engine)
│   └── catalog/, goals/, schema.py, prompts/, subagents/
├── audit/              — SEO audit agent
│   ├── v1/             — create_agent runner (default)
│   └── v3/             — Claude Agent SDK runner (`engine: "v3"`)
└── content/            — Content Studio (plans, posts, images, publishing)
    ├── v1/             — deepagents runner (the only content engine)
    └── tools.py, subagents/, prompts.py, schema.py, artifacts.py, enrichment.py
```

Route convention: each agent type gets its own route prefix, and every agent's
session lifecycle runs through the unified `routes/agents.py`:
- `POST /api/agents/{type}/sessions` → stream → messages — every session
- `POST /api/insights/generate` — the unattended brief
- `POST /api/audit/run` — the audit pipeline
- `/api/content/*` — content CRUD, brand context, the slide-render bridge; the
  legacy `plan/stream` and `post/stream` entry points drive the same runner

Cross-agent invocations are modelled at the frontend level (e.g. audit findings carry an `invoke_insights` action that pre-populates the insights wizard). Backend agents remain decoupled — no direct calls between agent types.

## Agent ports — the harness boundary

We rent an agent harness; we do not marry one. The full declaration (with the
port table and the external standard behind each) lives in
`agents/core/ports/__init__.py` — read it before adding anything that touches a
framework. The rules it implies:

- **Never write an `AgentHarness` interface.** Harnesses differ in capability,
  not just API shape; the intersection loses the reason to use one and the
  union means maintaining a framework. The harness stays harness-shaped inside
  a runner, and only its *boundary* is standardized.
- **Domain code imports no framework.** Tool bodies, prompts, schemas, goals and
  scoring are plain Python. `agents/core/memory_tools.py` is the reference
  shape: `_remember_sync` / `_search_sync` / `_get_sync` hold the logic, and
  `build_memory_tools_lc` / `build_memory_tools_sdk` are thin binders.
- **Framework imports live only in adapters** — runners, binders, and the
  named shims. `tests/test_harness_boundaries.py` enforces this and lists the
  allowlist; adding a file to that list is a deliberate act, not a fix for a
  failing test.
- **Write the adapter on the second implementation, not the first.** One
  implementation is a guess. The human-in-the-loop port is the worked
  example: `PauseFn` in `agents/core/session.py` was declared only once the
  LangGraph `interrupt()` implementation (`agents/core/lc.interrupt_pause`)
  existed beside the Future bridge. A tool body takes a `PauseFn`; the binder
  that mounts it decides which one — the Future for an agent with no
  checkpointer (audit v1, audit v3, the slide-render bridge), the interrupt
  for one with durable threads (insights v1, content v1). Same events, same
  route, and the frontend cannot tell them apart.
- **A durable thread is the conversation.** The insights runner keys its
  LangGraph thread on the conversation id, so a resumed session continues the
  thread — and a pause the thread is parked on comes back as the same SSE
  event, flagged `replay`, when a session resumes it. Never key a thread on
  a session id; that made "resume" a transcript the agent could not see.
- **A failure is a code before it is a message.** `agents/core/errors.py`
  classifies an exception once (`classify_error`), and that code decides the
  retry (`is_retryable`), rides on the failure event (`error_payload`), and
  picks the copy in the browser. Never emit `str(exc)` to a client, and never
  add a regex on message text in the frontend — add a code, or a class name to
  the classifier's table.
- **Input during a turn is steered or queued, never refused.** A harness that
  can hand the model a message at its next call sets `steer_queue` on its
  session (insights does, via `SteerMiddleware`); the rest fall back to
  `chat_queue`. The route decides; the runner reports `user_input_consumed`
  when it dequeues so the client can drop the "queued" mark. Do not reintroduce
  the 409.
- **Run status is derived from the stream, in one place.** `ConversationRecorder`
  (`agents/content/persistence.py`) already sees every event, so it is what
  writes `agent_conversations.run_status` (`RunStatus` in
  `agents/core/events.py`: idle / running / paused / failed / cancelled) and
  `run_error`, and appends a `failure` event where a turn died. The list and
  state routes carry both; a reload shows the failure where it happened, with
  the same code. Do not set the status from a runner — a second writer is how
  two agents end up disagreeing about one column. A session closed mid-turn is
  recorded as `cancelled` by `recorder.close()` in `_close_and_consolidate`.
- **A retry says how long, and the provider's `Retry-After` wins.**
  `MODEL_RETRYING` carries `retry_in` (seconds, a duration — the client anchors
  it to its own clock so skew cannot show a countdown already over), computed by
  `retry_delay(attempt, exc)`, which reads `retry_after_seconds(exc)` from
  `agents/core/errors.py` before falling back to the jittered schedule. A
  provider asking for longer than `MODEL_RETRY_HEADER_MAX_DELAY` is not
  retried at all — the failure, with its code, is more useful now than after
  a countdown that fails anyway. The summariser's calls are billed with
  `scope: compaction`, so they count toward the total and never drive the
  gauge.
- **A request too long gets one compaction and one retry.** The automatic
  summariser works from an estimate and the provider counts for real; when
  they disagree the request comes back as `context_window`. The insights
  runner then calls `compact_thread` (`agents/core/lc.py`) — LangChain's own
  `SummarizationMiddleware` forced by a one-message trigger, keeping the last
  `COMPACT_KEEP_TOKENS`, written back "as" the tools node so the graph's next
  step is the request that failed — emits `context_compacting` /
  `context_compacted`, and continues from the checkpoint. A second overflow is
  the ordinary failure. deepagents' own summarisation event is cleared in the
  same write: it indexes into the message list the rewrite just replaced.
- **A model has a price or it has no cost.** `PRICING` in `agents/models.py`
  mirrors `CONTEXT_WINDOW` (a test holds them equal) and `cost_usd()` prices a
  call from LangChain's usage, taking cached tokens out of the input figure.
  `TOKEN_USAGE` and the state route carry `cost_usd`, `None` when unpriced —
  never a guess, because on BYO keys the figure is what the user pays.
- **Read the harnesses built in the open before designing a lifecycle
  feature.** [`docs/engineering/agent-harness-references.md`](../docs/engineering/agent-harness-references.md)
  is the watch-list — Codex, OpenCode, pi — with the revision each was last
  read at, findings pinned to `file:line`, and the gaps they expose in ours,
  sized. Pauses that survive a reconnect, typed error codes, steer-versus-queue
  input and visible compaction all have a worked answer there. Refresh the
  table when you read one.
- **Pick the lowest rung that works.** LangChain 1.x is layered, and the layers
  carry different stability guarantees: `init_chat_model` and `create_agent` are
  on the semver-stable 1.x LTS surface (no breaking changes until 2.0), while
  `deepagents` is 0.x with no stability policy and a weekly cadence. Reaching for
  `deepagents` where `create_agent` suffices buys churn for nothing.

  The rung is a property of the agent, not of the agent *type*, and it can move
  when the agent's job does. The autonomous insights session
  (`agents/insights/v1/runner.py`) is on `deepagents` because it needs four
  things `create_agent` lacks — a planning loop, subagents, skills, and the
  `interrupt_on` upgrade path — and the phase plan spends all four. The content
  session (`agents/content/v1/runner.py`) spends three of them from its first
  turn: `write_todos` is the checklist the workspace renders, `research_pillar`
  and `draft_post` are sub-agents, and the virtual scratch space holds drafts.
  Audit's V1 runner is still `create_agent`, and content's enrichment pass
  (`agents/content/enrichment.py`) is one too — search, fetch, structured
  answer, no planning.

  Three consumers of the 0.x pin now, so `tests/test_deepagents_harness.py`
  matters more, not less: run it before moving the pin. `tests/test_content_v1_runner.py`
  pins the content contract the same way `tests/test_insights_session.py` pins insights.
- **`deepagents` is pinned exactly**, not with a caret — it changes behaviour in
  minors (task planning became opt-in in 0.7). `tests/test_deepagents_harness.py`
  is the upgrade gate; run it before moving the pin.

## Artifact contract

The app lists top-level `*.json` briefs in `data/google_ads/` (e.g. `google-ads-report.json`) for local dev; user-generated insights are returned from `POST /api/insights/generate` and stored client-side (`localStorage`).

The JSON contract:
- `source_metadata.theme` — theme key (`paid_ads`, `product_intelligence`, `organic_growth`); the app resolves accent colors from this
- `source_metadata.generated_at` — ISO 8601 timestamp
- All other fields follow the typed models in `service/google/schema.py`

Do not write HTML from the backend. Do not reference `themes.json` or HTML templates — those have moved to the app.

## Code design rules

- Normalize first, synthesize second.
- Keep typed schemas central and explicit.
- The backend is a data pipeline, not a renderer. Output JSON; let the app handle presentation.
- Separate ingestion, normalization, synthesis, and delivery concerns.
- Prefer extensible evidence models so future tools can enrich the same findings.

### Shared helpers — check here before writing a local copy

Each of these replaced a family of divergent duplicates (23 private
`_utcnow()` definitions, five hand-rolled retry loops). A new local copy
re-opens that drift, so reach for these first and extend them when they
don't fit.

- `utils/dates.py` — `utcnow()`, `now_iso()`, `parse_iso()`, `last_n_days()`.
  **Never `datetime.now()` or `datetime.utcnow()`**: every persisted timestamp
  is UTC-aware, and naive ones compare and serialise inconsistently across
  SQLite (desktop) and Postgres (Railway). Stdlib-only leaf module, so
  `models/` can use `default_factory=utcnow` without an import cycle.
- `utils/strings.py` — `slugify()`, `titleize()`.
- `utils/formatting.py` — `money()`, `number()`, `percent()`, `multiplier()`,
  `safe_divide()`.
- `service/memory.py` — agent memory (`project_memories`): `remember()` is the
  ONLY write path (it redacts secrets, dedupes, honours the pause switch, and
  closes the previous value of a state key), `search()` is the only read path
  (Postgres FTS, SQLite LIKE), and `build_memory_context()` assembles the prompt
  blocks. Never write the table directly and never re-render the digest locally
  — the supersession and never-raise contracts live in that module.
  `service/memory_consolidation.py` owns the post-session extraction pass; its
  model output is a proposal that still goes through `remember()`. Tools for
  both harnesses are in `agents/core/memory_tools.py` and the shared prompt
  stanza is `agents/core/prompts.py::MEMORY_DISCIPLINE`. Per-project memory goes
  in the USER message, never the system prompt.
  `search(time_aware=True, rank=True)` is the question-shaped read — it reads a
  date range out of the words, treats a named kind as a filter, matches on ANY
  term and then tightens (all terms → two → one), and ranks by relevance +
  recency + importance + recall. Leave both off for a filter form like the
  timeline, whose inputs are the user's explicit instructions. Retrieval makes
  no model calls, by design. `tests/eval/memory_recall.py` holds the 50-question
  set (`pytest tests/test_memory_retrieval.py -s` prints the per-axis report);
  it exists because it caught the AND-everything query bug that made questions
  retrieve nothing, so extend it before tuning retrieval by feel.
- `agents/core/lc.py` — the LangChain adapter every V1 runner shares:
  `resolve_chat_model` (model transport) and `stream_agent` (LangChain stream →
  the `AgentEvent` vocabulary), plus `build_ask_user_tool`, the LangChain half
  of the human-in-the-loop port. Extracted from `agents/audit/v1/runner.py` when
  insights became the second V1 runner. A V1 runner should not talk to
  `init_chat_model` or drive `astream` itself.
- `service/artifact_store.py` — versioned artifact persistence. `ArtifactPersister`
  wraps a runner's emit and stores every `ARTIFACT_VERSION` event; an **adapter**
  (`ArtifactVersion` + a `Callable[[dict], ArtifactVersion]`) reads one version out
  of whatever payload that agent emits. A new agent writes an adapter — audit's
  validates an `AuditReport`, insights' reads a written brief — and never a second
  persistence path. Storing is the store's job; understanding the payload is the
  adapter's.
- `agents/tools/execution_tools.py` — the staged-execution tool surface, as a
  binder pair (`build_execution_tools_lc` / `build_execution_mcp_server`) over
  shared descriptions, arg schemas and domain functions. The surface is
  deliberately asymmetric: propose, inspect and roll back exist; **approve and
  apply do not, in either harness.** Autonomy (`ask | assisted | auto`) changes
  how often an agent interrupts, never what may auto-apply — `service/execution/
  policy.py` is the one place that decides, and it does not consult the model.
- `service/connectors.py` — the registry and the adapter contract. A
  `list_accounts` row has a canonical half the browser reads and a native half
  it never does: `account_id` / `account_name` name the thing being **picked**
  (the GA4 property, the GTM container — not its parent account, which several
  rows share), and the optional `entity_url` / `entity_detail` / `entity_meta`
  (built with `entity_facts`) are what the picker renders as a favicon, a
  disambiguating line and short chips. Vocabulary is server-side too
  (`ConnectorMeta.entity_noun`), so adding a connector stays one registration
  rather than a registration plus an edit to a table in the frontend.
- `service/rest.py` — sync HTTP transport for the reporting connectors:
  retry, backoff, rate-limit pacing, error typing. A new connector declares
  an `Endpoint` and an `ApiError` subclass and writes no transport code;
  auth headers, query encoding and pagination stay vendor-side. Not for
  `service/apify` or `service/post_bridge` — those are async, hold a
  long-lived client, and need no retry.

## Sequencing rules from the plans

- Validate the brief/report shape before building heavy automation.
- Start with one customer, one tool, one brief/report end-to-end.
- Add connectors and orchestration only after the output format is useful.
- Add real-time anomaly detection after the scheduled brief flow works.

## What not to build yet

- no custom auth in backend
- no full Airbyte platform management
- no heavyweight job system beyond the planned orchestration layer
- no broad dashboard experience
- no complex cross-tool logic before the single-source MVP is producing useful output

## Configuration

`config.py` is the source of truth for what the backend reads; `.env.example`
is its documentation, and `tests/test_env_example.py` keeps the two honest.

The reason that test exists is worth knowing before adding a setting: **every
field in `Configs` has a default.** A missing variable therefore never fails —
the feature it powers silently does nothing. That makes an undocumented setting
undiscoverable rather than broken, which is how `.env.example` drifted to
covering about a third of what a running instance sets.

So when you add a setting:

- If it is a credential (matches `api_key|_secret|_token|_dsn|password|client_id|encryption_key|jwt_secret`),
  the test **requires** it in `.env.example`. That is not bureaucracy; it is the
  only signal a new contributor gets.
- If it is read from `os.environ` directly rather than through `Configs`, add it
  to `NOT_CONFIG_FIELDS` in that test with the reason. A bare exemption is a
  hole in the check.
- Renaming a field means renaming it in `.env.example` too — the stale check
  catches it, because a wrong example is worse than a missing one.

Names are shared across processes deliberately. `SENTRY_DSN` is read by this
backend, by the desktop sidecar (only on user consent), and compiled into the
Tauri shell via `option_env!`; `GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET` likewise.
One value in `.env.local` serves all of them — do not invent a `DUCT_`-prefixed
variant for the desktop half.

### Creating a migration

Always create Alembic revisions with autogenerate — `alembic revision
--autogenerate -m "..."` or `python scripts/migrations.py revision ...`. Do not
hand-write a revision file. Autogenerate diffs the models against the live
schema, which is the step that catches a column you added to a model and forgot
to migrate; a hand-written revision cannot notice what you did not think of.
Review the generated file before applying it — autogenerate is a good first
draft and a poor final one, especially for renames and server defaults.
