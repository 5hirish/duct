# The test suite, for fast iterative development

**Author:** Shirish Kadam · **Date:** 2026-09-14

The agents' lifecycles are mock-tested well: open, prompts, tools, pauses, steer, resume, compaction, artifacts, memory and close all have named tests against a scripted model. The connectors are not: the fakes sit one layer above the vendor SDK, so the code that builds the real request is the least covered code in the tree, which is exactly where the GA4 bug lived for its whole life. The suite is hermetic and under a minute; the real gaps are what it cannot see, not how long it takes.

2026-09-14 · measured at eeb7b3e: 1,618 offline backend tests in 58 s, 161 app tests, 1 desktop Rust test; `coverage run --source=agents,routes,service,utils` = 67% of 19,922 statements · backend CI ≈ 2 min 10 s, app CI ≈ 1 min

## 01 · Short answer

- **Agents: good.** Each of the three runners has a lifecycle test file driven by `fakes.ToolCallingFake`, a scripted model that can call tools, raise, rate-limit and overflow. Insights alone has 54 tests naming the stages: prompt cache stability, user-turn blocks, mounted tools per session shape, opening turn then chat loop, pause then answer then resume, steer mid-turn, compaction once then fail, retry countdown, artifact versioning across resumes, verifier tier, autonomy restated. Content and audit have the same shape at 19 and 17. Memory has 80 tests across write, supersession, digest, retrieval ranking, consolidation and the routes.
- **Connectors: thin where it matters.** Parsing and money rules are tested (31 client tests across Apple, Meta, Stripe, RevenueCat, OpenAI; 22 for Mixpanel, Clarity, GrowthBook). The request-building code is not: GSC 27%, Google Ads fetch 38%, GA4 43%, the Google brief pipeline 16 to 18%, Meta fetch 18%, RevenueCat fetch 28%, HubSpot and Apify 0%. Every caller fakes the client one layer up, so a vendor rename or a wrong import inside the fetcher is invisible until a session hits it. Nothing runs against a real account anywhere: the `live` marker covers audit, content, model transport and web search, never a connector.
- **Speed and stability: good.** Hermetic by construction (an autouse socket guard), 58 s locally, two minutes in CI, no order dependence beyond the known migration walk-back. Two new contract tests (§06) are 13 s of the 58, and that is the price of importing the SDKs nobody else imports.
- **The app is a reducer with tests and a UI without them.** 552 lines of reducer fixtures for the session state machine, 14 lib test files, zero component tests, and the smoke script that drives the three workspaces against the fixture mock is deliberately not in CI. The backend-to-app event contract is asserted on the backend side only, against string literals, and one fixture already carries a memory kind the backend does not have.

## 02 · Agent lifecycle, stage by stage

What a mock test exists for, per runner. "Insights" is the deepagents session runner; "Content" and "Audit" share the same `DeepSession` core. Test names are the actual functions, abbreviated.

| Stage | Insights | Content | Audit | Shared core |
| --- | --- | --- | --- | --- |
| Request shape | project + sentence is complete; unknown fields rejected; wizard body rejected | no session means no tools and no questions | every route builds the one runner; project scope from the session not the caller | — |
| System prompt | byte-identical across sessions; describes mounted tools; carries catalog + notes index | — | — | xml_block; business-context rendering |
| User turn | per-project blocks; `<data_sources>`; empty prompt becomes an opening instruction; format preference steers the user turn, never the system prompt | pre-checkpoint resume primes the first message | — | — |
| Tools mounted | virtual FS not disk; planning; memory needs a project; unremembered gets none; connector discovery; pause tools need session + project; signed-out gets no connector tools | orchestrator gets every tool; sub-agents never get writer tools; web search rides only on a verified provider; vision follows provider | ask-user only with a session; caps questions; timeout tells the model to continue | planning + virtual FS + no shell; fallback chain one same-provider step |
| Data fetch | every catalog entity fetchable; provider error tells the agent not to retry; unbound connector names the fixing tool; compaction keeps every quotable number | — | crawl then publish; unreachable site closes the step, never reaches the model | — |
| Pause / answer | question parks, answer resumes; answer without id takes the only pending; chat while parked is steered; account pick and connect offers (23 tests in connector_access) | question parks the thread, answer resumes | ask-user emits and waits | — |
| Steer mid-turn | reaches the model at its next call; route steers while running, queues otherwise; steered text not echoed as the agent | chat turn releases the queued row | follow-up on the same thread | steer middleware hands the model what arrived |
| Failure / retry | failed turn does not end the session; transient retried and reported; Retry-After sets the countdown; capped; rejected key fails on first attempt | failed chat turn is a row | — | error classification (13), quota cooldown per key (17) |
| Compaction | request-too-long compacted once and retried; second overflow is the ordinary failure; prune trigger below the summarisation floor | prunes only where it sees pictures | — | compaction reported, survivors not replayed; pruning is not a compaction |
| Artifacts | closing tag publishes a version; not also chat prose; second brief is v2; resumed session continues numbering; persists as readable markdown | plan artifact becomes the preview event; post artifact routes to the post event | each published report is a new numbered version | artifact tools (11) |
| Memory | tools need a project; unremembered session gets none | same | — | 80 tests: write, redact, supersede, digest, ranking, consolidation, pause, export, reset |
| Resume | parked conversation shows the pause again; thread is the conversation not the session; thread state reports parked | idle resume is silent and ready | resume continues without crawling again | checkpointer: thread outlives saver; no bleed; fallback saver |
| Usage / gauge | token usage reaches stream + thread state | — | — | billed once at stop marker; summariser billed but not gauged; cache rate priced |
| Close / consolidate | — | — | — | consolidation runs once per watermark; skipped for short and paused; unremembered not consolidated |
| Unattended run | cannot ask a question; run_once returns the brief; wrote nothing says so | — | — | — |

**Verdict.** good This is the right shape: behaviour tests against a scripted model, named after the promise they hold, no prompt-wording assertions (deliberately cut; see the trim rules in `backend/AGENTS.md`). Three thin spots inside an otherwise strong table: `routes/agents.py` is 45% covered for 712 statements, and it is where session creation, steer, answer, grace-close and consolidation scheduling live; `agents/content/tools.py` is 24% of 930; the insights goal packs are 57% and the legacy wizard prompts 14% (dead weight or untested, and the suite cannot tell which).

## 03 · Connectors: where the fake sits decides what a test can see

Every connector test fakes at the same layer: the vendor client (`FakeAdsClient`, `FakeDiscoveryService`, HTTP transports replaced by a canned response). That is the right layer for money rules and pagination, and it is why 31 client tests catch real things (Meta minor units, Stripe zero-decimal currencies, RevenueCat public-key rejection). It cannot see the code between the fake and the wire: the function that imports the SDK's types and builds the request. The GA4 fetcher imported `StringFilter` from a module that nests it under `Filter`, and no test executed that line because the client it would have been passed to was already faked.

| Connector | Request-building module | Coverage | What is tested | What is not |
| --- | --- | --- | --- | --- |
| GA4 | `service/google/ga4.py` | 43% | landing pages request (added 09-13, after the bug); key-event and audience executors (23) | conversion paths; property listing |
| Search Console | `service/google/gsc.py` | 27% | account resolution helpers | both report requests, site listing |
| Google Ads read | `service/google/ads.py`, `fetch.py` | 38% / 16% | executors (26) against real protos; GAQL fields (new, §06) | the report fetchers themselves; the legacy brief pipeline (18%) |
| Meta Ads | `service/meta/ads/fetch.py` | 18% | units, purchase attribution, error branching, cursoring | the fetch orchestration |
| Mixpanel / Clarity / GrowthBook | `service/*/fetch.py` | 78% / 78% / 82% | request shape, exclusions, clamps, 429 handling, executors | — |
| Stripe / Apple / RevenueCat | `service/*/fetch.py` | 55% / 31% / 28% | money and status rules | fetch orchestration; Apple JWT client (40%) |
| HubSpot / Apify | — | 0% | nothing | everything |
| PostBridge | `service/post_bridge/client.py` | 73% | upload flow, analytics chain, 429, bearer scope | — |

Two more facts belong here. **No connector has a live test.** The `live` marker exists and CI has a manual workflow for it, but it is used for the model transport, the audit and the content post, never for a data source; a connector that Google or Meta changes under us is discovered by a user. And **the Google OAuth split is untested**: a refresh token is bound to the client that minted it, the desktop sidecar mints with one client and the hosted API refreshes with another, and nothing in the suite models two clients (found live on 09-14).

## 04 · Speed and stability

| Property | State | Verdict |
| --- | --- | --- |
| Hermetic | autouse `no_network` socket guard; SQLite engine per test; env cleared by `clean_env`; `live` deselected by default so an exported key cannot fire a paid call. One leak worth knowing: some paths still read `.env.local` and log a failed connection to the Railway proxy during the run. The guard stops them, the warnings are noise | good |
| Wall clock | 58 s locally (1,618 tests), CI 2 min 10 s including install; app CI about 1 min. A contended laptop (a PyInstaller freeze in the background) stretches this tenfold and makes 5 s tests look like a minute; measure idle before believing a slow test | good |
| Slow tail | the two contract tests (8.1 s + 4.9 s, first import of the GA4, GenAI and Ads SDKs); the Ads negatives preview (4.8 s, same proto import when it runs first); two audit runner tests at 2 s. Everything else is under a second | acceptable |
| Order dependence | one known: the desktop migration walk-back needs a line per migration and fails only in some collection orders (noted 09-08). Not seen in this run | watch |
| Flakiness sources | 20 real `sleep` calls in tests; the SSE smoke is kept out of CI for exactly this reason | contained |
| Postgres paths | every test runs on SQLite; the FTS search, JSON columns and the checkpointer's Postgres branch are exercised only by a running server. The sidecar-on-SQLite schema divergence found on 09-02 is the same blind spot from the other side | gap |
| Schema drift | no autogenerate-is-empty test; the checkpointer test pins the LangGraph table list by hand | gap |
| Dependency bumps | dependabot merges landed green because nothing exercised the vendor surface (google-ads 31 to 32 merged 09-14 with the same fake-client tests) | was blind → §06 |

## 05 · App, desktop, contracts

- **App reducer:** `agentSession.test.js` (552 lines) is the regression gate for the session state machine and the three JSON fixtures replay through `mock-agent-backend.mjs`. Good, and fast.
- **App components:** zero `.test.jsx`. Every workspace, card and composer is verified by eye through `/preview`. The parity scripts (`check-*.mjs`) are pure-rule guards and do run in CI since 09-04.
- **Backend to app contract:** `test_event_values_and_aliases_match_frontend_contract` asserts backend string literals against themselves; it never opens `app/src/lib/agentEvents.js`. The fixture `insights-pause.json` carries `"kind": "target"`, which is not a memory kind the backend emits (`goal` is). Drift is already present and nothing would say so.
- **Desktop:** one `#[cfg(test)]` block in `chatgpt.rs`; `cargo check` and the shell-contract script are the only gates. The sidecar handshake, the deep-link parser and the keychain fallbacks are untested.
- **Evals:** an LLM-as-judge harness exists (`tests/eval/`, 13 framework tests) and the content eval runs only by hand (`workflow_dispatch`). Fine for cost, but no signal reaches a PR.

## 06 · Added with this review

### new `tests/test_vendor_contracts.py`: resolve what the fakes cannot see

Two static checks against the installed packages: every vendor import that lives inside a function body (the ones no test's own import line has executed) resolves, including attribute chains such as `Filter.StringFilter.MatchType`; and every field in every GAQL query exists in the protos of the library's default API version. Both would have failed on the GA4 import from the day it was written, and the second turns a dependabot bump of `google-ads` into a real signal. Cost: 13 s, almost all of it the first import of `google.analytics.data_v1beta`, `google.genai` and the Ads protos. That is a fifth of the suite, spent on the one class of bug the rest of the suite cannot reach.

## 07 · What to do, in order

1. done **One request-shape test per fetcher, at the SDK boundary.** The GA4 test is the template: fake only the client, let the real types build the request, assert the request. GSC (two reports plus site list), GA4 conversion paths, the Google Ads report fetchers, Meta fetch, RevenueCat and Apple fetch. About a dozen tests, all cheap, and the request-building modules go from 16 to 43% to what the executors already have (76% and up). Half a day.
   *Landed the same evening (9b09dc7, ded9144): `test_gsc_fetchers.py`, `test_google_ads_fetchers.py`, `test_rest_connector_requests.py` (Meta, Apple, Stripe, RevenueCat) and two more GA4 tests, on three new shared seams in `tests/fakes.py` — `FakeWire` under `httpx.request`, `RecordingHttp` + `discovery_build_offline` for the discovery-document APIs, `FakeAdsClient.search_stream` with real row protos. The rule is written into `backend/AGENTS.md`.*
2. done **A live smoke per connector, run by hand and on a schedule.** The script from 09-14 (list bound sources for a user's projects, call every fetcher with a two-week window, print status only) is the shape; it found the OAuth client split in one run. Wire it as `pytest -m live tests/test_connector_smoke.py` gated on a service account, on the same manual workflow as the content eval.
   *Landed (abfdc4a, d173660): `tests/test_connector_smoke.py` and `connector-smoke.yml`, Mondays 06:00 UTC and on demand. Its five repository secrets are set through `scripts/push_env_to_github.py`; the user is a secret, not a variable, because variables are world-readable on a public repository. It cannot be dispatched until the workflow file is on `main`, so the first run is after this branch merges.*
3. deferred **Model the two Google OAuth clients in a test** once the credential row records its issuer: mint with client A, refresh with client B must pick A's secret. Small, and it pins the fix.
   *Waits on the fix itself, which lives in `service/google/credentials.py` and `service/connector_access.py`, both mid-edit in the developer-token removal on this branch at the time of writing. Nothing to test until the row carries the issuing client id.*
4. done **Read the app's event vocabulary from the backend test.** `test_agent_core` should parse `app/src/lib/agentEvents.js` and the fixtures under `__fixtures__` and assert every event name and every memory `kind` exists on the backend. One test, catches the drift that is already there.
   *Landed (6b8fc63) as its own file, `test_app_event_contract.py`: events both ways, error codes exactly, insights step ids, fixture events and memory kinds. Its first run caught the `"target"` kind; the fixture now says `goal`, and `app/AGENTS.md` points at the test.*
5. partly **One Postgres run in CI.** A service container, the suite once against it with `DATABASE_URL` set: FTS, JSON columns, the checkpointer's real saver, and an `alembic check` step that fails on autogenerate diff. Ten minutes of YAML, closes two gaps at once.
   *The migrations half landed (bca7c96): a `migrations` job in `backend.yml` applies the chain to a fresh Postgres 16, runs `alembic check` and undoes the newest migration once; `make check-migrations` mirrors it. The suite half did not: the engine fixture creates tables from the models per test, so running it on Postgres is a fixture redesign, not a YAML change. The job could not be run locally (no Postgres here) and the staging database is behind head, so the first pull-request run is its first real run.*
6. done **Keep the tail visible.** `--durations=10` in `addopts`, so the next slow test is seen the day it lands rather than found by coverage archaeology.
   *Landed (5d5f657). Paid for itself on its first run: one of the new RevenueCat tests was sleeping 2.4 s on the real charts pacer, fixed in ded9144.*
7. done **Desktop: three Rust tests.** Handshake line parsing, deep-link URL parsing, keyring error description. The three places where a regression reaches a user as "the app does nothing".
   *Landed (166308c): seven tests across the three seams, after extracting `parse_handshake` and `deep_link_target` as pure functions. `cargo test --lib` now runs in `desktop-check.yml` and `make check-desktop` — the two ChatGPT callback tests the crate already had ran nowhere before. About a minute on a warm cache.*
8. not started **Later:** component tests only for the pause cards and the composer, where state and copy meet; the SSE smoke into CI only after it has proven flake-free by hand, as `app/AGENTS.md` already says.
   *Still later, on purpose.*

None of this changes the philosophy the suite already has (behaviour over wording, hermetic by default, fakes that keep real protos). It moves the fake one layer down, where the bugs have been, and lets one scheduled run touch the real vendors so a change on their side is a notification rather than a support thread.
