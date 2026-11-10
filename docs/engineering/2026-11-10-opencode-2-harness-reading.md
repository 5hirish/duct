# OpenCode 2 went from last to tied for first: what to take

**Author:** Shirish Kadam · **Date:** 2026-11-10

On the Harness Leaderboard, which holds the model fixed and varies only the code around it, OpenCode moved from 35.5% to 52.0% between versions 1.19 and 2.2.6 while its cost per solved task fell from $3.35 to $0.45. This record reads the code behind that move, reads pi (the cheapest harness per solve) beside it, and ranks what Duct should copy from both.

| Harness (same models) | Score, 95% CI | Cost per trial | Cost per solve | Time per trial |
|---|---|---|---|---|
| **OpenCode 2.2.6** | 52.0% (49.1 to 54.8) | $0.15 | $0.45 | 29.6 min |
| mini-swe-agent 2.4.6 (bash only) | 50.7% (47.8 to 53.6), tied | $0.18 | $0.54 | 35.1 min |
| Claude Code 2.1.300 | 49.1% (46.4 to 51.9) | $0.15 | $0.52 | 38.6 min |
| Pi 1.2.0 | 48.7% (45.9 to 51.5) | $0.097 | $0.29 | 31.4 min |
| OpenCode 1.19.0 (replaced) | 35.5% (32.9 to 38.1) | $0.36 | $3.35 | not read |

## At a glance

- **The harness moves the score by 25 points on the same model**, and the cost per solve by 5x. It is a product lever, not plumbing.
- **OpenCode 2's lead is a tie, and part of the jump is a fixed handicap.** Version 1 ran through a bridge that dropped tool arguments and never compacted early.
- **Its efficiency is five habits**: a tiny stable prompt, changes sent as deltas, early cache-aware compaction, a reply budget per call, and oversized output spilled to a file.
- **Pi reaches the same habits with four tools and adds two of its own**: cache misses counted in dollars, and cache warming decided by expected value.
- **Duct already has about half of them.** The biggest gap is not a mechanism. Our eval gate has one case, so we could not see a move like this in our own harness.
- **Do the measurement first.** Six proposals are ranked below; none is code yet.

## Read the board with three cautions

The numbers are real and the method is careful: three attempts per task, confidence intervals, cost metered by a proxy outside the harness, every trajectory public. Three things still limit what the top row proves.

1. **First place is a statistical tie.** mini-swe-agent, Kimi Code and Hermes Agent carry the board's "tied with the leader" mark. A bash-only agent ties the most engineered one.
2. **Version 1 was handicapped.** It reached the model through a format bridge that ran multi-tool replies without their arguments, and it compacted only after the provider refused a request. Part of the 16-point jump is removing that.
3. **OpenCode 2 is the only row run under the newest rules**: the model's real context window, no reply cut by a provider default, DeepSWE fully offline, and a different week. The board says older rows were not re-run.

> **Why it matters:** the lesson is not "OpenCode's design wins". It is that settings a harness guesses wrong (window size, reply limit, when to compact) cost more points than its clever features earn.

## Five habits make it cheap

Each was read in the source at the revision in the Reference.

| Habit | What OpenCode 2 does | Duct today |
|---|---|---|
| **A tiny, stable system prompt** | 756 bytes. Tool guidance is added only for tools the run has. | Insights is about 6,989 tokens, stable and cached, but paid on every call. |
| **Changes as deltas** | The date, the environment and plugin instructions are appended as a short update at the next step. The prefix is never rewritten, so the cache holds. | Per-user text is already in the user turn. A mid-thread change to sources or memory has no delta form. |
| **Early, cache-aware compaction** | Compacts at 85% of the model's real window using the provider's token count, keeps about 15,000 recent tokens, and sends the summary request on top of the cached prefix. A background summary starts 60,000 tokens early. | Prune first, then summarise from an estimate; one emergency compaction on overflow. The floor is a fixed 170,000 tokens. |
| **A reply budget per call** | The reply limit is the room left in the window, recomputed each call. | Not done. |
| **Spill, do not cut** | Output past 2,000 lines or 50 KiB is saved to a file. The model gets the head and the path. | A lossless fold, then a cut at 60,000 characters mid-structure. |

Two more are worth knowing. OpenCode keeps its tool list unchanged on the last allowed step and forbids calls instead, so the cached prefix survives the limit. And it shows the model 12 tools, folding every MCP tool behind one; Duct's two fixed MCP tools are the same idea, already shipped.

## Pi is the cheapest per solve, partly by accident

Pi costs $0.29 per solved task against OpenCode's $0.45, at 3.3 points lower. It is the minimal design: four tools (read, bash, edit, write) and a one-sentence preamble.

> **Gotcha:** the board says Pi's low cost per call comes "mostly" from a wrong setting. It assumed a 128,000-token window on models that hold up to 1,048,576, so it compacted at about 112,000 tokens, and it capped replies at 16,384. Short context is cheap context.

That accident is the most useful finding for Duct. **When to compact is a cost dial, not only a safety valve.** On a million-token model, OpenCode's "85% of the window" means paying for 890,000-token prompts before compacting; Pi's accidental ceiling paid for 112,000 and lost about three points.

| Where the two agree (independently) | OpenCode 2 | Pi |
|---|---|---|
| Truncate tool output at the same size and save the rest to a file | 2,000 lines or 50 KiB | 2,000 lines or 50 KB |
| Clamp the reply limit to the room left, each call | 15% margin on the estimate | 4,096 tokens or 15% of the input |
| A structured checkpoint summary, updated rather than rewritten | Objective, decisions, work state, next move | Goal, constraints, progress, decisions, next steps |
| Prompt guidance only for tools the run has | Rendered per tool | Each tool contributes its own snippet and rules |
| Prompt changes sent as patches, never a rewrite | Hashed instruction deltas | Named sections, diffed |

Two designs arriving at the same five answers is stronger evidence than either alone. Those five go first.

Pi adds two things OpenCode does not have, and both are unit economics.

1. **Cache misses in dollars.** After each reply Pi computes the prompt tokens that should have been read from cache and were not, prices the difference, and names the cause (idle past the cache lifetime, or a model switch). The session summary shows "Cache Re-billed" with the amount.
2. **Cache warming as an expected-value bet.** Pi keeps a cache alive only when `chance of another request x cost of a miss - cost of the ping` is at least $0.05. It measured the chance of a request arriving while idle at 15% and found per-session estimates no better.

> **Why:** that formula says when warming is worth building. At Anthropic's usual cache prices (a write at 1.25x input, a read at 0.1x) a 15% chance clears $0.05 only when the prompt costs about $0.69 to send, roughly 230,000 tokens at $3 per million. On the cheap models most Duct runs use, it never clears. This is our arithmetic on Pi's formula, not a measurement.

## We cannot see this in our own harness yet

The board's real product is its method, and that is what Duct lacks.

| | Harness Leaderboard | Duct's eval gate |
|---|---|---|
| Tasks | 198 | 1 case |
| Attempts | 3 each, with a 95% interval | 3 on a pull request, 6 on `main` |
| Cost | per trial and per solve, metered outside the harness | median cost and model calls per trial |
| Noise control | rerun flips (23%) against harness-swap flips (29%) | none |
| A minimal baseline | mini-swe-agent, bash only | none |

The last row is the sharpest. Nobody has run a Duct brief on a bare loop with one data tool to learn whether our seven middleware layers earn their cost. On this board the equivalent experiment ended in a tie.

## What to do, in order

Each item goes through `prioritize` before any code. Sizes are S (a day), M (a few days), L (a week or more).

| # | Proposal | Size | Why this rank |
|---|---|---|---|
| 1 | **#532.** **Grow the eval to 15 to 20 cases and report cost per pass, tokens and calls per trial, with an interval.** Add a bare-loop baseline row. | L | Every later item is a guess without it. It also tells us whether items 2 to 5 are worth doing at all. |
| 2 | **#533.** **Spill oversized tool results to the scratch space** and return the head plus a path the agent can `grep`. | M | Removes the one place we still discard customer numbers. The scratch tools already exist. |
| 3 | **In #532 as measurement; display not filed.** **Report cache misses in dollars** per run: tokens that should have been cached and were not, priced, with the cause. | M | Pi's habit, and already an open gap in [the watch-list](agent-harness-references.md). On customers' own keys this is money they pay; it also tells us whether any caching work below is needed. |
| 4 | **#534, with 6.** **Compact at the lower of a share of the window and a token ceiling**, sized from the provider's count. | M | OpenCode's share protects small models (Kimi Code lost a third of its trials on one model to a wrong window). Pi's accidental ceiling is why it is cheapest. Use item 1 to pick the ceiling. |
| 5 | **#535 (idea).** **Audit the insights system prompt against a 1,000-token budget.** Let each tool contribute its own guidance, mounted only with the tool. | M | 7,000 tokens on every call is our largest fixed cost. Both harnesses build the prompt this way. Needs item 1 to prove quality holds. |
| 6 | **#534.** **Budget the reply limit per call** and keep tools defined at the call limit. | S | Both harnesses do the first. Cheap, and both prevent a failure rather than save tokens. |

Not recommended now:

- **Cache warming, in either form.** Pi's own formula says it pays only on large prompts and expensive models. Revisit when item 3 shows real re-billed dollars.
- **OpenCode's background summary.** It spends tokens on summaries that may never be used.
- **Code Mode and the Effect architecture.** Both need a runtime we do not have.
- **Cutting to Pi's four tools.** Pi's surface is small because a shell does everything. Duct deliberately has no shell; the lesson is fewer, broader tools, which `FetchData` over one catalog already is.

## Follow the people who measure, not the people who announce

Sources are in [the watch-list](agent-harness-references.md), under "People and boards we follow". Joel Niklaus's board is the first entry because its changelog, lab notebook and decision log are public and each one records a harness mistake we could also make.

## Reference

### What was read

| Source | Revision or date | Notes |
|---|---|---|
| Harness Leaderboard, `huggingface.co/spaces/joelniklaus/harness-leaderboard` | Space files as of 2026-11-10, board v0.1.3 | `README.md`, `CHANGELOG.md`, `docs/harness-settings.md`, `docs/blog/post.md`, `docs/blog/numbers.md` |
| OpenCode, `github.com/anomalyco/opencode` | `98e4b53` on `dev`, 2026-11-10 | The board pins 2.2.6 (2026-11-06). Line numbers below are from `dev` and may differ by a few lines in the pinned release. |
| OpenCode migration guide, `opencode.ai/docs/migrate-v1/` | 2026-11-10 | Three breaking changes: plugin API, server API and clients, terminal config. |

Table figures for OpenCode 2 and the 2.2.6-era rows come from the board on 2026-11-10; the 1.19.0 row comes from `docs/blog/numbers.md` (generated 2026-11-02).

### Findings pinned in OpenCode at `98e4b53`

Paths are under `packages/core/src/`.

| Finding | Where |
|---|---|
| The whole base system prompt, 756 bytes | `session/runner/prompt/system.txt` |
| Tool guidance rendered only for tools present | `session/system-prompt.ts:9-27` |
| Date and environment as instruction entries with `initial` and `changed` renderers | `instructions/builtins.ts:24-49` |
| Instruction changes as content-hashed deltas, frozen as chronological system messages | `specs/v2/session.md`, "Instructions Are Value Deltas" (repository root) |
| Reply limit = window minus measured input minus 1.15 x estimated new input | `session/model-request.ts:57-62`, `:95-101` |
| Compaction reserve: 15% of the window, at least 16,000 tokens | `session/compaction.ts:129-135` |
| Background summary: 60,000 tokens early, only while 30 s of cache life remains | `session/compaction.ts:154-162` |
| Summary request appended to the unchanged conversation so it reads the cached prefix | `session/compaction.ts:343-346`, `:455-456` |
| Summary template with required headings and one repair turn | `session/compaction.ts:173-212`, `:248` |
| After a "too long" rejection, retry at 85%, 70%, 50%, 35% of the rejected size | `session/compaction.ts:127` |
| Old images dropped in batches so the prefix holds between cuts | `session/model-request.ts:225-236` |
| Tools stay defined on the final step; calls are forbidden instead | `session/runner/llm.ts:274-275`, `session/runner/max-steps.ts` |
| Cache key is the session's affinity id; per-model cache TTL | `session/model-request.ts:326-328` |
| Tool output bound: 2,000 lines or 50 KiB, full text saved, marker names the path | `tool-output.ts:13-14`, `:70-95` |
| One tool result carries machine `output`, model `content` and UI `metadata` | `specs/v2/tools.md`, "Tools" (repository root) |
| MCP and namespaced tools default into Code Mode behind one `execute` tool | `tool/AGENTS.md`, "Registration" |
| Each step reloads history; no in-memory tool loop; orphaned calls failed on restart | `specs/v2/session.md`, "One Step May Have Several Physical Attempts" |

### Findings pinned in pi at `6273031`

Read on 2026-11-10 from `github.com/earendil-works/pi`. The board pins pi-coding-agent 1.2.0, so lines may differ. Paths are under `packages/`.

| Finding | Where |
|---|---|
| One-sentence preamble; tool list and rules built from each mounted tool's own snippet and guidelines | `coding-agent/src/core/system-prompt.ts:88-126`, `:151-160` |
| Prompt held as named sections; a change is a section patch | `coding-agent/src/core/system-prompt.ts:210-228` |
| Cache miss per reply: missed tokens, dollars, idle time, model change; 1,024-token noise floor | `coding-agent/src/core/cache-stats.ts:5-24`, `:57-70` |
| "Cache Re-billed" shown in the session summary | `coding-agent/src/modes/interactive/interactive-mode.ts:6949-6953` |
| Warming decision: `p x missCost - warmCost >= $0.05`, `p` = 0.15 when idle | `ai/src/cache-warming.ts:31-43`, `:84-106` |
| Warming replays the last request with a one-token reply; stops after 30 idle minutes | `ai/src/cache-warming.ts:34`, `:65-77` |
| Reply limit clamped to the window minus input minus a margin | `ai/src/api/simple-options.ts:15-35` |
| Compaction: reserve 16,384 tokens, keep 20,000 recent | `coding-agent/src/core/compaction/compaction.ts:126-130`, `:267-270` |
| Checkpoint summary template, and an update prompt that folds new messages into the old summary | `coding-agent/src/core/compaction/compaction.ts:507-583` |
| Summary carries the files read and modified | `coding-agent/src/core/compaction/compaction.ts:52-55` |
| Tool output: 2,000 lines or 50 KB; shell keeps the tail and saves the full output | `coding-agent/src/core/tools/truncate.ts:11-12`, `coding-agent/src/core/tools/bash.ts:283` |
| Paired evals: each case run with and without a change, repeated, reporting lift | `evals/README.md` |

How the board ran Pi (assumed 128,000-token window, 16,384-token replies, text only) is in the board's `docs/harness-settings.md` and its changelog entry of 2026-11-07.

### Duct's side of the comparison

| Fact | Where |
|---|---|
| Insights system prompt about 6,989 tokens | [agent-prompts.md](agent-prompts.md) |
| Summarisation floor fixed at 170,000 tokens; prune clears in batches to keep the cache | `backend/agents/core/deep_session.py` |
| Cache-miss attribution listed as an open gap since the September pi reading | [agent-harness-references.md](agent-harness-references.md), pi section |
| Emergency compaction keeps 20,000 tokens | `backend/agents/core/lc.py` |
| Connector payload cut at 60,000 characters after the lossless fold | `backend/agents/insights/fetchers.py`, `backend/agents/core/compaction.py` |
| One eval case; baseline records pass rate, median cost and median model calls | `backend/tests/eval/cases/`, `backend/tests/eval/baselines.json` |

### Not verified

- Whether Duct's system prompt or tool list ever changes mid-thread. If it never does, the delta habit buys nothing.
- What a Duct run looks like when it hits its model-call limit, and whether the tool list changes on that call.
- The paper the board's post cites for rerun noise (Liu and Han, 2026, arXiv 2610.04433) was not read.
