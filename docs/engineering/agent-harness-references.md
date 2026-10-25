# Agent harnesses we learn from

**Author:** Shirish Kadam · **Updated:** 2026-10-26

Three coding-agent harnesses are built in the open by teams who hit every problem our agent shell hits, a year ahead of us and with more users. Reading them is cheaper than rediscovering their answers.

A harness is the code around the model: loop, tools, streaming, pauses. This watch-list says which we read, why, and at which revision, with each finding pinned to a file and line so a later reader diffs instead of re-reading.

Reference material, not rules: the rules a reading produced live in the area `AGENTS.md` files and [the agent rulebook](agent-engineering.md); this file records where they came from.

## At a glance

- **Three harnesses and one index:** Codex, OpenCode and pi at a pinned revision; awesome-harness-engineering for sources.
- **Same problems, worked answers:** reconnect, resume, pauses that outlive a process, flicker-free streaming, actionable errors.
- **Two days of fixes:** 17 of 27 exposed gaps closed on 2026-09-04 and 05; nine open, one half done, sized in the Reference.
- **Evidence, never opinion:** each finding is a file and line at a named revision. No code is pasted here.

## Three harnesses, each for a different reason

Codex has the most complete client protocol, OpenCode has our shape, and pi shows the minimum that works.

| Harness | Why it matters to us | Last read |
|---|---|---|
| **Codex** (OpenAI), `github.com/openai/codex` | The desktop and IDE apps are clients of `codex app-server`, a JSON-RPC server whose thread / turn / item contract is the most fully specified agent-UI protocol in the open. The desktop app is closed; the TUI in the same repo is the reference client. | `de78740`, 2026-09-04; the shallow clone at `../codex` is gone (2026-10-25), re-clone to refresh |
| **OpenCode** (Anomaly), `github.com/anomalyco/opencode` (moved from `sst/opencode`; default branch `dev`) | A TypeScript server and clients over a session / message / part model with an SSE event bus, mid-migration to an event-sourced v2. Provider-agnostic, and the closest in shape to our Next.js app talking to a backend. | `5cf9f51`, 2026-09-04 |
| **pi** (Earendil), `github.com/earendil-works/pi` (moved from `badlogic/pi-mono`; docs at `pi.dev/docs/latest`) | A deliberately small TypeScript agent loop and TUI: the reference for how little harness you need. Explicit steer-versus-follow-up input modes, abortable retry, session trees. | `9841914`, 2026-09-05 |

## One index feeds the reading list

A harness is read at a revision; an index is read for leads. This one curates the harness-engineering literature (vendor engineering posts, papers, open implementations) by concern: loop, planning, context, tools, memory, permissions, human-in-the-loop, evals, observability.

> **Rule:** mine it for sources, then read the primary one. Its one-line summaries are an editor's, and some run ahead of what the source measured.

| Index | What we took | Last read |
|---|---|---|
| **awesome-harness-engineering**, `github.com/ai-boost/awesome-harness-engineering` (raw README, no clone needed) | The rules in [the agent rulebook](agent-engineering.md) and four records of the same day: [eval gating](2026-09-27-agent-eval-gating-design.md), [insights code execution](2026-09-27-insights-code-execution-design.md), [execution approvals](2026-09-27-execution-approval-ux-research.md) and [memory freshness](2026-09-27-memory-freshness-design.md). Found through it: the audit graph had none of the shared middleware (fixed; `tests/test_agent_assembly.py` holds it), and a stopped process left its runs `running` (fixed; `cancel_orphaned_runs`). | `5592ad5`, 2026-09-27 |

## How to read one

1. **Shallow clone into a scratch directory** outside this repository (`git clone --depth 1 --filter=blob:none`) and delete it afterwards. Never beside the repo: the root `AGENTS.md` forbids sibling directories.
2. **Start from the docs index and the protocol README's table of contents.**
3. **Grep for the mechanism**, then read the 30 to 60 lines around the hit. Never a whole file.
4. **Pin what you found** as `file:line` at the named revision. No code is pasted here.
5. **Update "Last read".** Findings are dated by that revision.
6. **Move any new rule** into the area `AGENTS.md`; this file keeps the provenance.

**Refreshing:** in a fresh clone, `git log <rev>..HEAD -- <path>` from the table's revision lists what moved; re-pin, then update "Last read".

## What each reading changed in Duct

Small gaps closed within a day of each reading.

| Harness | What we took | Where it landed | Still open |
|---|---|---|---|
| Codex | Typed error codes mapped to copy and an action. Elapsed clock and activity label. Tables held until the block closes. Usage, context left, visible compaction. Mid-turn follow-ups steered or queued. Run status on the list. | `app/src/lib/agentSession.js`; rules in [backend/AGENTS.md](../../backend/AGENTS.md) and [app/AGENTS.md](../../app/AGENTS.md) | Pause-resolved event. Reject with feedback. Thinking folded by default. One writer per conversation. Interrupted marker. One item lifecycle. Non-blocking questions. Step durations. |
| OpenCode | Retry as a status with a deadline and an action, `Retry-After` honoured. Failure stored on the thread with a code. Healed streaming tail. Notifications from phase transitions. Cost beside tokens. Pending pauses and status for every conversation. | `ReportedRetryMiddleware` and `ConversationRecorder` in `backend/`; the contract in [agent-ports-and-events.md](agent-ports-and-events.md) | None. |
| pi | Stop hands queued messages back. A `Retry-After` past the cap fails at once. Gauge unknown after compaction. Cache-hit share. Compact once and retry on overflow. | `compact_thread` in `backend/agents/core/lc.py`; `ContextRing.jsx` in `app/` | An "after this turn" send. Cache-miss attribution in dollars. Session trees. |
| awesome-harness-engineering | The rulebook, four research records, two bugs found by comparison (above). | [agent-engineering.md](agent-engineering.md) | Its own "Open gaps" section. |

## What they confirmed we already had right

The shell rebuilt on 2026-09-04 already matched all three here; nothing argues for redoing it.

- **The thread is the conversation** and outlives the session; a parked pause replays on reconnect, history hydrates before the stream opens, the grace is Codex's 60 s.
- **Steer at the next model call, refusing nothing.** Retry is a status with a countdown; the provider's wait wins. Usage sits on the message, summariser included.
- **A failure stays in history and out of the model's context.** Our READY phase is pi's settled state: nothing more happens on its own.

> **Remember:** read the harness before designing a lifecycle feature; the answer is usually pinned below.

## Reference

Pinned findings per harness, at the revision in the watch-list. "Ours" describes Duct at the time of the reading, so the reason for a change survives it. Gap rows are sized S, M, L so the next person picks by appetite, not by scrolling.

### Codex, at `de78740`

Paths are relative to `codex-rs/` unless they start with `sdk/`.

#### The contract a desktop client is built on

| Finding | How Codex does it | Ours, at the reading |
|---|---|---|
| **Three primitives, one item lifecycle** | Thread, turns, items. Every unit of work (user message, agent message, reasoning, command, file change, tool call, web search, plan, compaction) is an item in one tagged union (`app-server-protocol/src/protocol/v2/item.rs:237-416`), and every item goes `item/started`, deltas, `item/completed` (`app-server/README.md:1859`). Deltas carry the `itemId` from `item/started` so a client appends to the right thing (`item.rs:1421`, `:1433`, `:1490`). The TypeScript SDK reduces the whole protocol to eight events: `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.started`, `item.updated`, `item.completed`, `error` (`sdk/typescript/src/events.ts:76-85`, items at `sdk/typescript/src/items.ts:120`). | About 25 named events with a reducer case each; theirs is one lifecycle and a `kind`. |
| **Thread status is pushed, subscribable state**, not a field the client infers | `notLoaded`, `idle`, `systemError` or `active { activeFlags }`, with `waitingOnApproval` and `waitingOnUserInput` as the flags (`app-server-protocol/src/protocol/v2/thread.rs:1639-1656`), delivered as `thread/status/changed` (`README.md:651-668`). Thread listing returns the same status per row (`README.md:187`). | |
| **A turn ends in exactly one of three states** | `completed`, `interrupted` or `failed` (`v2/turn.rs:32`). A failure carries a typed `codexErrorInfo`: `ContextWindowExceeded`, `UsageLimitExceeded`, `rateLimitExceeded` (only after the retry budget), `ResponseStreamDisconnected { httpStatusCode }`, `ActiveTurnNotSteerable`, `Unauthorized`, `Other` (`README.md:1946-1967`). The client maps a code to copy and to the action it offers; it never pattern-matches message text. | |
| **Two ways to ask the user** | Blocking: `item/tool/requestUserInput` with `questions[] {id, header, question, options\|null, isOther, isSecret}` and `isBlocking` (`item.rs:1733`, answers at `:1786`, doc `README.md:2027`). Non-blocking: an `agentMessage` with `delivery: "async"` and a `questions` array; the reply arrives as an ordinary steer and the turn never stopped (`item.rs:250-260`, `README.md:1881`). Command and patch approvals are a third server-to-client request with sentence-shaped options (`README.md:1997-2023`); the full list of server-initiated requests is `common.rs:1698-1752`. | |
| **Pending requests belong to the turn and survive the connection** | A turn start, completion or abort fails every pending request with reason `turnTransition` (`app-server/src/bespoke_event_handling.rs:168,198,1211`; `outgoing_message.rs:185-200`). A client disconnect prunes only the connection's context; the callbacks stay keyed by thread (`outgoing_message.rs:242`, `:465`). `thread/resume` re-sends every still-pending request to the new connection (`thread_lifecycle.rs:791`, `outgoing_message.rs:362`). Whatever cleared a request, the client hears `serverRequest/resolved { threadId, requestId }` (`notification.rs:74`), so a second tab can drop its card. | |
| **Input during a turn is steered or queued, never refused** | `turn/steer` injects into the running turn with an `expectedTurnId` precondition (`v2/turn.rs:277-306`). `thread/queue/add` persists a follow-up with a client-provided `clientUserMessageId`, started when the thread goes idle; an interrupted turn leaves the queue paused (`README.md:930-952`). | |
| **Liveness is a timer, and writes are exclusive** | A thread unloads 60 s after its last subscriber leaves and activity stops, runs `SessionEnd` hooks, then emits `thread/closed` (`README.md:677-684`). One process holds the write lock on a thread; a second `thread/resume` gets `-32600` (`README.md:473`, `thread-store/src/local/writer_lock.rs`). The desktop keeps all of this alive across app restarts with a daemon on a unix socket (`app-server-transport/src/transport/mod.rs:54-64`, `app-server-daemon/src/client.rs:63-70`). | |

#### The loop underneath

| Finding | How Codex does it | Ours, at the reading |
|---|---|---|
| **One task per turn; steering is drained at the top of every model call** | All ops enter one channel (`core/src/session/handlers.rs:529`); spawning a task aborts the previous one with reason `Replaced` (`core/src/tasks/mod.rs:271-278`). A mid-turn message is appended to the turn's pending input (`core/src/session/turn_input.rs:553`) and drained before the next request is built (`core/src/session/turn.rs:337-345`); pending input alone forces another loop iteration (`turn.rs:470`). | |
| **Interrupt is cancel, grace, hard abort, then tell the model** | Cancel the token, wait a graceful timeout, abort the join handle, clear pending approvals (`core/src/tasks/mod.rs:903-944`). Then a `<turn_aborted>` marker is written into model history and the rollout flushed before `TurnAborted` is emitted (`:947-964`, text at `core/src/context/turn_aborted.rs:10-11`), so the next turn's model knows tools may have half-run. | |
| **Retries are status, not errors** | The model stream retries up to five times (`model-provider-info/src/lib.rs:28-33`) with 200 ms × 2ⁿ jittered backoff (`core/src/util.rs:6-7,86`), emitting `StreamError "Reconnecting... n/max"` to the UI each time (`core/src/responses_retry.rs:102-121`); `will_retry` distinguishes a retry from a terminal failure. | |
| **Compaction is automatic, mid-turn, and visible** | The trigger is computed after every sampling (`core/src/session/context_window.rs:56-118`) and run inside the turn (`core/src/session/turn.rs:506-530`). The summary replaces history behind a token-budgeted tail of prior user messages (`core/src/compact.rs:670-760`), with `PreCompact` and `PostCompact` hooks around it (`core/src/hook_runtime.rs:528,565`). The UI gets a `contextCompaction` item. | |
| **The rollout keeps two streams in one file** | `ResponseItem` and `Compacted` rebuild model context; `EventMsg` rebuilds the UI (`history/src/lib.rs:114`, policy at `rollout/src/policy.rs:10-142`). Errors, warnings and deltas are never persisted. Resume scans newest to oldest for the last compaction checkpoint and replays only that tail into the model (`core/src/session/rollout_reconstruction.rs:133`); the UI replays only safe items with their event ids cleared so nothing fires twice (`tui/src/chatwidget/replay.rs:26-33`). | |
| **Token accounting subtracts a baseline** | 12 000 tokens, so "% context left" reads 100 % after the first prompt (`protocol/src/protocol.rs:2394,2428`). `TokenCount` carries `{total, last, modelContextWindow}` plus a rate-limit snapshot (`:2318`, `:2251`) and is persisted and re-read on resume. | |
| **The plan tool goes straight to the UI** | `update_plan` parses `{explanation?, plan: [{step, status}]}` and emits `PlanUpdate` with an inert tool result (`protocol/src/plan_tool.rs:9-30`, `core/src/tools/handlers/plan.rs:93-97`). | Same shape as our `Todos`. |

#### The UI on top (the TUI; the desktop app is closed)

| Finding | How Codex does it |
|---|---|
| **Status row** | `Working (12s • esc to interrupt) · <detail>` (`tui/src/status_indicator_widget.rs:211-249`). The header is the first **bold** phrase of the current reasoning, so the model titles its own step (`tui/src/chatwidget/streaming.rs:246-273`); details sit under `└` capped at three lines (`status_indicator_widget.rs:41-42`); the interrupt hint keeps a fixed position and extra context is appended after it (`:245-263`). |
| **Reasoning is hidden live and folded after** | Deltas only drive the header; at block end the text becomes a dim bullet cell, and one without a bold title is transcript-only (`chatwidget/streaming.rs:232-290`, `history_cell/messages.rs:629-645`). |
| **Streaming commits a stable region and keeps a mutable tail** | (`tui/src/streaming/controller.rs:1-36`); one line per frame, flipping to catch-up with hysteresis under backlog (`streaming/chunking.rs:85-116`); pipe tables are held back until finalised because a new row reflows every column (`controller.rs:12-20`). |
| **Approval options are sentences**, and "No" has a feedback path | `No, and tell Codex what to do differently` aborts and hands control back (`tui/src/bottom_pane/approval_overlay.rs:836-912`). |
| **The question form** | Multi-question with options plus a per-question notes field, a synthetic `None of the above`, a "submit with unanswered?" confirm, and for non-blocking asks a 60 s hidden grace then a 60 s visible countdown (`tui/src/bottom_pane/request_user_input/mod.rs:60-69,600-638`). |
| **Errors** | A retry re-uses the status row and restores the previous header afterwards (`chatwidget/streaming.rs:301-311`); hard errors are a red `■` row, warnings a yellow `⚠` row (`history_cell/notices.rs:87,244`); rate-limit nudges at 50/75/90/95 % with a switch-to-cheaper-model modal at 90 % (`chatwidget/rate_limits.rs:19,441-512`); compaction takes over the status row and leaves `Context compacted · 1m 12s` behind (`chatwidget/compaction.rs:6-56`). |
| **Notifications** | On turn completion, coalesced by priority and suppressed while the terminal is focused (`chatwidget/notifications.rs:6-23`, `tui.rs:99-102`). |
| **Tool cells** | `Running` becomes `Ran`, exit code and duration on the result line, output truncated head+tail to five lines (`history_cell/exec_cell/render.rs:223-233,356-372,695-699`); MCP `Calling` becomes `Called server.tool` (`history_cell/mcp.rs:131-190`); plan steps `✔` struck-through, `□` bold for in-progress, `□` dim for pending (`history_cell/plans.rs:186-196`). |
| **Queued input is shown under the composer** | Three labelled sections (after next tool call, at end of turn, queued follow-ups) as `↳` rows (`bottom_pane/pending_input_preview.rs:88-175`); only one modal is ever visible, the rest wait in an interrupt manager (`chatwidget/interrupts.rs:17-58`). |
| **The footer is a state machine** | Over composer state and whether a task runs (`bottom_pane/footer.rs:165-238`), showing `N% context left` (`:1032-1044`). A failed transcript load degrades in place with an "Earlier messages unavailable" row that invites a scroll-up retry (`tui/src/pager_overlay.rs:462`). |

#### What this validated in ours

The shell rebuilt on 2026-09-04 (`app/src/lib/agentSession.js`, `app/src/hooks/useAgentSession.js`, `backend/agents/core/session.py`) already matched Codex on four points.

| Confirmed | In ours |
|---|---|
| The thread is the conversation | It outlives the session |
| A parked pause is replayed to a reconnecting client | The replay is not re-persisted |
| History is hydrated before the live stream opens | Same |
| The reconnect grace | The same 60 s |

#### What it exposes in ours

Rows marked done landed on 2026-09-04, the same day as the reading.

| Size | Gap | Status | Codex | Ours, at the reading |
|---|---|---|---|---|
| S | Typed error codes | done | `codexErrorInfo` enum mapped to copy and an offered action | `friendlyErrorMessage` regexed the message text (`agentSession.js:442`) |
| S | Elapsed time and activity label while running | done (label and clock; step durations still open) | status row plus `Ran · 1.4s` | "Thinking…" and step chips with no clock; steps carry no timestamps |
| S | A `pause_resolved` event | open | `serverRequest/resolved` for every clearing reason | a second tab keeps a stale card; the runner knows when a pause resolves and says nothing |
| S | Completion notification when the tab is hidden | done (via the OpenCode reading, 2026-09-05) | coalesced desktop notification, suppressed when focused | none; insights pipelines run for minutes |
| S | Hold back markdown tables until the block closes | done (settled plus healed tail, 2026-09-05) | `controller.rs:12-20` | `ChatMarkdown` re-rendered the tail on every delta, so briefs reflowed mid-table |
| S | "Reject, and say what to do instead" | open | the `No, and tell Codex…` option | `ChangeSetCard` has approve and reject only |
| S | Thinking folded to a title by default | done 2026-10 | transcript-only unless titled | `AgentChat.jsx` folds to "Thought for Ns" |
| M | Token usage and context left; compaction made visible | done | `TokenCount` per turn, `N% context left`, "Compacting context" | insights compacted silently through deepagents' `SummarizationMiddleware` (since moved to `backend/agents/core/lc.py`) and reported no usage. On BYO keys the user paid for what they could not see, and the Heavy, Standard and Light tiers had no "switch to Light" moment |
| M | Queue follow-ups while a turn runs | done (insights steers; content and audit queue) | steer or `thread/queue`, shown as `↳` rows | input disabled while streaming; chat while parked was a 409 |
| M | One writer per conversation; status on the list route | half (status on the list route landed 2026-09-05; the writer lock is still open) | writer lock, and `thread/list` rows carry status | two tabs can each resume the same LangGraph thread; the desk had no badge because the state route was per-conversation only |
| M | Interrupted marker | open | `<turn_aborted>` written and flushed before the abort is announced | `stop()` deletes the session; the next resume's model has no idea tools half-ran |
| L | Item lifecycle instead of an event per kind | open | `item/started`, deltas, `item/completed`, plus `kind` | 25 event names; add the next kind as an item, not as three new names |
| L | Non-blocking questions | open | `agentMessage { delivery: "async", questions }` | every question parks the pipeline |

### OpenCode, at `5cf9f51`

Paths are relative to `packages/`; `specs/` and `CONTEXT.md` sit at the root.

The runtime is mid-migration from a v1 session / message / part model to an event-sourced v2 (`session.next.*` events, a durable inbox, Context Epochs). The clients still run on v1, so both are read: v1 for what ships, the v2 spec for where it is going.

#### The contract a client is built on

| Finding | How OpenCode does it | Ours, at the reading |
|---|---|---|
| **Session, messages, parts, and the error is a field of the message** | `Assistant` carries `tokens {input, output, reasoning, cache {read, write}}`, `cost`, `finish`, `error` and `time {created, completed}` (`schema/src/session-message.ts:165-190`); a `Compaction` message `{reason: auto \| manual, summary, recent}` sits in the transcript as a message of its own (`:193-199`). An interrupt writes `error = {aborted: true}` plus `time.completed` onto the assistant message (`opencode/src/session/prompt.ts:1203-1210`), which the TUI renders as `· interrupted` after any reload (`tui/src/routes/session/index.tsx:1568`). | `pipeline_failed` was a stream event; `thread_state` returned `status: unfinished` and no error, so a reloaded failed turn was a user message with no reply and no reason. |
| **Session status is one pushed, subscribable state** | `idle`, `busy` or `retry {attempt, message, action?, next}` (`schema/src/session-status-event.ts:9-32`), published as `session.status` by a single service (`opencode/src/session/status.ts:39-48`); the runner sets `busy` at the top of every loop iteration and `idle` when its runner empties (`session/prompt.ts:1089`, `session/run-state.ts:60-64`). The session list paints a gutter for any busy-or-retrying session (`tui/src/component/dialog-session-list.tsx:238-240`), and a client bootstrap fetches the whole status map, not one session's (`app/src/context/global-sync/bootstrap.ts:390-406`). | |
| **Retry is a status with a deadline, not an error** | `next` is an epoch timestamp, so the client counts down ("retrying in 4s, attempt #2") on a one-second timer (`session-ui/src/components/session-retry.tsx:14-51`; TUI `tui/src/component/prompt/index.tsx:1550-1575`). The optional `action {reason, provider, title, message, label, link}` becomes a modal with one button (`tui/src/component/dialog-retry-action.tsx`, opened from `routes/session/index.tsx:357-366`); the same slot serves "subscribe" and "switch provider". Policy: 2 s × 2ⁿ with 25 % jitter, five retries, `retry-after-ms` and `retry-after` honoured whether seconds or an HTTP date, 30 s cap when the provider says nothing (`opencode/src/session/retry.ts:26-31,47-77`); every 5xx retries whatever the SDK's flag says (`:85-94`). A sub-agent's retry shows under its task row as `↳ retrying… attempt #n` (`routes/session/index.tsx:2249-2305`). | |
| **Pending prompts are listable, and every clearing is an event** | `permission.list` and `question.list` return the pending requests across all sessions (`opencode/src/server/routes/instance/httpapi/groups/permission.ts:23-28`, `question.ts:24-29`) and the app fetches them at bootstrap (`app/src/context/global-sync/bootstrap.ts:447-454`). A reply publishes `permission.replied`; a reject cascades to every sibling and an "always" resolves the siblings it matches, each with its own `replied` (`opencode/src/permission/index.ts:109-166`). The waits are process memory though: disposing the instance rejects them all (`:56-59`). | Unlike ours, their pause does not survive a restart. |
| **Input during a turn is persisted and picked up at the next model call, on the server** | `prompt()` writes the user message first (`session/prompt.ts:1052-1057`); `ensureRunning` on a running session just awaits the run in flight (`opencode/src/effect/runner.ts:115-138`); the loop re-reads history every iteration (`prompt.ts:1088-1096`), so the message is in the next request. Nothing is refused and there is no queue object. The TUI paints `QUEUED` on any user message newer than the one being answered (`routes/session/index.tsx:1387,1450`). The app's follow-up setting `queue \| steer` is being collapsed to `steer` (`app/src/context/settings.tsx:26,187,354-377`). v2 makes the inbox durable: `session.next.prompt.admitted` (with `admittedSeq`) and then `prompted` when the runner promotes it, so queued input replays to a reconnecting client (`specs/v2/session.md:36-40`). | Our `client_message_id` then `user_input_consumed` is their admitted then prompted. |
| **One lifecycle per kind, one client reducer** | v2's vocabulary is `session.next.step.started \| ended \| failed`, `text.started \| delta \| ended`, `reasoning.*`, `tool.input.started \| delta \| ended`, `tool.called \| progress \| success \| failed`, `retried`, `compaction.started \| delta \| ended` (`schema/src/session-event.ts:88-421`), reduced in one file (`app/src/context/server-session-v2-reducer.ts:29-390`). Every event gets an ascending id at the bus (`opencode/src/bus/global.ts:14-18`) and durable ones additionally carry `seq` and `aggregateID` (`event-v2-bridge.ts:45-60`). Same shape as Codex's item lifecycle. | |
| **The stream carries no catch-up; resume is refetch-then-listen** | The SSE handler subscribes eagerly, sends `server.connected`, heartbeats every 10 s and closes on `server.instance.disposed` (`opencode/src/server/routes/instance/httpapi/handlers/event.ts:29-33,63-71`). On `server.connected` the app re-bootstraps every active directory through a refresh queue (`app/src/context/server-sync.tsx:547-570`, `global-sync/queue.ts`). | Same as ours: hydrate, then stream. |
| **The share page is a projection of rows, not a replay of events** | Share sync watches `session.updated`, `message.updated`, `part.updated` and `session.diff`, batches per session and POSTs `{type: session \| message \| part \| model \| session_diff}` rows (`opencode/src/share/share-next.ts:124-140,179-200,250-266`); the page opens a WebSocket and reconciles rows by key (`web/src/components/Share.tsx:100-135`). That answers the question this file asked: they do not rebuild a transcript from the event stream. | |

#### The loop underneath

| Finding | How OpenCode does it | Ours, at the reading |
|---|---|---|
| **Overflow is a budget computed before the call** | usable = input limit minus reserved, where reserved is `min(20 000, max output)` unless configured; overflow when the last assistant message's total is at or above usable; `compaction.auto: false` opts out (`opencode/src/session/overflow.ts:8-34`). Compaction publishes `session.compacted` (`session/compaction.ts:554`), and a separate **prune** stamps old completed tool outputs `time.compacted` once more than 20k tokens are reclaimable beyond a 40k protected tail, never touching `skill` results (`:28-31,273-315`). A provider overflow rejection gets one compaction and one retry, then fails (`specs/v2/session.md:119-122`); in v2 only the `compaction.ended` event is durable and model-visible, deltas are live-only (`:113-117`). | |
| **Context Epochs: the system prompt is a cache baseline** | It is rendered once per epoch; when an environment fact changes (date, an `AGENTS.md`, the agent's skills) the change is appended as a chronological system message instead of re-rendering the prefix, and a completed compaction starts a fresh baseline (`CONTEXT.md:26-35`, `specs/v2/session.md:54-64`). | This is the discipline behind our "per-request data goes in the user message" caching rule, written down as a runtime concept. |
| **Interrupt writes the abort into the record** | (above), cancels background jobs whose metadata points at the session, transitively (`session/run-state.ts:111-143`), and in v2 fails any tool still `running` from a previous process with "Tool execution interrupted" before the next request (`specs/v2/session.md:47`). Same purpose as Codex's `<turn_aborted>`. | |
| **Usage and cost live on the message; the ring reads the last one** | Context % = the last assistant message's `input + output + reasoning + cache.read + cache.write` over the model's context limit (`app/src/components/session/session-context-metrics.ts:28-60`); the TUI sidebar shows tokens, % used and `$ spent` (`tui/src/feature-plugins/sidebar/context.tsx:19-44`); the app's tooltip is three rows (cost, usage, tokens) around a progress circle (`app/src/components/session-context-usage.tsx:104-135`). | The same formula, minus cost and reasoning tokens. |

#### The UI on top

| Finding | How OpenCode does it |
|---|---|
| **Streaming markdown is projected block by block** | Everything before the last non-space token is committed as `full` blocks; the tail is one `live` block healed with `remend` (closes dangling emphasis and links); an open fence streams as `code` without `complete` (`session-ui/src/components/markdown-stream.ts:53-86`), and `project()` reuses the previous blocks when the text only grew (`:88-100`). A cheaper answer than Codex's chunker to the same reflow problem. |
| **Notifications are a plugin over four events** | `session.status` idle-after-busy gives "Session done"; `question.asked` or `permission.asked` gives "needs input"; `session.error` gives "Model stopped responding" or "Session aborted"; desktop notification only when blurred, sound always, never for a sub-agent (`tui/src/feature-plugins/system/notifications.ts:9-86`); an unknown focus state suppresses rather than guesses (`tui/src/attention.ts:107-133`). |
| **The interrupt hint is two-stage** | `esc interrupt` becomes `esc again to interrupt` after the first press (`tui/src/component/prompt/index.tsx:1587-1590`). |

#### What this validated in ours

| Confirmed | In ours |
|---|---|
| Steering at the next model call, server-side, with nothing refused | They are folding their client-side queue mode into it |
| Resume as hydrate-then-listen with no sequence catch-up on the stream | Same |
| Usage on the message and a ring over the last call | Same formula |
| Pruning old tool output before compacting | Our `ContextEditingMiddleware` (now mounted in `backend/agents/core/deep_session.py`) is their `compaction.prune` |
| One reducer over typed events | Same |

#### What it exposes in ours

Rows marked done landed on 2026-09-05, the day after the reading.

| Size | Gap | Status | OpenCode | Ours, at the reading |
|---|---|---|---|---|
| S | Retry status carries a deadline and an action | done | `retry {attempt, message, action?, next}`; the row counts down; `Retry-After` honoured | `model_retrying {attempt, max_attempts, code}`; `retry_delay` was 1 s × 2ⁿ capped at 8 s and ignored `Retry-After`; the row said "(2/4)" and could not count down |
| S | The failure is part of the thread | done | `Assistant.error`, `aborted: true` on interrupt, `· interrupted` after a reload | `pipeline_failed` was stream-only; `thread_state` said `unfinished` with no error, so a reloaded failed turn showed no reason and no action |
| S | Heal the streaming tail instead of re-rendering it | done | `markdown-stream.ts` commits closed blocks, heals the open one | `ChatMarkdown` re-rendered the whole tail per delta: the Codex table's "hold back tables" row; one fix closed both |
| S | Notifications keyed on status transitions | done | idle-after-busy, `*.asked`, `session.error`, blurred-only | parked on 2026-09-04; built from the reducer's phase transitions like this, not per workspace |
| M | Cost, not only tokens | done | `cost` on every assistant message, `$ spent` in the sidebar | `usage` carried tokens only; on BYO keys the dollar figure is what the user pays |
| M | Pending pauses across conversations | done | `permission.list` and `question.list` at bootstrap; status map for every session | the state route was per conversation: the Codex table's "status on the list route" row, with the list shape spelled out |

### pi, at `9841914`

Paths are relative to `packages/`. The docs site is rendered from `packages/coding-agent/docs/*.md`, so the markdown is the record.

#### The loop, and what it refuses to own

| Finding | How pi does it | Ours, at the reading |
|---|---|---|
| **The loop is one function** | `agent/src/agent-loop.ts:150-268`: drain steering, stream the assistant, run its tool calls, `turn_end`, ask `shouldStopAfterTurn`, poll steering again; when it would stop, poll follow-ups and go round once more. The `Agent` wrapper (`agent/src/agent.ts`) owns the transcript, two `PendingMessageQueue`s (`:125-160`) with `QueueMode = "all" \| "one-at-a-time"` (`types.ts:50`), abort and `waitForIdle`. Ten events in the core (`types.ts:431-446`): agent, turn, message and tool_execution, each start and end (plus update for the streaming two). Nothing else lives there: no persistence, no compaction, no retry. | |
| **Everything else is the session around it** | `coding-agent/src/core/agent-session.ts` (3.5k lines) plugs in through hooks: compaction runs between turns in `prepareNextTurn` (`agent-loop.ts:176-197`, so steering typed during a long compaction is picked up after it), retry re-runs the loop from the outside (`_willRetryAfterAgentEnd` `:725-735`), and the session adds its own events `agent_settled`, `auto_retry_start \| end`, `summarization_retry_*` (`:149-184`). `agent_end` carries `willRetry`; `agent_settled` means nothing more will happen on its own: no retry, no compaction retry, no queued follow-up (`docs/rpc.md:899-912`). | That is what our READY phase means; worth keeping it that strict. |

#### Steer versus follow-up, as the user sees it

| Finding | How pi does it | Ours, at the reading |
|---|---|---|
| **Two queues, two keys** | Enter steers: delivered after the current assistant turn's tool calls, before the next model call. Alt+Enter follows up: delivered only when the agent would otherwise stop (`docs/usage.md:63-74`, `docs/keybindings.md:159-166`, `docs/rpc.md:80-123`). `one-at-a-time` is the default for both: one message per turn, so a steer never bundles two changes of direction (`docs/rpc.md:361-395`). Messages typed during compaction queue separately and flush after it (`modes/interactive/interactive-mode.ts:222,466-467,3390`). | |
| **Escape aborts and hands the queue back** | `clear_queue` returns the queued texts and the client puts them in the editor before `abort` (`docs/rpc.md:137-158`, `interactive-mode.ts:1864,4158-4162`); Alt+Up pulls them back without aborting. | Ours dropped a still-queued row on Stop. |

#### Retry

| Finding | How pi does it | Ours, at the reading |
|---|---|---|
| **Session-level, abortable, announced with its delay** | `auto_retry_start {attempt, maxAttempts, delayMs, errorMessage}` then an abortable sleep (`agent-session.ts:2894-2946`, `abortRetry` `:2950`); the failed message is dropped from the model's context but kept in the session file (`:2913-2917`). The TUI counts the delay down (`modes/interactive/components/countdown-timer.ts`). | |
| **A Retry-After the harness will not wait for is a failure now** | pi-ai's provider retry honours `retry-after-ms` and `retry-after` (seconds or a date) and throws immediately when the server asks for more than `maxRetryDelayMs` (60 s by default) (`ai/src/utils/provider-retry.ts:36-66,96-104`); the schedule otherwise is 0.5 s × 2ⁿ capped at 8 s with 25 % jitter (`:65-66`). | We capped at 30 s and retried anyway. |

#### Compaction and the session tree

| Finding | How pi does it | Ours, at the reading |
|---|---|---|
| **Threshold and cut rules, written down** | Auto-compaction when `contextTokens > contextWindow - reserveTokens` (16k), checked after a tool batch lands and before a new prompt; keep the most recent 20k tokens; cut only at user, assistant, bash or custom messages, never at a tool result; a single turn bigger than the budget is split and gets two summaries merged (`docs/compaction.md:24-100`). `CompactionEntry {summary, firstKeptEntryId, tokensBefore, usage}`: the summariser's usage is counted in the session total (`:139-160`, `core/usage-totals.ts:38-70`). Context % is `null` after compaction until a fresh response, shown as `?` (`docs/rpc.md:590-596`, `modes/interactive/components/footer.ts:106-111`). | Ours showed the summariser's prompt as the thread's context. |
| **Sessions are trees** | Every JSONL entry has `id` and `parentId`; the leaf is the position; `/tree` moves it, editing an earlier message and resubmitting starts a branch, `/fork` and `/clone` make new files, labels name points, and leaving a branch can attach a branch summary at the new position (`docs/sessions.md:69-139`, `core/session-manager.ts:846-856`, `docs/compaction.md:160-215`). | Ours is linear; LangGraph checkpoints can fork, which is what Codex's `thread/fork` offers. |

#### Cost and cache, in the footer

| Finding | How pi does it |
|---|---|
| **The footer carries the bill** | `↑in ↓out Rcache Wcache CH92.3% $0.123` plus the context % (`modes/interactive/components/footer.ts:87-148`): cache hit rate of the latest prompt, cost including summaries, all from the session file. |
| **Cache misses are counted and blamed** | `core/cache-stats.ts` counts a miss per turn as prompt tokens that were in the previous prompt but were not read from cache, prices the waste at the paid rate minus the cache rate, and attributes it to an idle gap longer than the 5-minute TTL or to a model switch (`:1-12,60-92`); a compaction resets the baseline because the prompt legitimately changed (`:119-125`). Cost also breaks down by model with a "Tools/summaries" bucket (`core/usage-totals.ts:38-70`). |

#### What this validated in ours

| Confirmed | In ours |
|---|---|
| Steer at the next model call as the default | The queued row is released when the model takes it |
| Retry as a status with a countdown, `Retry-After` honoured | Same |
| The summariser's calls on the bill | `UsageTracker.feed` runs before the summariser skip in `stream_agent` |
| A failure kept in history and out of the model's context | Our `failure` event kind is their "keep in session, drop from agent state" |

#### What it exposes in ours

Rows marked done landed on 2026-09-05 with the reading.

| Size | Gap | Status | pi | Ours, at the reading |
|---|---|---|---|---|
| S | Stop hands queued messages back to the composer | done | Escape restores the queue to the editor | a row still marked queued was dropped with the run |
| S | A Retry-After beyond the cap is not waited for | done | fails immediately above 60 s | waited 30 s, retried, failed again |
| S | The gauge is unknown after compaction | done | `percent: null`, `?` in the footer | the ring showed the summariser's prompt as the thread's context |
| S | Cache hit share beside the cached tokens | done | `CH92.3%` | cached tokens with no share |
| S | An explicit "after this turn" send | open | Enter steers, Alt+Enter follows up, `one-at-a-time` | steer-if-possible only; a note meant for after the run interrupts it |
| M | Cache-miss attribution | open | idle beyond the TTL or a model switch, dollars wasted | none; on BYO keys a 5-minute pause silently re-bills the prompt |
| M | Compact once and retry on overflow (OpenCode does this too) | done (2026-09-05) | `isRecoverableLength`, one bounded attempt | `context_window` meant start fresh |
| L | Session tree | open | `/tree`, `/fork`, `/clone`, branch summaries | linear; LangGraph checkpoints can fork, as Codex's `thread/fork` does |
