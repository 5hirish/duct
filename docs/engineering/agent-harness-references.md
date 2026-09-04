# Agent harnesses we learn from

Three coding-agent harnesses are being built in the open, by teams that hit
every problem our agent shell hits — reconnect, resume, pauses that outlive a
process, streaming that does not flicker, errors a user can act on — a year
ahead of us and with more users. Reading them is cheaper than rediscovering
their answers. This file is the watch-list: which harness, why it matters to
us, the revision it was last read at, and the findings pinned to `file:line`
so a later reader can diff rather than re-read.

It is reference material, not rules. The rules that came out of a reading go
into the area `AGENTS.md`; this file records where they came from.

## The watch-list

| Harness | Repo | Why it matters to us | Last read |
|---------|------|----------------------|-----------|
| **Codex** (OpenAI) | `github.com/openai/codex` | The desktop and IDE apps are clients of `codex app-server`, a JSON-RPC server whose thread / turn / item contract is the most fully specified agent-UI protocol in the open. The desktop app itself is closed; the TUI in the same repo is the reference client. | `de78740`, 2026-09-04 — shallow clone at `../codex` |
| **OpenCode** (sst) | `github.com/sst/opencode` | TypeScript server + clients over a session / message / part model with an SSE event bus; provider-agnostic; closest in shape to our Next.js app talking to a backend. | not yet read |
| **pi** (badlogic) | `github.com/badlogic/pi-mono` | A deliberately small TypeScript agent loop and TUI; the reference for "how little harness do you need". Has explicit steer-vs-follow-up input modes and session trees. | not yet read |

## How to read one

- Shallow clone into the parent workspace directory (`git clone --depth 1
  --filter=blob:none`), never into this repo.
- Read the docs index and the protocol README's table of contents first; grep
  for the mechanism; read the 30–60 lines around the hit. Do not read whole
  files, and do not paste code here — a `file:line` at a named revision is
  the record.
- Update the table's "Last read" column. Findings below are dated by that
  revision; `git log <rev>..HEAD -- <path>` in the clone is how a refresh
  starts.

---

## Codex, at `de78740`

Paths below are relative to `codex-rs/` unless they start with `sdk/`.

### The contract a desktop client is built on

- **Three primitives, one item lifecycle.** Thread → turns → items. Every
  unit of work — user message, agent message, reasoning, command, file
  change, tool call, web search, plan, compaction — is an item in one tagged
  union (`app-server-protocol/src/protocol/v2/item.rs:237-416`), and every
  item goes `item/started` → deltas → `item/completed` (`app-server/README.md:1859`).
  Deltas carry the `itemId` from `item/started` so a client appends to the
  right thing (`item.rs:1421`, `:1433`, `:1490`). The TypeScript SDK reduces
  the whole protocol to eight events: `thread.started`, `turn.started`,
  `turn.completed`, `turn.failed`, `item.started`, `item.updated`,
  `item.completed`, `error` (`sdk/typescript/src/events.ts:76-85`,
  items at `sdk/typescript/src/items.ts:120`). *Our vocabulary is ~25 named
  events with a reducer case each; theirs is one lifecycle and a `kind`.*
- **Thread status is a pushed, subscribable state**, not a field the client
  infers: `notLoaded | idle | systemError | active { activeFlags }` with
  `waitingOnApproval` and `waitingOnUserInput` as the flags
  (`app-server-protocol/src/protocol/v2/thread.rs:1639-1656`), delivered as
  `thread/status/changed` (`README.md:651-668`). Thread listing returns the
  same status per row (`README.md:187`).
- **A turn ends in exactly one of `completed | interrupted | failed`**
  (`v2/turn.rs:32`), and a failure carries a typed `codexErrorInfo` —
  `ContextWindowExceeded`, `UsageLimitExceeded`, `rateLimitExceeded` (only
  after the retry budget), `ResponseStreamDisconnected { httpStatusCode }`,
  `ActiveTurnNotSteerable`, `Unauthorized`, `Other` (`README.md:1946-1967`).
  The client maps a code to copy and to the action it offers; it never
  pattern-matches message text.
- **Two ways to ask the user.** Blocking: `item/tool/requestUserInput` with
  `questions[] {id, header, question, options|null, isOther, isSecret}` and
  `isBlocking` (`item.rs:1733`, answers at `:1786`, doc `README.md:2027`).
  Non-blocking: an `agentMessage` with `delivery: "async"` and a `questions`
  array, where the reply arrives as an ordinary steer and the turn never
  stopped (`item.rs:250-260`, `README.md:1881`). Command and patch approvals
  are a third server→client request with sentence-shaped options
  (`README.md:1997-2023`); the full list of server-initiated requests is
  `common.rs:1698-1752`.
- **Pending requests belong to the turn and survive the connection.** A
  turn start, completion or abort fails every pending request with reason
  `turnTransition` (`app-server/src/bespoke_event_handling.rs:168,198,1211`;
  `outgoing_message.rs:185-200`); a client disconnect prunes only the
  connection's context, the callbacks stay keyed by thread
  (`outgoing_message.rs:242`, `:465`); and `thread/resume` re-sends every
  still-pending request to the new connection
  (`thread_lifecycle.rs:791`, `outgoing_message.rs:362`). Whatever cleared a
  request, the client hears `serverRequest/resolved { threadId, requestId }`
  (`notification.rs:74`) — so a second tab can drop its card.
- **Input during a turn is steered or queued, never refused.** `turn/steer`
  injects into the running turn with an `expectedTurnId` precondition
  (`v2/turn.rs:277-306`); `thread/queue/add` persists a follow-up with a
  client-provided `clientUserMessageId`, started when the thread goes idle,
  and an interrupted turn leaves the queue paused (`README.md:930-952`).
- **Liveness is a timer, and writes are exclusive.** A thread unloads 60 s
  after its last subscriber leaves *and* activity stops, runs `SessionEnd`
  hooks, then emits `thread/closed` (`README.md:677-684`). One process holds
  the write lock on a thread; a second `thread/resume` gets `-32600`
  (`README.md:473`, `thread-store/src/local/writer_lock.rs`). The desktop
  keeps all of this alive across app restarts with a daemon on a unix socket
  (`app-server-transport/src/transport/mod.rs:54-64`,
  `app-server-daemon/src/client.rs:63-70`).

### The loop underneath

- **One task per turn; steering is drained at the top of every model call.**
  All ops enter one channel (`core/src/session/handlers.rs:529`); spawning a
  task aborts the previous one with reason `Replaced`
  (`core/src/tasks/mod.rs:271-278`). A mid-turn message is appended to the
  turn's pending input (`core/src/session/turn_input.rs:553`) and drained
  before the next request is built (`core/src/session/turn.rs:337-345`);
  pending input alone forces another loop iteration (`turn.rs:470`).
- **Interrupt is cancel → grace → hard abort → tell the model.** Cancel the
  token, wait a graceful timeout, abort the join handle, clear pending
  approvals (`core/src/tasks/mod.rs:903-944`). Then an `<turn_aborted>`
  marker is written into model history and the rollout flushed *before*
  `TurnAborted` is emitted (`:947-964`, text at
  `core/src/context/turn_aborted.rs:10-11`), so the next turn's model knows
  tools may have half-run.
- **Retries are status, not errors.** The model stream retries up to
  five times (`model-provider-info/src/lib.rs:28-33`) with 200 ms × 2ⁿ jittered
  backoff (`core/src/util.rs:6-7,86`), emitting `StreamError
  "Reconnecting... n/max"` to the UI each time (`core/src/responses_retry.rs:102-121`);
  `will_retry` distinguishes a retry from a terminal failure.
- **Compaction is automatic, mid-turn, and visible.** Trigger computed after
  every sampling (`core/src/session/context_window.rs:56-118`), run inside
  the turn (`core/src/session/turn.rs:506-530`); the summary replaces history
  behind a token-budgeted tail of prior user messages
  (`core/src/compact.rs:670-760`), with `PreCompact` / `PostCompact` hooks
  around it (`core/src/hook_runtime.rs:528,565`). The UI gets a
  `contextCompaction` item.
- **The rollout keeps two streams in one file.** `ResponseItem` and
  `Compacted` rebuild model context; `EventMsg` rebuilds the UI
  (`history/src/lib.rs:114`, policy at `rollout/src/policy.rs:10-142`).
  Errors, warnings and deltas are never persisted. Resume scans newest to
  oldest for the last compaction checkpoint and replays only that tail into
  the model (`core/src/session/rollout_reconstruction.rs:133`); the UI
  replays only safe items with their event ids cleared so nothing fires twice
  (`tui/src/chatwidget/replay.rs:26-33`).
- **Token accounting subtracts a baseline** of 12 000 tokens so "% context
  left" reads 100 % after the first prompt (`protocol/src/protocol.rs:2394,2428`);
  `TokenCount` carries `{total, last, modelContextWindow}` plus a rate-limit
  snapshot (`:2318`, `:2251`) and is persisted and re-read on resume.
- **The plan tool goes straight to the UI.** `update_plan` parses
  `{explanation?, plan: [{step, status}]}` and emits `PlanUpdate` with an
  inert tool result (`protocol/src/plan_tool.rs:9-30`,
  `core/src/tools/handlers/plan.rs:93-97`). Same shape as our `Todos`.

### The UI on top (the TUI; the desktop app is closed)

- **Status row:** `Working (12s • esc to interrupt) · <detail>`
  (`tui/src/status_indicator_widget.rs:211-249`). The header is the first
  **bold** phrase of the current reasoning, so the model titles its own step
  (`tui/src/chatwidget/streaming.rs:246-273`); details sit under `└` capped
  at three lines (`status_indicator_widget.rs:41-42`); the interrupt hint
  keeps a fixed position and extra context is appended after it
  (`:245-263`).
- **Reasoning is hidden live and folded after:** deltas only drive the header;
  at block end the text becomes a dim bullet cell, and one without a bold
  title is transcript-only (`chatwidget/streaming.rs:232-290`,
  `history_cell/messages.rs:629-645`).
- **Streaming commits a stable region and keeps a mutable tail**
  (`tui/src/streaming/controller.rs:1-36`); one line per frame, flipping to
  catch-up with hysteresis under backlog (`streaming/chunking.rs:85-116`);
  pipe tables are held back until finalised because a new row reflows every
  column (`controller.rs:12-20`).
- **Approval options are sentences,** and "No" has a feedback path: `No, and
  tell Codex what to do differently` aborts and hands control back
  (`tui/src/bottom_pane/approval_overlay.rs:836-912`).
- **The question form** is multi-question with options plus a per-question
  notes field, a synthetic `None of the above`, a "submit with unanswered?"
  confirm, and for non-blocking asks a 60 s hidden grace then a 60 s visible
  countdown (`tui/src/bottom_pane/request_user_input/mod.rs:60-69,600-638`).
- **Errors:** a retry re-uses the status row and restores the previous
  header afterwards (`chatwidget/streaming.rs:301-311`); hard errors are a
  red `■` row, warnings a yellow `⚠` row (`history_cell/notices.rs:87,244`);
  rate-limit nudges at 50/75/90/95 % with a switch-to-cheaper-model modal at
  90 % (`chatwidget/rate_limits.rs:19,441-512`); compaction takes over the
  status row and leaves `Context compacted · 1m 12s` behind
  (`chatwidget/compaction.rs:6-56`).
- **Notifications** on turn completion are coalesced by priority and
  suppressed while the terminal is focused (`chatwidget/notifications.rs:6-23`,
  `tui.rs:99-102`).
- **Tool cells:** `Running` → `Ran`, exit code and duration on the result
  line, output truncated head+tail to five lines
  (`history_cell/exec_cell/render.rs:223-233,356-372,695-699`); MCP `Calling`
  → `Called server.tool` (`history_cell/mcp.rs:131-190`); plan steps `✔`
  struck-through, `□` bold for in-progress, `□` dim for pending
  (`history_cell/plans.rs:186-196`).
- **Queued input is shown under the composer** in three labelled sections —
  after next tool call, at end of turn, queued follow-ups — as `↳` rows
  (`bottom_pane/pending_input_preview.rs:88-175`); only one modal is ever
  visible, the rest wait in an interrupt manager
  (`chatwidget/interrupts.rs:17-58`).
- **The footer is a state machine** over composer state and whether a task
  runs (`bottom_pane/footer.rs:165-238`) and shows `N% context left`
  (`:1032-1044`). A failed transcript load degrades in place — "Earlier
  messages unavailable — scroll up to retry" (`tui/src/pager_overlay.rs:462`).

### What this validated in ours

The shell rebuilt on 2026-09-04 (`app/src/lib/agentSession.js`,
`app/src/hooks/useAgentSession.js`, `backend/agents/core/session.py`) already
matches Codex on the points that cost the most to get wrong: the thread is the
conversation and outlives the session; a parked pause is replayed to a
reconnecting client and the replay is not re-persisted; history is hydrated
before the live stream opens; the reconnect grace is the same 60 s. Nothing
here argues for redoing those.

### What it exposes in ours

Sized so the next person picks by appetite, not by scrolling. Rows marked
**done** landed on 2026-09-04, the same day as the reading; the "ours today"
column keeps what they replaced so the reason survives.

| Size | Gap | Codex | Ours today |
|------|-----|-------|------------|
| S | **done** — Typed error codes | `codexErrorInfo` enum → copy + offered action | `friendlyErrorMessage` regexes the message text (`agentSession.js:442`) |
| S | **done** (label + clock; step durations still open) — Elapsed time and activity label while running | status row + `Ran · 1.4s` | "Thinking…" and step chips with no clock; steps carry no timestamps |
| S | A `pause_resolved` event | `serverRequest/resolved` for every clearing reason | a second tab keeps a stale card; the runner knows when a pause resolves and says nothing |
| S | Completion notification when the tab is hidden | coalesced desktop notification, suppressed when focused | none; insights pipelines run for minutes |
| S | Hold back markdown tables until the block closes | `controller.rs:12-20` | `ChatMarkdown` re-renders the tail on every delta, so briefs reflow mid-table |
| S | "Reject, and say what to do instead" | the `No, and tell Codex…` option | `ChangeSetCard` has approve / reject only |
| S | Thinking folded to a title by default | transcript-only unless titled | `ThinkingMarkdown` shows the whole block inline |
| M | **done** — Token usage and context left; compaction made visible | `TokenCount` per turn, `N% context left`, "Compacting context" | insights already compacts silently through deepagents' `SummarizationMiddleware` (`backend/agents/insights/v1/runner.py:411`) and reports no usage. On BYO keys the user pays for what they cannot see, and the Heavy/Standard/Light tiers have no "switch to Light" moment |
| M | **done** (insights steers, content and audit queue) — Queue follow-ups while a turn runs | steer or `thread/queue`, shown as `↳` rows | input disabled while streaming; chat while parked is a 409 |
| M | One writer per conversation; status on the list route | writer lock + `thread/list` rows carry status | two tabs can each resume the same LangGraph thread; the desk has no badge because the state route is per-conversation only |
| M | Interrupted marker | `<turn_aborted>` written and flushed before the abort is announced | `stop()` deletes the session; the next resume's model has no idea tools half-ran |
| L | Item lifecycle instead of an event per kind | `item/started` → deltas → `item/completed` + `kind` | 25 event names; add the next kind as an item, not as three new names |
| L | Non-blocking questions | `agentMessage { delivery: "async", questions }` | every question parks the pipeline |

---

## OpenCode and pi — what to look for when they are read

- **OpenCode:** the session / message / part model and which events the SSE
  bus emits on part updates; how a client resumes a session and whether
  permissions (their approval prompts) survive a reconnect; the share page,
  which is a read-only replay of the same events — a test of whether the
  event stream alone can rebuild a transcript.
- **pi:** the agent loop's size and what it refuses to own; steer versus
  follow-up input modes and how each is shown; session trees (branching a
  conversation, which maps to Codex's `thread/fork`); how compaction is
  triggered and what the user sees.

Record the revision and the `file:line`s here when done, and move anything
that became a rule into the area `AGENTS.md`.
