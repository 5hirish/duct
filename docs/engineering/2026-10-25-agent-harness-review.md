# The agent harness holds at its boundaries and leaks at its seams

**Author:** Shirish Kadam · **Date:** 2026-10-25

Six parallel reviews of the agents, the harness, the app shell and the desktop shell found every named boundary intact and the leaks at seams nobody had named. Fix five things first: a conversation id trusted across projects, a post published twice, a prefix cache broken on every call, a run killed by leaving the page, and an over-granting desktop capability.

File, line, fix and test for each finding: [`2026-10-25-agent-harness-review-findings.md`](2026-10-25-agent-harness-review-findings.md). Security detail stays in the private repository until fixed.

2026-10-25 · at 84630151 on `feat/mcp-connectors` · offline suite: 1,062 passed before the first failure, a local-environment leak · deepagents 0.7.23 of 0.7.32, langchain 1.4.3 of 1.4.7, langgraph 1.2.12 of 1.2.17, mcp current

## At a glance

- **Security: 14 findings, 4 high.** Two in the API (a cross-tenant conversation read, an unbounded fetch) and two in the desktop shell (the hosted origin gets more than the keychain). Every boundary the rulebook names held.
- **Correctness: 1 high, 6 medium, 10 low.** The high one publishes a post twice and orphans the first.
- **Libraries: behind on everything but `mcp`, broken by nothing.** Three PRs in a fixed order.
- **Performance: the two biggest levers are one argument each.** Batch the tool-result pruning; keep the cache alive for an hour.
- **Shell: ahead on memory and pause cards, behind on the loop.** Runs die on navigation, sub-agents are invisible, cost is computed and never shown.

## Fix first

Ranked by failure prevented or money saved, over effort. Security rows name the class, not the path.

| # | Change | Area | Effort |
|---|---|---|---|
| 1 | Conversation resolution checks the conversation's project against the authorised one | security, API | S |
| 2 | Desktop capability grants the app commands and notifications only, not `core:default` and `opener:default` | security, desktop | S |
| 3 | A post that already has a PostBridge id cannot be published again | bug, content | S |
| 4 | Tool-result pruning clears in batches, so one prune buys several calls | perf | S |
| 5 | Web fetch stops reading at the byte cap instead of after the body | security, harness | S |
| 6 | The audit thread is keyed on the conversation, not the session | bug, audit | S |
| 7 | Leaving the page detaches from a run instead of deleting it | UX | M |
| 8 | Bump langgraph, then core and langchain, then deepagents | libraries | M |
| 9 | Keychain commands in the shell leave the main thread | desktop perf | S |
| 10 | A model fallback never steps up in price | bug, models | S |

## Security: two seams, not the walls

The reviews went after the three things the rulebook guards: untrusted data reaching the model, credentials reaching anything, and the model reaching side effects without a human. The guards held.

- **Held:** SSRF checks on every redirect hop, PKCE sign-in with single-use state for MCP, no tool that can approve or apply a change, artifacts and memory scoped by project, no unsafe deserialisation.
- **Leaked, API:** a conversation is loaded by id with no check that it belongs to the project the caller proved membership of. A fetched page is read whole before the size cap applies, an out-of-memory on a one-gigabyte container.
- **Leaked, desktop:** the hard parts (updater signatures, keychain separation, the sidecar's loopback bind) are right. The capability file hands the hosted origin two permission sets nothing uses.

## Correctness: the content agent carries the risk

Publishing is the one high finding. Nothing stops a second `publish_post` on the same post, so a model that calls it once per channel creates two PostBridge posts and loses the handle to the first. The route has the same hole.

- **Content holds connections open** across image and publish calls: pool exhaustion under a slide phase.
- **Audit keys its checkpoint thread on the session,** so a resumed audit never sees its own history.
- **Manual connectors mislabel the window:** an August ask returns September data captioned August.
- **One fallback is dearer than the model it replaces,** and content uses it as the cheap research model.
- **One test fails only on a developer laptop:** its "unconfigured" settings still read the GitHub App values from the environment.

## Libraries: three PRs, in order

Every package but `mcp` is behind, and the delta changes none of Duct's calls. The harness profile files are byte-identical across the nine deepagents releases.

- **The bumps buy:** resume fixes on the exact path the pauses run, checkpoint pruning, a summariser that survives its own overflow and strips stale reasoning blocks, and a closed advisory.
- **They do not buy** anything on the rulebook's gap list. Every API those gaps need already ships in the installed versions.
- **Order:** langgraph with its checkpoint packages, then core and langchain with the provider partners, then deepagents alone. Dependabot groups all of it into one PR; do not take it.

## Performance: the cache first, then the verifier

Past 120k tokens the harness clears one tool result per model call, so the cached prefix breaks on every call for the rest of the brief. One argument fixes it.

- **The cache dies while the user reads.** The caching middleware hardcodes a five-minute lifetime; the chat idles for thirty. The first follow-up rebuilds the whole prefix.
- **The verifier is 66 s of 198.** It fetches one entity per turn and inherits the analyst's thinking effort. One turn at lower effort is the next lever, sized by a trace.
- **Database rows matter in dev only,** where the proxy costs 45 ms a trip. One exception: the checkpointer runs every session through one connection under one lock, and nothing ever deletes a thread.
- **Measure first:** cache reads against cache writes per call across one real thread, from the usage rows already stored.

## Shell: what every other harness now does

Read against the October changelogs of Claude Code, Codex, OpenCode and pi. Duct is ahead on memory undo and freshness, pause cards, typed errors and settled streaming. Four gaps are now table stakes elsewhere:

- **Runs survive navigation.** Duct's unmount sends a delete, and the run is cancelled. Opening Connections mid-brief kills the brief.
- **Sub-agents are visible.** Duct shows one row with a summary; others show a live line per sub-agent.
- **Cost per turn is shown.** Duct computes it and the ring tooltip omits it on purpose, while the app guide says the opposite.
- **The composer points at things.** No `@` for a source, memory or brief, no drafts, no Esc to stop.

The ranked list of thirteen improvements and fifteen UI defects is in the findings record. Three delight ideas specific to a marketing agent: a "since last time" divider that says what moved, receipts on every cited number, and "watch this" on any finding.

## Desktop: async the keychain, keep the sidecar on a leash

- **Keychain and file commands run on the main thread,** and the app reads up to five keys per API request. Marking the commands async and caching the shell info is the quick win.
- **The sidecar cannot notice its parent dying,** so a crash leaves a Python process holding the database and port.
- **A cold-start deep link is dropped** on Windows and Linux.

## Housekeeping

- Rulebook gaps 1 to 9 and 12 have no GitHub issue. Each goes through `prioritize`.
- The harness references doc: the thinking-fold row is done, the Codex clone beside the repo is gone, and OpenCode dropped session sharing.
- The app guide and the context ring disagree about whether cost is shown.

## Addendum, 2026-10-26: what landed

Every fix the review asked for merged the same evening, as one PR per concern (#385 to #410, #389 skipped): the two security seams, the content agent's publish and thread fixes, the three library bumps in order, the cache and crawl work, the shell copy and progress fixes, and the desktop capability trim, navigation guard, async keychain and sidecar leash. The rulebook rows those PRs closed are struck in `agent-engineering.md`.

Three follow-ups are in review: the sidecar now receives its secrets on the pipe it already holds rather than in its environment (#418); a writer tool executed twice for one call, which a run continued from its checkpoint does, writes once (#419); and a run outlives the page that started it, with a pulse in the sidebar and Stop as the only cancel (#420). Still open, as listed in the findings record: the MCP response bounds and the approval card's server-authored title, the self-host entitlements, and the structural desktop change that keeps provider keys out of page scripts altogether.

## How this was done

Six read-only passes ran in parallel on 2026-10-25, each briefed with the rulebook and told not to re-report its open gaps. Each area's headline finding was re-read by hand before this record was written. The test suite ran once and stopped at its first failure, so later tests are unverified for this run.
