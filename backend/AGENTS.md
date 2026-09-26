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

- **AI synthesis:** Every agent runs on V1 (LangChain 1.x / `deepagents`) — the only
  engine. Engine selection is still per request, defaulting from the
  `generate_engine` env var, because stored preferences and requests carry the
  string; `resolve_engine` folds any other value back to `v1`.

  **The consolidation is finished.** Per the engine consolidation review
  (duct-cloud, private), every agent moved to one harness — LangChain 1.x /
  `deepagents` — because customers bring their own model (OpenAI / Gemini /
  Claude / xAI / OpenRouter) and the Claude Agent SDK was Anthropic-only by
  design (upstream issue #410, closed `not planned`). Insights
  (`agents/insights/v1/runner.py`) and content (`agents/content/v1/runner.py`)
  are `deepagents` sessions; audit's runner is `create_agent` driven by the same
  shared `DeepSession`.

  **V3 (Claude Agent SDK) was removed** last, because it was the hardest: the
  project-scoped audit ran it unconditionally, and four capabilities existed
  nowhere else. Each was ported first — a chat loop and `run_resume` (both
  DeepSession's, which audit now uses), the project artifact library
  (`agents/core/artifact_tools.py`), and the competitor-research pass
  (`agents/audit/enrichment.py`, now `create_agent` + web tools on any
  provider). Verified live on Gemini and OpenAI against the audit rubric before
  the delete.

  One capability genuinely went with it, deliberately: a Claude *subscription*
  (`sk-ant-oat…`) authenticates only through the CLI, and the Messages API
  rejects it (Anthropic disabled third-party OAuth in Feb 2026). Claude needs an
  ANTHROPIC_API_KEY everywhere now. `agents/content/persistence.py` detects the
  token prefix and says so once rather than failing a call per turn.

  **How content and insights got there**, recorded because the moves are the
  pattern any future port follows. Content V3 was removed once its port landed. What moved, and where it went:
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

  **Images are a second provider inside a content run, and not a fixed one.**
  The conversation runs on whatever key the user brought for chat; the pictures
  run on whatever *image-capable* key they brought — Gemini, OpenAI, xAI or
  OpenRouter, in that order of preference
  (`agents/models.IMAGE_PROVIDER_ORDER`; the gateway is last because a
  first-party key for the same model is one hop fewer). The seam is
  `service/images/`: one request shape, one `ImageAPIError`, one factory
  (`image_client_for`), four backends (`service/google/gemini/client.py`,
  `service/openai/images.py`, `service/xai/images.py`,
  `service/openrouter/images.py`). `routes/content.py`
  resolves the image run once per session (`agents/engines.resolve_image_run`)
  and stashes provider + key on it; the tools spend that or decline, and the
  decline names every provider that would unblock the user. The agent's tool
  schema still defaults to the Gemini model id, so `image_model_for` swaps in
  the resolved provider's default rather than refusing — the agent asked for an
  image, not a Google image. Adding a backend means a client module, an
  `ImageModel` entry whose prefix `provider_of` recognises, a
  `DEFAULT_IMAGE_MODELS` row, and a branch in
  the factory; `/providers/status` and `/models/catalogue` derive the settings
  page's Images row from those same tables, so nothing in the browser lists a
  model.

  **The OpenRouter backend is a short list, not a catalogue.** They front 52
  image models; `ImageModel` names four, because it is a Pydantic enum in the
  content agent's tool schema and opening it to free-form slugs — the way the
  *chat* catalogue deliberately does — would let a run invent a model and fail
  on a slide. Three of the four reach vendors no first-party key here can
  (Seedream, Flux, Recraft, the last emitting SVG); the fourth is the cheap
  Gemini workhorse. Adding one is an enum line plus a `_CAPS` row in
  `service/openrouter/images.py`, and that row is not optional: the four models
  disagree about `resolution`, ratio lists and how many images one call may
  return, so every request is clamped to the table and the clamp is logged
  rather than sent hopefully. The ChatGPT-subscription route (`agents/core/codex.py`) is deliberately
  not an image backend: it can draw through Codex's hosted tool, but OpenAI's
  own docs scope subscription sign-in to Codex products and it is Plus-and-up,
  per-minute-quota'd, and unofficial — the wrong thing to put a customer's slide
  deck on.

  Two consequences, stated rather than discovered later. **Content on Claude now
  needs an API key** — `routes/content.py` refuses the subscription credential with
  the same 402 the browser already handles. And **the model only sees the images it
  generates on Anthropic**: image blocks inside a tool result are accepted there and
  rejected by the OpenAI chat API, so `VISION_PROVIDERS` decides whether the tools
  return pictures or URLs, and the system prompt says which. Where it does see
  them, `SeenImagePruneMiddleware` (`agents/core/lc.py`) swaps the base64 for a
  note after the model call that looked at it: the thread is durable and the
  Postgres saver writes the whole `messages` channel per superstep, so a
  picture left in state would be copied into every later checkpoint.

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

  **A ChatGPT plan is now a live OpenAI credential**, wired where the note above
  said it should be: `agents/core/lc.resolve_chat_model` sends a subscription
  credential to `_ChatOpenAICodex` (`agents/core/codex.py`), so every runner gets
  it. The credential is the *access token* the desktop shell minted — it arrives
  in `X-Provider-OpenAI` beside `X-OpenAI-Account-Id`, `service/auth.py` packs the
  two into one string, and the shape (a JWT, not `sk-…`) is what routes it.
  `ProviderKey.source` is `subscription`; it is the user's own plan, never billed
  to Duct. The refresh token never reaches the backend, `PUT /providers/openai/key`
  refuses to store a token, and background jobs (no request, no header) still
  need an API key. `CHATGPT_AUTH_ENABLED=false` is the kill switch the app reads
  from `/api/providers/status` — the Codex backend is undocumented and the path
  can stop working without notice.

  So a shared change is made once. Claude remains a first-class *model* through
  V1, which is why retiring its SDK cost no model coverage.

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
- **Email:** `service/email/` — one seam (`send_email`) over swappable providers in
  `service/email/providers/`, the only place a mail vendor is named. `EMAIL_PROVIDER`
  picks one; unset takes the first with credentials (Cloudflare, then Resend) and
  falls back to `console`, which logs, so dev/CI/self-host need no vendor account.
  Same shape as the app's analytics seam, for the same reason: a fork swaps one file.
- **Observability:** Sentry error tracking; OpenTelemetry tracing of every
  agent turn, model call and tool call (`agents/core/telemetry.py`), shipped
  over OTLP/HTTP to whatever `OTEL_EXPORTER_OTLP_ENDPOINT` names and off when
  it is unset. Locally that is Phoenix: the "Duct: App + API + Phoenix" and
  "Duct: Desktop + API + Phoenix" launch compounds start it and point the
  API (and, for the desktop one, the sidecar via a second `open --env`) at
  `http://localhost:6006`, and every FetchData and verifier dispatch is a span
  with its own latency. The spans carry `openinference.project.name: duct`, so
  they land in Phoenix's **duct** project instead of in `default` beside every
  other local project's traces; Phoenix creates it on the first span, and any
  other OTLP backend ignores the attribute. Phoenix's own MCP server is
  registered in `.mcp.json`
  at `/mcp` on the same port, so an agent can read the traces of a slow run
  instead of querying the transcript table. Every log line carries a request
  id (`[a1b2c3d4]`, from `X-Request-Id` when the caller sends one, minted
  otherwise, echoed in the response); an agent run logs under the id of the
  request that created its session, so one grep follows one press of Send.
  Each turn ends with a `turn 198.0s: 4 tool calls …` line naming the slowest
  three, which answers "where did the time go" without a SQL script.
- **Hosting:** Railway — auto-deploys from `main` via GitHub integration; `railway.json` defines Railpack build + uvicorn start.
  `railpack.json` sits beside it and configures the **builder**, where
  `railway.json` configures **Railway**. It exists for one line —
  `deploy.aptPackages: ["...", "libexpat1"]` — and every character of it is
  load bearing, including the `"..."`. Railpack builds with a mise-installed
  CPython, then assembles a slim runtime image carrying only the apt packages
  it inferred from the dependency graph (`libpq5`, from psycopg). That
  interpreter is dynamically linked against `libexpat.so.1`; nothing in the
  graph implies it, so without this the ELF loader fails before Python starts
  and **the container dies on its first line**.
  **`"..."` is not decoration.** Railpack arrays *replace* the inferred value
  rather than extend it; `"..."` is its spread syntax. Writing
  `["libexpat1"]` therefore drops `libpq5` and everything else Railpack
  worked out.
- **Runtime commands must name the venv binary, never `poetry run`.**
  `startCommand` and `preDeployCommand` both run in the deploy image, and
  `poetry` is not a real program there — it is a mise shim onto a private
  virtualenv that mise built with the *builder* image's system interpreter.
  Railpack copies `/mise/installs` into the runtime image but the runtime base
  carries no system Python, so that interpreter is a dangling symlink and the
  container dies with `Could not find platform independent libraries` /
  `Failed to import encodings module` before poetry prints a single line.
  Nothing in the message mentions poetry, which is why this cost three weeks
  and two wrong fixes. The app's own `/app/.venv` is unaffected — it was built
  by the mise CPython that *is* copied — so `/app/.venv/bin/uvicorn` and
  `/app/.venv/bin/python` work where `poetry run` cannot. This surfaced when
  Railpack's Debian base moved to trixie (2026-08-16); every backend deploy
  between then and the fix failed identically, and production served a June
  image for three months because a failed deploy leaves the old one running.
  The other trap: the build **succeeds** and the image pushes, so Railway
  reports a failed deployment that looks like a build failure and is not. Read
  the *deploy* logs (`railway logs --deployment <id>`), not the build logs.
  Also check the deployment is not `SKIPPED` — `railway.json`'s
  `build.watchPatterns` gates whether a push builds at all, so a file it does
  not list (this one, once) can leave a fix sitting on `main` doing nothing.
  JSON has no comments, which is why this note lives here.
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
- **The offline suite cannot open a socket.** `conftest.py`'s autouse
  `no_network` fixture raises on `socket.connect` for anything not marked
  `live`, so a test that forgets to fake its transport fails naming the seam it
  forgot rather than passing on the author's machine and nowhere else. It
  blocks loopback too, deliberately: an agent sandbox or a corporate runner
  exports `HTTPS_PROXY=http://localhost:<port>`, so a guard that waves loopback
  through waves the whole internet through, silently, in exactly the
  environments most likely to be holding a key.
- **Fake at the seam the vendor gives you, and put the fake in
  `tests/fakes.py`.** For the sync reporting connectors that is the vendor's own
  `api()` wrapper; for the retry loop underneath them it is `service/rest.py`,
  covered directly by `tests/test_rest_transport.py` because five connectors
  share it and a regression there lands on all of them at once. For Google Ads
  it is `FakeAdsClient`, which keeps the library's local machinery — `get_type`,
  `enums`, `copy_from`, the GAPIC path helpers — and replaces only
  `get_service`. That distinction is the point: a stub made of attribute bags
  passes while the field is misspelled and the enum is not a member, which is
  the whole class of bug worth catching in code that changes what a customer
  spends. Building a real `GoogleAdsClient` refreshes OAuth against Google at
  construction time, so `FakeAdsClient` is also the only offline way into those
  executors at all. GA4 has the same problem for the same reason —
  `discovery.build()` fetches the discovery document before it returns a client
  — and `FakeDiscoveryService` answers the fluent chain by dotted call path
  (`"properties.keyEvents.list"`). The GTM fake in `test_execution_policy.py`
  stays where it is on purpose: it keeps container state so it can answer a read
  that follows a write, which is a different job from replaying canned answers.
- **A fetcher's test fakes the transport, not the client.** The client-level
  fakes above are right for an executor, where the mutation it sends is what
  matters. They never run the code that *builds* a read request, and that is
  where GA4 landing pages were broken for six weeks (`StringFilter` imported
  from the wrong module) with every test green. So each read fetcher has a
  request-shape test one layer down: `FakeWire` replaces `httpx.request`
  beneath `service/rest.py` so a whole Meta, Apple, Stripe or RevenueCat pull
  runs with the vendor's own encoding, headers and pagination real
  (`test_rest_connector_requests.py`); `RecordingHttp` plus
  `discovery_build_offline` let `googleapiclient` build Search Console and the
  GA4 admin API from the discovery document it ships, so method names and
  parameters are validated offline (`test_gsc_fetchers.py`); the GA4 Data API
  test fakes only `BetaAnalyticsDataClient` and lets the real request types
  build the report; and `FakeAdsClient.search_stream` answers the Google Ads
  read fetchers with real `GoogleAdsRow` protos and logs the GAQL in `queries`
  (`test_google_ads_fetchers.py`). When you add a fetcher, add one of these
  with it — assert on the request that would have gone over the wire, then on
  the parsed rows. `test_vendor_contracts.py` covers what none of them can:
  that every lazily imported SDK name and every GAQL field still exists in the
  installed package.

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

### Before adding a table, an event kind or a log

Name which existing store already records it, and propose new storage only
when none does. Four overlap on purpose and each answers one question:

| Question | Store |
|---|---|
| what was said, what did each tool return | `agent_events` |
| who did what to a project, when | `activity_logs` |
| what state is a change in right now | `execution_change_sets` |
| what the agent knows and cannot re-derive | `project_memories` |

The full list, one line per table, is
[`docs/engineering/data-model.md`](../docs/engineering/data-model.md), and
`tests/test_data_model_doc.py` fails when a new table is missing from it.
Why this rule exists: on 2026-09-24 a "decision event" was designed for chat
approve/reject rows while `activity_logs` already recorded every one of them,
with its actor and conversation. The gap was the reader, not the record.

### Database migrations

Schema changes are applied **manually** with Alembic — a normal local dev step,
distinct from an app deploy (the global "deploys go through CI/CD" rule is about
shipping app code, not running migrations). Nothing runs migrations
automatically: `railway.json` only starts uvicorn. CI does *verify* them —
`backend.yml`'s `migrations` job applies the whole chain to an empty
Postgres 16, runs `alembic check` (fails on any model/migration drift, the
diff `--autogenerate` would have written) and undoes the newest one once.
The offline suite runs on SQLite and cannot see any of that;
`make check-migrations` is the same three steps against whatever throwaway
Postgres `DATABASE_URL` names.

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
- `routes/signin.py` — Google sign-in, and the **guest**: `POST /auth/guest`
  mints a real `users` row keyed on an install id so an audit can run before
  anyone signs in; `/auth/guest/link-code` + `?link=` on authorize lets the
  Google callback link the account to that guest or merge the guest into an
  existing one (`service/user_store.py::absorb_guest`, which walks the schema
  for owner columns rather than keeping a list). Never make an owner column
  nullable for this — a guest is why they need not be.
  `?sources=onboarding` on authorize is the **onboarding bundle**: the same
  sign-in also asking for the Search Console and Analytics *read* scopes,
  offline grant, consent forced; the callback stores one
  `connector_credentials` row per scope Google actually granted
  (`service/signin_sources.py`, through the same upsert the Connections page
  uses, `service/connector_store.py`). It exists for exactly one surface —
  the connector prompt on the onboarding audit, for a guest — and every other
  sign-in and every connector flow stays as it was. Never add a write scope to
  the bundle; a connector asks for those itself, with its justification on
  screen (`service/connector_scopes.py`).
- `routes/audit_prefetch.py` — the crawl onboarding starts the moment a URL
  validates (`agents/audit/prefetch.py`): root page now, the rest in the
  background, handed to `run_pipeline` by `crawl_id`. Duct's bandwidth only;
  inference never runs here.
- `agents/audit/draft.py` — the project drafted from the crawl, two layers
  (`crawl` deterministic, `inferred` one structured call), emitted as
  `PROJECT_DRAFT` when a run sets `draft_project`. Never infers the North
  Star; the agent asks for it in chat.
- `agents/engines.resolve_job_run` — provider and model over the keys *this
  caller* can spend, so a user holding only an OpenAI key runs on OpenAI
  instead of a 402 for the instance default. All three agents route through
  it now: audit directly, insights via `agents/insights/setup.resolve_run`
  (which serves both the live session and the scheduled brief), content via
  `routes/content._resolve_run_model`. `resolve_run_model` remains for callers
  that have no job to name.
- `models/settings.py` + `service/profile.py` + `routes/profile.py` — the
  operator profile: name, role, writing preset, the language Duct writes to
  them in, and their own instructions. Same argument as the tier map below,
  applied to voice. Two rules worth knowing: **the server row is the truth and
  the request payload is the fallback** (`resolve`), so a signed-out audit
  still gets the voice picked in the browser; and **the preset derives the
  older `communication_style`/`report_depth` pair** rather than replacing it,
  so every prompt that reads those is unchanged. Rendered for a run by
  `agents/core/voice.user_context_block` into the `<user_context>` block — in
  the USER turn, never the system prompt, because
  `build_insights_system_prompt` is cache-stable and one per-customer string
  in it costs the cached prefix on every call.
- `models/settings.py` + `service/model_settings.py` — the tier map and the
  fallback switch, keyed by user. They used to live in `localStorage` and ride
  on each request, which meant the scheduled brief — the run whose owner is
  definitely not watching — could not read the preference its owner had set.
  The browser's copy is now a cache of this, and on disagreement the server
  wins.
- `agents/core/quota.py` — a 429 the retry loop gave up on, remembered for a
  few minutes so the next run resolves to a tier that can serve. Keyed by
  `(HMAC-SHA256(process salt, key)[:16], provider)` and **never by provider
  alone**: Duct is
  multi-tenant with bring-your-own keys, so one customer's rate limit says
  nothing about another's. In-process and deliberately not durable — a
  cooldown is a hint, and the worst case on a fresh worker is one wasted 429.
  Recorded in `ReportedRetryMiddleware._give_up`, consumed by
  `agents/tiers.resolve_tier_model`'s `cooling` set, reported to the browser
  as `tier_skipped` on `PIPELINE_STARTED`. See
  `docs/engineering/2026-09-08-quota-aware-tier-ladder.md`.
- `POST /api/providers/{id}/verify` — one real completion on the provider's
  Light model, classified into `invalid_key` / `no_billing` / `model_access`
  / `rate_limited` / `unreachable`, or for a ChatGPT credential
  `subscription_quota` / `subscription_revoked` / `subscription_blocked`. The
  only endpoint that can tell a pasted key from a working one.
- The audit agent mounts the insights agent's connector tools
  (`agents/core/connector_tools.py`): `ListDataSources` always, `SelectAccount`
  and `RequestConnection` when the run has a project. The system prompt holds
  the rule (Search Console only, after the report, once); the onboarding
  audit's user turn (`draft_project`) is the trigger, so the cached prefix is
  identical across every other audit.
- `service/discovery.py` — saved TikTok references. `ingest_reference(db,
  project_id, post)` is the one way a `ScrapedPost` becomes a
  `discovered_reference` row (one per post per project); `capture_reference_media`
  copies its cover and slides into project storage and records the outcome in
  `params["media"]`, because TikTok's image URLs carry a signed expiry. The
  Discover save runs capture after the response; `/content/discover/recapture`
  is the backfill, called when Discover opens. A clone-from-URL flow reuses
  both. Every media fetch goes through `service/url_safety.py`: https only, a
  host allowlist (`MEDIA_DOMAINS`), redirects re-checked hop by hop, a size cap
  and an image content type. The URLs arrive in the request body, so without
  that guard a save is a request the caller aims at our network.
- `service/apify/run_cache.py` — an identical Discover search (actor + canonical
  input) inside 30 minutes joins the earlier Apify run instead of paying for a
  new one. In process; the API runs one worker.
- `routes/generate.py` — `POST /api/insights/generate` for interactive brief + LangChain synthesis envelope
- `routes/project_members.py` — project members + email invitations (`docs/engineering/2026-08-16-project-collaboration-plan.md`)
- `service/membership.py` — project access checks (owner vs collaborator) and invite token handling
- `data/google_ads/` — `google-ads-report.json` (demo brief), `raw/demo_raw_payload.json`

## Agent-type architecture

The `agents/` directory is organised by agent type. Each type is independent and has its own goals, tools, prompts, schema, and versioned runners.

```
agents/
├── engines.py          — engine/provider/model registry + resolve_run_model (shared)
├── models.py           — Provider, ModelName enums (shared)
├── core/               — the ports: session registry, events, LangChain adapter (lc.py),
│                         checkpointer, memory/artifact/connector/web tool binders,
│                         the shared DeepSession loop, SDK shims
├── insights/           — Insights agent (paid ads + organic growth intelligence)
│   ├── v1/             — deepagents runner (the only insights engine)
│   └── catalog/, goals/, schema.py, prompts/, subagents/
├── audit/              — SEO audit agent
│   ├── v1/             — create_agent runner (default)
│   ├── crawl.py        — engine-neutral: the session, the crawl, report parsing
│   ├── enrichment.py   — competitor research; create_agent + web tools, any provider
│   └── scoring.py      — the report's scores and counts, computed from its findings on
│                         every submit (both engines); the prompt's tables render from it
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
  checkpointer (audit, the slide-render bridge), the interrupt
  for one with durable threads (insights v1, content v1). Same events, same
  route, and the frontend cannot tell them apart.
- **What the user may watch an agent do is one allowlist, in one place.**
  Every tool call passes through `recorder_tool_hooks`; `agents/core/activity.py`
  wraps that pair and emits `TOOL_ACTIVITY` for the tools it maps — a connector
  pull, a web search, a page read, an image, a sub-agent dispatch — twice per
  call (running, then the verdict), with **structured fields and no prose**, so
  the app writes the sentence in the reader's language. Three rules:
  - **Allowlist, never denylist — and the allowlist is nearly everything.**
    A tool is invisible until someone writes its card, so a new tool leaks
    nothing by default; but the standard is transparency, and the only calls
    left off are the ones with a better row of their own: `RememberFact`
    (the "Remembered" note, with undo), the pause tools (the cards),
    `Create/Update/RewriteArtifact` (the artifact card), `write_todos` (the
    strip), the execution proposal (the change-set card) and the audit's
    report builders (its step ladder). Memory searches and reads, the
    connector listing, opening or listing a document, every read the content
    agent makes of what the project holds, and everything it saves, publishes
    or logs are rows. A new tool goes on the list unless it has one of those
    other rows — say which, in the comment above `ACTIVITY_TOOLS`.
  - **The run's own context is a row too.** `announce_context` records the
    CONTEXT row and emits the "Read project context · business, memory,
    connected sources" notice in one call, so a runner cannot do one without
    the other. Every runner calls it where it composes its opening turn;
    a resume records the row and draws no notice (the reopened transcript
    already has one). Memory's two events are stored as rows as well
    (`EventKind.MEMORY_RECALLED` / `MEMORY_WRITTEN`), so what the run
    recalled and remembered survives a reload for every agent.
  - **No bespoke per-tool step events.** The insights runner used to emit a
    STEP per data pull with an English label built in Python, which the ladder
    and a separate pane both rendered; that is one line said twice and
    untranslatable. Add a mapper, not an event.
  - **Every runner wires the hooks.** `tests/test_tool_activity.py` fails a
    runner that opens a `DeepSession` without `activity_hooks`, because the
    audit runner passed no tool hooks at all for months — recording nothing,
    showing nothing — and nothing failed. The card payload carries the notice
    that a tool ran, never its output: the full input and result are already in
    the transcript, and a card holding fetched page text would put
    attacker-authored bytes in every client's memory.
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
  Both paths — the emergency one and the automatic summariser reported by
  `_dispatch_updates` — put the **summary text** on `context_compacted`
  (`compaction_summary` finds it by the summariser's own `lc_source` tag,
  minus its framing sentence) and the recorder writes it as an
  `EventKind.COMPACTED` row, so the transcript can show what the thread now
  opens with, live and after a reload, instead of an unexplained gap.
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
- `agents/core/turn.py` — **how every agent's user turn is built.** An agent
  declares a `ContextSpec` in `agents/registry.py` (which shared blocks it
  wants); a run renders a `TurnContext`; `build_turn` orders them. A new agent
  that declares nothing gets everything — business context, the operator's
  profile, stored agent context, prior reports, memory, data sources — which is
  the right default, because an extra block costs a few hundred tokens and a
  missing one costs an agent that does not know who it is answering. That was
  not hypothetical: `display_name` reached insights and content and silently
  missed audit for a release, because audit described the operator its own way.

  Two rules this module exists to hold, both enforced by `tests/test_turn.py`:

  - **Per-user and per-project text goes in the USER turn, never the system
    prompt.** The system prompt is the cached prefix; one customer's name in it
    gives every account a prefix of its own and loses the hit on every call of
    every run. The test builds a profile of distinctive strings and fails if
    any of them appear in a system prompt.
  - **`BLOCK_ORDER` is stable-first, volatile-last, and it is a cache decision
    rather than a formatting one.** Inside one session the order is free (turn
    one is the prefix for turn two either way). It pays *across* runs: two
    insights runs on the same project a week apart share a system prompt, and
    if both turns open with byte-identical `<business_context>` and
    `<user_context>` the cached prefix extends past the system prompt into the
    turn. Lead with the memory digest instead and the match ends at the first
    block, because memory moved in between. Do not "tidy" that tuple into
    declaration order.

  An agent with a block of its own may set an unlisted tag — it renders after
  the ordered blocks and before the request. Anything a *second* agent starts
  using belongs in `BLOCK_ORDER`, where its cache position is a decision
  somebody made on purpose.

- `scripts/session_bundle.py` — pull one stored session (the context the
  model read, every tool call with its payload, artifact versions, memories,
  cost) into a folder for review; `make session-bundle ID=<conversation id>`
  or `ID=list`. Read-only, redacts on the way out, and the folder is
  customer data: it goes in the private audit home, never here. The
  `session-audit` skill (`.agents/skills/session-audit/`) is the review
  procedure built on it. The pull is only as good as what the recorder
  wrote: `EventKind.CONTEXT` (one row per `run_session`, written by the
  runner that composed the turn — the insights runner today) holds the
  composed opening turn, its blocks and the system prompt's fingerprint,
  because the USER row is only the sentence the person typed. A runner
  that assembles its own turn and does not record a CONTEXT row cannot be
  audited against what its model saw; give it one before relying on the
  skill for that agent.
- `scripts/session_replay.py` — re-run a bundled session on exactly its
  own data with the current prompt and any model (`make session-replay
  BUNDLE=<dir>`). FetchData is seeded from the bundle and the connectors
  are closed (`replay=` in `build_data_tools_lc`: a pull the original never
  made returns `not_in_replay`), no recorder, no persister, no memory or
  execution tools. It is how a prompt proposal is checked against the run
  that motivated it before it ships, and it spends a real model call.
- `scripts/dump_prompts.py` — **regenerate after any prompt change**
  (`make dump-prompts`). It renders every agent's system prompt and a sample
  assembled turn to [`docs/engineering/agent-prompts.md`](../docs/engineering/agent-prompts.md),
  checked in, so a prompt change lands in the pull request as prose rather than
  as a Python string edit a reviewer has to assemble in their head.
  `prompts.yml` runs the `--check` form on a PR that touched a prompt, and
  `make check-backend` runs it locally.

  We looked at the prompt file formats (Prompty, dotprompt, POML, BAML) and did
  not adopt one. They solve prompts-as-swappable-config, edited outside the
  repository and hot-reloaded without a deploy. Duct's prompts are composed:
  `agents/content/prompts.py` alone has 47 interpolation sites and 22 branches,
  audit assembles its scoring table from `agents/audit/scoring.py` and varies
  its tool guidance on whether the provider does vision. Moving that into
  Handlebars or Jinja moves real logic into a template language with no types
  and no tests. **The reviewability problem was never the storage format** — it
  was that nobody could read the assembled result. That is what the dump fixes.

  The output must stay deterministic: no timestamps, no run ids. A
  non-deterministic byte fails `--check` on every unrelated pull request, and a
  check that cries wolf gets switched off.

- `agents/core/lc.py` — the LangChain adapter every V1 runner shares:
  `resolve_chat_model` (model transport) and `stream_agent` (LangChain stream →
  the `AgentEvent` vocabulary), plus `build_ask_user_tool`, the LangChain half
  of the human-in-the-loop port. Extracted from `agents/audit/v1/runner.py` when
  insights became the second V1 runner. A V1 runner should not talk to
  `init_chat_model` or drive `astream` itself.
- `agents/core/compaction.py` — lossless payload compaction, applied to a
  connector result before it reaches the model. Folds a homogeneous row array
  to typed CSV; **verifies the result structurally and discards a fold that
  lost anything**, because `lossless_only` does not gate every path in the
  library underneath (an array of identical strings is still collapsed). Off
  is not "the model sees everything" — off is the mid-structure cut in
  `agents/insights/data_tools.py`, which on a 900-row pull drops about two
  thirds of the numbers. Absent dependency degrades to plain JSON, so a
  self-host build without the Rust extension still runs. Reached from a
  `UserPreferences` flag (`context_compression`, default on) threaded through
  the runner the same way `artifact_format` is.
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
