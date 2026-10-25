# Agent harness review: the findings

**Author:** Shirish Kadam · **Date:** 2026-10-25

The tables behind [`2026-10-25-agent-harness-review.md`](2026-10-25-agent-harness-review.md). Read that first; open this when fixing something. Paths are relative to `backend/`, `app/src/` or `desktop/src-tauri/` as the section says, at 84630151 on `feat/mcp-connectors`.

## Security: counts and classes

Exploit paths are in `docs/engineering/2026-10-25-agent-harness-security-findings.md` in the private repository until each row is fixed.

| Area | High | Medium | Low | Classes |
|---|---|---|---|---|
| API and harness | 2 | 4 | 2 | an id trusted across tenants; an unbounded read before a cap; unbounded MCP listings; a writer replayed on crash-resume with no idempotency key; `str(exc)` in tool results and activity cards; server-authored approval titles |
| Desktop shell | 2 | 3 | 1 | a remote origin granted more than it uses; no navigation guard on the window; secrets in a child process environment; self-host entitlements on the shell binary; a prefix check a crafted host passes |

Checked and sound:

- **SSRF:** scheme allowlist, hostname denylist, resolved-address check on every redirect hop, for web fetch and MCP alike.
- **MCP OAuth:** PKCE S256, resource indicator on both legs, issuer check, single-use state bound to the starting user, token bodies never logged.
- **MCP tool surface:** two fixed tools, no name collision with Duct tools, approval shows arguments whole or refuses.
- **Session routes:** owner-checked on stream, messages, state and delete; non-members get 404; per-user live-session cap.
- **Execution:** no approve or apply tool; auto-apply needs allowlist, non-destructive, rollback-capable and clean preview, all four.
- **Artifacts and memory:** scoped by project on read and write.
- **Rendering:** scripted artifact frames never carry `allow-same-origin`; mermaid goes through DOMPurify.
- **Serialisation and telemetry:** no pickle, eval or unsafe YAML; checkpoints are msgpack; spans and logs carry no secrets.
- **Desktop:** the updater signature check cannot be disabled, deep-link values are validated, ChatGPT sign-in is PKCE with a bound listener, the sidecar binds loopback on a random port behind a per-install key.

## Correctness (`backend/`)

| Sev | Where | Defect | Fix · test |
|---|---|---|---|
| High | `agents/content/tools.py` `publish_post`; `agents/content/publishing.py:62-76,124-141` | Nothing checks `post_bridge_post_id` or a scheduled/posted status. A second call uploads media again, creates a second PostBridge post and overwrites the id, so every later edit or cancel misses the first. The publish route has the same hole | refuse in `publish_blockers` · publish twice, assert one create |
| Med | `tools.py` `mark_posted` | Marks a PostBridge-queued post `posted` without cancelling it; PostBridge still publishes at the scheduled time | cancel first or refuse · one test |
| Med | `agents/insights/fetchers.py:119-126` + the manual fetchers | Mixpanel, Clarity and GrowthBook count back from yesterday but the result is captioned with the requested window. An August ask returns September data labelled August, and the verifier compares the wrong periods | report the window the fetcher read, or refuse one not ending yesterday · test on `fetch_entity` |
| Med | `tools.py` `publish_post`, `generate_image`, `edit_image`, `log_metrics` | DB session held open across provider calls; a slide phase holds 4–5 Postgres connections for 10–60 s each. `generate_video` already does it right | the `generate_video` shape |
| Med | `agents/models.py:416,490-491` | `GPT_6_LUNA` falls back to `GPT_5_MINI`, 2.5× dearer on input and 4× on output; content also uses the sibling as its *cheap* research model | `GPT_6_LUNA: ()` · PRICING-monotone assertion over `MODEL_FALLBACK` |
| Med | `agents/audit/v1/runner.py:600` | Thread keyed on `session_id`, minted per session. A resumed audit never sees its checkpoint and a turn cut by a redeploy cannot continue; the runner's docstring describes this as the failure the checkpointer prevents | `thread_id=conversation_id or session_id` · resume with a new session id |
| Med | `tools.py:1364-1397` `fetch_content_assets` | Returns every asset with full `params`, no limit | `limit=50`, trim `params` |
| Low | `agents/insights/v1/runner.py:596-638` | Scheduled briefs mount `ProposeChanges`; under `auto` the allowlist applies with nobody watching. Intended? Pin it either way | `execute=False` or a test |
| Low | `agents/insights/data_tools.py:281-282` | Two keys per pull, so `FETCH_CACHE_MAX=64` holds 32; after that the verifier re-fetches the 45 s GA4 report | count distinct `resolved` |
| Low | `tools.py:1724-1739`; `agents/core/lc.py:547-587` | Video spend is a hand-emitted usage event; a reopened thread's total drops it | read `scope:media` rows in thread state |
| Low | `agents/core/deep_session.py:170-190`; `agents/content/v1/runner.py:451-454` | Fallback and content models lose `cache_key`; an OpenAI loop rebuilds its prefix per call | pass it through |
| Low | `agents/content/persistence.py:55-70` | Image bytes under 256k are written whole into `agent_events` although the checkpoint prunes them | placeholder before `record_tool_result` |
| Low | `agents/audit/crawl.py:85-90`; `agents/audit/prefetch.py:163-179` | 35 fetches at one host with no semaphore; robots fetched, not honoured; a 45 s prefetch timeout leaves the first crawl running while a second starts | semaphore; honour or say so; cancel the prefetch |
| Low | `agents/core/deep_session.py:588-603` | A steered message whose turn raises is neither re-queued nor recorded | re-queue · test |
| Low | `agents/core/connector_tools.py:252`; `agents/insights/fetchers.py:337-338` | `str(exc)` reaches the model and then the brief | classify |
| Low | `tests/test_github_app.py:376` | The "unconfigured" `Configs()` still loads the GitHub App values from a developer's environment, so the suite is red on a laptop that has them and green in CI | pass the four fields empty |

Sub-agents, checked: content's four are read-only; insights' verifier is `FetchData` + `ReadConnectorNotes` on the Standard tier; the auto-added general-purpose one still carries everything (rulebook gap 1); none has retry or limits (gap 5).

## Libraries

| Package | Installed | Latest | What matters in between |
|---|---|---|---|
| deepagents (pinned) | 0.7.23 | 0.7.32 | the summariser retries on overflow (0.7.24) and strips Claude reasoning bound to replaced history (0.7.30), both under Duct's own compaction path; `summarizer=` can run compaction on the Light tier (0.7.26); the harness profile files are unchanged byte for byte; legacy `mode="handoff"` is gone (Duct does not use it) |
| langchain / core | 1.4.3 / 1.6.10 | 1.4.7 / 1.7.0 | core 1.7 changes streamed tool-argument events; `stream_agent` reads text and thinking only, so no consumer breaks |
| langgraph | 1.2.12 | 1.2.17 | resume fixes on the exact path Duct's pauses run (an invalid resume no longer kills sibling tasks; answered interrupts are dropped from state, the field `lc.py:679` works around); DeltaChannel checkpoint fixes; forces checkpoint 4.3.0 |
| checkpoint-postgres | 3.1.2 | 3.2.0 | `prune()`, the checkpoint-deletion runner-up; closes GHSA-6hmw-9432-67qq (Store namespaces; Duct uses only the saver, so not exposed) |
| langchain-anthropic / -openai | 1.7.5 / 1.6.7 | 1.7.6 / 1.7.2 | profiles for Haiku 5.5 and Mythos; Duct's catalogue ids are unchanged, so the ~850k summarisation trigger (gap 3) is still Duct's to fix |
| mcp | 2.3.0 | 2.3.0 | current. `streamable_http_client` caps one SSE event at 1 MiB by default and `service/mcp/client.py:180` does not pass the argument, so a remote tool result over that fails rather than being bounded by Duct |

Already installed and unused, enough for the gap list: `ToolErrorMiddleware`, `ModelRetryMiddleware.retry_on`, `GeneralPurposeSubagentProfile(enabled=False)`, `HarnessProfile.excluded_middleware`, trigger override by name. No library ships a cost ceiling or timeout middleware (gap 12 stays Duct's).

Bump order, each PR gated by `test_deepagents_harness.py` and `test_agent_assembly.py`:

1. langgraph + langgraph-checkpoint + checkpoint-postgres + langgraph-sdk. Also resume a real pause on a Postgres thread.
2. langchain-core + langchain + langchain-anthropic + langchain-openai + langchain-google-genai, together. Also `test_request_invariants.py` and `routes/chat.py` by hand.
3. deepagents alone. Also `make dump-prompts` byte-identical and the compaction cases; update the pin comment at `pyproject.toml:73` and the "0.7.15 ships" line in the rulebook.

## Performance (`backend/`)

Dev numbers assume the measured 45 ms proxy round trip; prod private networking is 1–2 ms, so the database rows shrink there and the model rows do not.

| # | Lever | Evidence | Saving | Effort |
|---|---|---|---|---|
| 1 | `clear_at_least` on `ClearToolUsesEdit` | `agents/core/deep_session.py:332-337` passes none; langchain's `context_editing.py:95-98` clears `candidates[:-keep]` on every call past the trigger, so each call clears one more result and the prefix diverges at the 6th-newest tool message | 1–2 s per call after 120k tokens, and 1.25× instead of 0.1× price on ~60k tokens per call; 10–20 s on a long brief | S |
| 2 | Verifier fetches in one turn, at lower effort | the prompt says "once per entity", never "in one turn"; langgraph runs a turn's calls with `gather`; `verify_llm` inherits the analyst's thinking level | 20–40 s of 66 s (hypothesis, needs a trace) | M, eval gate |
| 3 | Recorder writes off the superstep boundary | `agents/content/persistence.py:425-434` awaits the write inside the stream consumer; one row is three statements plus a pre-ping | 6–9 s of 198 s in dev, ~0.3 s prod | S |
| 4 | 1h cache TTL for idle chats | both caching middlewares hardcode 5m; `CHAT_IDLE_TIMEOUT` is 30 min, so a pause over 5 min is the normal case | 2–4 s and 1.25× vs 0.1× on ~100k tokens at the first follow-up | S–M |
| 5 | Checkpointer: pool and prune | `agents/core/checkpoint.py:153` opens one `AsyncConnection`, every cursor under one lock for all sessions; `messages` is written whole on each change, ~2.2 MB at 150k tokens, twice per model call; nothing deletes a thread | a throughput ceiling past one concurrent session; ~250 MB per 60-call run | M |
| 6 | `POST /sessions` sync DB work on the loop | `routes/agents.py:1377-1392,1803-1810` | 0.4–0.9 s dev per start, stalling every open stream | S |
| 7 | Priming: gather, and one ranked query for the digest | `routes/agents.py:1948-1963` serial; the digest is ~12 queries | ~1.2 s dev / 50 ms prod | S / M |
| 8 | SDK retries under Duct's (gap 2) | anthropic `max_retries=2` × 4 harness attempts | failure path 60–90 s → ~15 s | S |
| 9 | Boot | 26 s to "startup complete" on 2026-10-19: 19 s connect + `setup()`, runner import 18 s cold | skip `setup()` after first boot; lazy Google imports | M |

Not a lever: checkpoint serialisation CPU (2 ms, off-loop; the virtual FS is a delta channel), SSE framing, prefix stability (no timestamps, fixed tool order), indexes (all present). `agent_events` keeps full tool results with no retention, about 1 MB per brief turn.

Measure first: `cache_read_tokens` against `cache_creation_tokens` per call, in order, across one real thread, from the `model_usage` rows already written. It confirms or kills #1 and #4 with a query.

## Shell (`app/src/`)

Read against Claude Code 2.1.287–310, Codex 0.161–0.164, OpenCode 1.18.31–1.19.4 and pi 0.86–1.4. Open rows in `agent-harness-references.md` are not repeated.

| Capability | Duct today | Elsewhere | Gap |
|---|---|---|---|
| Runs outlive the page | unmount sends DELETE and the recorder marks the turn cancelled (`hooks/useAgentSession.js:369-381`, `backend/routes/agents.py:150-170`); the 60 s grace covers dropped streams only | background sessions in all four | opening Connections mid-brief kills the brief |
| Sub-agent visibility | one row: brief plus a 140-char summary (`lib/toolActivity.js:758`) | a status line per sub-agent, transcript on demand | no progress, nested calls or clock |
| Viewport progress | `components/PipelineProgress.jsx:664-668,724`: "~3 min" hard-coded, a 180 s fill unrelated to progress | elapsed per step, last run's duration | the chat pane is honest, the right pane mimes |
| Cost per turn | computed (`lib/agentSession.js:337`) and never shown; `components/workspace/ContextRing.jsx:662-666` omits it; `app/AGENTS.md` says the tooltip carries it | footer cost and cache share | BYO-key users pay per turn and see nothing |
| Composer | plain textarea, no `/`, no `@`, draft lost on reload (`components/workspace/ChatInput.jsx:64`) | `@` mentions, drafts, presets | no way to point at a source, memory or brief |
| Approvals | approve or skip per call (`components/insights/ToolApproval.jsx:67-74`), nothing persisted | "always allow" with a list | a by-address MCP server asks forever |
| Change-set card | `diff \|\| summary` as one line (`components/execution/ChangeSetCard.jsx:217-219`); `DiffJsonView` exists and is unused | a diff with restore | |
| Artifact versions | diff only on the viewer page (`app/(app)/artifacts/[artifactId]/page.jsx:130-141`) | version arrows and restore beside the chat | "what changed since v2" is a page away |
| Export and share | PDF for audit reports only (`backend/routes/artifacts.py:246-248`); share is an audit member link | PDF, markdown, share links | a growth brief cannot leave |
| Titles and search | `prompt[:120]` (`backend/routes/agents.py:1391`); rename exists server-side (`:1197`) with no UI; no search | generated titles, rename, filter | nothing findable at 50 threads |
| "Why did it do that" | CONTEXT row, model divider, thinking fold; no trace or request id | compaction summaries, trace links | Phoenix holds every trace and the UI never points at it |

Ranked improvements, by value over effort:

1. Runs survive navigation: detach on unmount, a running badge in the sidebar, explicit Stop the only cancel (M).
2. Honest viewport progress: elapsed plus the last run's duration from stored conversations (S).
3. Version arrows and a diff toggle in the pane header, reusing `diffArtifact` (S).
4. Select-to-ask in the brief: Ask, Rewrite, Remember, quote lands in the composer (M).
5. `@` mentions resolving to `FetchData`, `GetMemory`, `GetArtifact` (M).
6. Remembered tool approvals per server, listed on the connect dialog (S–M).
7. Generated titles, inline rename, a filter box (S–M).
8. Nested sub-agent rows with a clock, via `parent_id` on `TOOL_ACTIVITY` (M).
9. A "why this answer" line under each reply: sources, memories, model, seconds, cost, trace id (S–M).
10. Cost on the ring for BYO keys (S).
11. Draft persistence, Esc stops, Shift+Enter hint (S).
12. Brief export and share: PDF for markdown and HTML briefs, PNG for charts, member link (M).
13. Stream an HTML brief as a document, not a wall of tags (`components/insights/InsightsWorkspace.jsx:593-603`) (S).

Defects found in the code:

| Where | Defect |
|---|---|
| `lib/agentSession.js:788-806,715,737`; `hooks/useAgentSession.js:76,341,353`; `hooks/useAgentNotifications.js:547-555` | Untranslated user-facing copy; `scripts/check-literal-strings.mjs:17` walks JSX text only |
| `components/workspace/Todos.jsx:989-993,1028`; `PipelineProgress.jsx:780-788,819`; `AgentChat.jsx:74,653,793,860,886`; `QuestionsCard.jsx:825`; `AccountSelect.jsx:63` | Glyphs as icons, against DESIGN.md |
| `components/workspace/AgentChat.jsx:739-797`; `SplitWorkspace.jsx:490` | Status row cannot wrap; "Start fresh" clips off-screen on phones; three bars stack before the first message |
| `components/insights/InsightsWorkspace.jsx:438,444` | Raw `ask/assisted/auto` enums in `AutonomyBadge` |
| `components/AgentDrawer.jsx`; `components/ChatSidebar.jsx` via `LocalInsightDetail.jsx:215` | Dead drawer with `<div onClick>` and "coming soon" buttons; a second chat fork still mounted |
| `components/workspace/MemoryRows.jsx:556-557` | `trackChip` is empty while its comment calls it "the one honest signal" |
| `InsightsWorkspace.jsx:520-538`; the artifact viewer toolbar | Native `<select>` for versions, inline `px` styles |
| `InsightsWorkspace.jsx:178-215` | Opening a stored brief fetches every version's bytes before showing one |
| `components/workspace/ContextRing.jsx:735-741` | A `<button>` labelled "Show token usage" with no click action |
| `components/workspace/AgentChat.jsx:365-384` | In-stream artifact card: emoji icon, raw `kind` enum, opens a new tab instead of the pane |

Three delight ideas specific to a marketing agent:

- **"Since last time" divider.** On reopen, re-pull the windows the last brief read (`dataSourceRollup` knows them) and say what moved, with sparklines.
- **Receipts on numbers.** Briefs carry `EvidenceSource` (`backend/agents/core/artifacts.py:416-427`); render each cited figure as a footnote chip with the connector's mark, hover for source, window and rows, click to the activity row that produced it.
- **Watch this.** A "Watch" action on any finding writes a `watch` memory (the kind exists, `components/memory/MemoryTimeline.jsx:80`); the scheduled brief checks it and the desk's "Needs you" card fires when it crosses.

## Desktop (`desktop/src-tauri/`)

Tauri 2.12 / wry 0.57; plugins deep-link, updater, opener, notification, single-instance; keyring 3.6. Security rows are in the private record.

| Sev | Where | Defect | Fix |
|---|---|---|---|
| Med | `src/lib.rs:164-188,194,384-409`; `src/chatgpt.rs:522-525,616-618`; `app/src/lib/providerKeys.js:211-226` | Keychain and file commands run synchronously on the main thread; the app issues up to five keychain reads per API request, absent keys re-read every time | `#[tauri::command(async)]`; cache `get_shell_info` in a `OnceLock`; cache negative lookups in JS |
| Med | `src/sidecar.rs:343,401-410` | stdin is null and shutdown runs only on `RunEvent::Exit` with SIGKILL; a crash, `kill -9` or a main-thread restart orphans the Python process holding the DB and port | pipe stdin and exit on EOF in `local_server.py`; `PR_SET_PDEATHSIG` on Linux, a Job Object on Windows; SIGTERM then grace; `request_restart()` in `install_update` |
| Med | `src/lib.rs:1029` | Only `on_open_url` is registered; a cold-start deep link on Windows and Linux is dropped and the 60 s code expires | `deep_link().get_current()` in setup |
| Low | `tauri.conf.json:74` | `perMachine` install means UAC on every self-update | per-user |
| Low | `src/lib.rs:977-981` | Reveal and focus on every finished load steals focus on reload | guard with an `AtomicBool` |
| Low | `src/telemetry/mod.rs:109` | Identifier hardcoded, so the `.dev` build shares data files and the sidecar SQLite with an installed Duct | `app_data_dir()`, `--data-dir` |
| Low | `tauri.conf.json:69` | appindicator deb dependency with no tray | remove |
| Low | `src/sidecar.rs:205,353,363-376,403,418,421` | `.lock().unwrap()` where `chatgpt.rs:235` tolerates poison; a poisoned lock is a main-thread panic | match the tolerant pattern |

Quick wins: async commands plus the shell-info cache take five Security.framework calls off the UI thread per request (1–5 ms each, seconds when a prompt is pending); a `OnceLock` `reqwest::Client` in `src/chatgpt.rs:426` saves rebuilding rustls per token refresh; spawning the sidecar off `setup()` lets the splash paint before the keychain answers. Do not `strip` without the Sentry debug-file upload.

Sound: release profile, updater, deep-link validation, ChatGPT PKCE, keychain separation, sidecar bind and auth, official-build entitlements and notarisation, telemetry scrubbing, artifact frame sandboxing, platform cfgs.
