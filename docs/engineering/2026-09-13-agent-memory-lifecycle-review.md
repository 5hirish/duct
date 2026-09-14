# Memory across the thread lifecycle

**Author:** Shirish Kadam · **Date:** 2026-09-13

Is memory fetched on an as-needed basis, or always? Both, by design — and that is the shape the field converged on. The three things that made it feel wrong on 2026-09-12 are implementation drift, not design: priming ran on threads that never read it, the always-on digest is mostly blind to the question, and after the opening turn nothing recalls automatically.

2026-09-13 · reviewed against `service/memory.py`, `service/memory_consolidation.py`, `agents/core/memory_tools.py`, `agents/core/deep_session.py`, `routes/agents.py` on `feat/drawer-feedback-and-engine-cleanup`, and the design in [2026-08-28-agent-memory-research.md](2026-08-28-agent-memory-research.md) · [2026-08-29-agent-memory-on-deepagents.md](2026-08-29-agent-memory-on-deepagents.md)

## 01 · The short answer

**The design is hybrid, and correctly so.** A bounded, always-present *digest* is rendered into the opening user turn (pinned · open · last 30 days · artifacts · relevant-to-this-question, at most 40 entries / 6,000 chars), the agent has `SearchMemory` / `GetMemory` for anything older or off the digest, and a background *consolidation* pass at session close writes what the session established. Every serious 2026 system has exactly these three parts under different names:

- **LangChain / deepagents**: memory files "loaded into the system prompt at startup", skills read on demand; writes "in the hot path" via a tool or "in the background" on a cron. Their own warning: "consolidating much more often than users converse just burns tokens on no-op runs."
- **Anthropic**: the memory tool's auto-injected protocol is "ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE", then *just-in-time* retrieval by lightweight identifiers; context editing clears re-fetchable tool results; compaction summarises what cannot be re-fetched.
- **Letta**: core memory blocks always in context, archival memory searched on demand, and a *sleep-time agent* that rewrites the blocks between turns so the primary agent never pays the latency.
- **Claude Code**: an index scan plus a selector returning at most five files "matching on what the question IS ABOUT", every recall stamped with its age, and an auto-dream after 24 h / 5 sessions.
- **ChatGPT**: went from an undated dossier to "Dreaming" — categorised, background-rewritten, time-aware — after admitting the old list "often became stale" and contradicted itself.

So "fetch on demand" alone is not the standard; **a small stable core plus on-demand retrieval plus background writing** is. Duct has all three. What it does not yet do well is decide, per turn, which few lines of the core are worth the model's attention — and that is what the "Recalled 16 memories" chip under a web-performance question was showing.

## 02 · What actually happens at each stage today

Read left to right: what the stage stores as evidence, what memory it reads, what memory it writes, what the user sees, and whether that matches the shape above. Line references are to the branch as of this review.

| Stage | Evidence stored | Memory read | Memory written | UI | Verdict |
| --- | --- | --- | --- | --- | --- |
| Fresh session open | `agent_events` USER row for the prompt; LangGraph checkpoint. | Off the request path, in the pipeline task on a worker thread: `seed_user_preferences` → `build_memory_context` (digest + opening alerts for watches/incidents the subject touches + user memory ≤12 + 5 prior report summaries + stored agent working context) → `touch_recall` on everything shown. Rendered into the USER turn with dated, citable ids. ~20 queries, ≈0.8 s against the remote DB. | Declared preferences seeded as user-scope rows. | "Recalled N memories" chip after PIPELINE_STARTED, before the first agent text. | matches |
| Reopen / resume | Transcript rehydrated from `agent_events`; checkpoint restored; parked pauses replayed. | Until 2026-09-13: the full priming ran and emitted the chip, but `run_session` discards the digest on a resume (the opening turn is the raw follow-up or nothing). Now: `memory = "" if is_resume`, no chip, no queries. | none | Was: an orphan "Recalled 16 memories" row between the restored history and the next message. Now: nothing. | fixed today |
| User follow-up (chat or steer) | USER row; on steer the HumanMessage is inserted at the next model call. | **Nothing automatic.** The model must call `SearchMemory` itself; the prompt rules tell it to before saying "unknown". The digest from turn 1 is still in context until compaction removes it. | Only if the model calls `RememberFact`. | No chip. Citations (`m_…`) appear in the answer if the model uses them. | gap |
| Data fetch (connector tool) | TOOL_USE (name + full input) and TOOL_RESULT (output, is_error) rows; result in the checkpoint until pruned. | none | none directly. Consolidation later sees only "agent called FetchData", not the numbers — a dated metric survives only if the agent states it in prose or calls `RememberFact`. | Data pane row (label, ok/error, provider sentence). | matches — re-derivable by rule; metrics are the deliberate exception and rely on the agent |
| Web search | The insights agent has no web-search tool; the audit agent crawls. Nothing to review here — listed because the question named it. | | | | n/a |
| Question / connect / account pause | QUESTION and ANSWER rows; interrupt in the checkpoint. | none | none (an answer is not a durable fact by itself; consolidation reads "user answered: …"). | Card in the transcript. | matches |
| Artifact written (brief version) | Artifact row + version; ARTIFACT_VERSION event. | none | `record_artifact_memory` (artifact-scope pointer entry) on every version; `extract_artifact_findings` lifts ≤6 findings (conclusion / incident / metric / watch) as *proposed* rows with the section they came from, when the report is summarised. | Artifact in the right pane; findings appear on the timeline as unconfirmed. | matches (Claude Code's "skip anything derivable" bar, with pointers instead of paraphrase) |
| Change set applied / reverted | Change-set rows. | none | `record_change_set_memory` → an `action` entry with applied/failed counts. | Execution UI. | matches |
| Context editing (prune) | Unchanged — `agent_events` is outside the context window. | none | none. Old tool results are dropped from the checkpoint before an LLM compaction is needed. | Context ring. | matches Anthropic's "clearing" |
| Emergency compaction | Unchanged. | none | none. `compact_thread` runs the stock summariser; the model is *not* asked to save durable facts first. The Anthropic cookbook's "save to memory before reset" is not needed here because the evidence store is not the context window — consolidation reads `agent_events`, so nothing is lost by compaction. | "Context compacted" notice. | matches, by a different route |
| Close · grace-close · idle | Recorder closed; a cancelled turn recorded as such. | Current digest, as context for the consolidator. | `schedule_consolidation` from all three close paths: a structured-output call over events since the `memory_through_seq` watermark (min 6 new events, ≤60k chars, ≤12 entries, 90 s timeout, one lock per project). Transcript = user / agent / answers / tool *names*; thinking and tool results dropped. Everything lands `proposed`; closes and archives, never deletes. Skipped when the session was opened with `remember: false`. | Timeline shows unconfirmed count; confirm / forget per entry. | matches LangChain background pattern and Letta's sleep-time agent, minus the "rewrite the core block" step (the digest is re-rendered from rows instead — better, it cannot drift) |
| Timeline edit by user | — | — | Confirm, forget, pause per project; supersession is code keyed on entity + attribute; secrets and instruction-shaped text scanned on write. | Timeline page. | matches claude.ai / ChatGPT controls |
| Cross-project | — | Project isolation absolute; user scope only carries declared preferences. | — | — | matches (Phase 4 still open) |

## 03 · Why "Recalled 16 memories" under a web-performance question

The digest renderer spends its budget in fixed sections, and only the last one looks at the question:

| Section | Selection | Cap | Query-aware? |
| --- | --- | --- | --- |
| Pinned | pinned rows by importance, then every `goal` / `decision` | 12 + 5 | no |
| Open | unresolved `incident` / `watch` / `status` | 10 | no |
| Last 30 days | ranked: relevance .40 · recency .25 (30-day half-life) · importance .20 · reinforcement .15 | 12 | no (relevance is 1.0 without a query) |
| Artifacts | artifact-scope pointers | 6 | no |
| Relevant to this question | FTS with time-aware expansion, ranked | 6 | yes |

On a freshly seeded project the "Last 30 days" section is the seed itself — the profile's competitor `entity` rows are all recent, all unrecalled-by-nobody-yet, and all equally important — so six competitors ride along with every question for a month. The chip then honestly reports "16", which reads as noise because 14 of them are the same 14 every time. Claude Code's rule for the same problem is the one to copy: recall matches "what the question IS ABOUT", capped at five, and the always-on part is a 200-line index, not the entries themselves.

This is also why per-turn recall matters more than the digest's size: the digest is a cold-start device. Once the thread is running, the model should be handed the two or three entries that the *current* message is about, not remembered as having been shown forty at the start.

## 04 · Findings

### fixed 09-13 F1 · Priming ran on resume and produced an orphan chip

Every reopened thread paid ~20 queries for a digest `run_session` then threw away, and the MEMORY_RECALLED event landed in the live stream between the restored history and the next message — attached to no turn, which is exactly the "random" placement reported. `routes/agents.py` now skips priming when `is_resume`.

### gap F2 · No automatic recall after the opening turn

Letta, Mem0 and Zep all retrieve per user message and hand the model a small context block each turn; Claude Code runs its selector per query. Duct recalls once, at open, then relies on the model to call `SearchMemory`. In a ten-turn thread the fifth question ("have we seen this CPA spike before?") depends on the model remembering a rule from a system prompt it read ten turns ago. Follow-up turns also produce no chip, so the UI cannot attribute a later answer to memory even when the model did search.

**Proposed:** on each chat/steer message, one FTS query (≈45 ms on the remote DB, in the worker thread the message already uses) for ≤4 entries the message is about, de-duplicated against ids already in the thread's context, prepended to that user turn as a short `<recall>` block, and emitted as a MEMORY_RECALLED event *carrying the client message id* so the chip attaches to that message. No LLM call, no latency the user notices.

### drift F3 · The digest is 34-of-40 query-blind

See §03. Not wrong for a cold start — every vendor keeps a stable core — but the core should be an *index* and the entries should follow the question.

**Proposed:** when a query is present, shrink the static sections (Pinned 5 · Open all · Last 30 days 4 · Artifacts 3) and grow Relevant to 12; exclude `entity`-kind rows from "Last 30 days" unless they match the query (they are reference data, not events); render the rest as a one-line-per-kind count ("+ 9 competitors, 3 decisions — SearchMemory to open") so the model knows what exists without reading it. Keep the 40/6k ceilings.

### drift F4 · Reinforcement only counts what the digest already showed

`touch_recall` runs on the priming set only; `SearchMemory` hits are never touched. The ranking's reinforcement term (.15, ceiling 10) therefore rewards whatever the static sections surface — rich get richer — and an entry the model actually went looking for gains nothing. One line in `memory_tools._search_sync`: touch the returned ids.

### ux F5 · The chip reports what was injected, not what was used

claude.ai and ChatGPT show the memories that *informed* an answer. Duct's chip lists the priming set, which after F3 will still be ~15 lines. The design already asks the model to cite `m_…` ids; the chip can split on that: entries cited in the answer first ("Drew on 2 memories"), the rest folded ("14 more in context"). Cited ids are already in the AGENT_MESSAGE text; the reducer can extract them without a backend change.

### note F6 · Dated metrics reach memory only through the agent's prose

Consolidation reads tool *names*, not results, so a fetched "Brand CPA $71 for 2026-08-01..14" is remembered only if the agent said it or called `RememberFact`. That is consistent with the "re-derivable" rule and keeps extraction noise down, but the design lists dated metrics as the exception. The cheap middle: include TOOL_RESULT rows for the metric-shaped fetchers in the consolidation transcript, truncated to their summary line, and let the consolidator decide. Watch the stale-fact rate before doing it.

### ok F7 · Compaction without a save step is fine here

The Anthropic cookbook prompts the model to save before clearing because its evidence lives in the context. Duct's evidence is `agent_events`, outside the window, and consolidation reads that at close — compaction loses nothing memory would need. Do not add a "save before compaction" prompt; it would double-write.

### ok F8 · Consolidation cadence

Session-close with a per-conversation watermark and a six-event floor is exactly the "match the cadence to usage" guidance from deepagents; a desk-opened thread that is reopened daily consolidates the new turns only. The 90 s timeout and one-lock-per-project keep it from piling up. No change.

## 05 · Side by side

| Property | Duct | LangChain / deepagents | Anthropic tool + cookbook | Letta | Claude Code | Zep |
| --- | --- | --- | --- | --- | --- | --- |
| Always-on core | digest in USER turn, ≤40 entries | memory files in system prompt | "view /memories" first | core memory blocks | MEMORY.md index ≤200 lines | context block (facts + entities) |
| Per-turn retrieval | opening only (F2) | agent tool / search | just-in-time by identifier | archival search per turn | selector ≤5 per query | hybrid search per message |
| Hot-path write | RememberFact, durable bar | edit_file / manage tool | create / str_replace | via sleep-time agent | save corrections + confirmations | add episode |
| Background write | consolidation at close, proposed status | cron consolidation agent | — | sleep-time agent | auto-dream 24 h / 5 sessions | graph extraction async |
| Time on facts | observed / valid_from / valid_to, absolute dates | — | — | — | age stamp on recall | validity windows |
| Provenance | source refs + seq ranges, ids cited | file path | file path | — | file per fact | episode links |
| Forgetting | close / archive, never delete; user forget | consolidation prunes | model deletes | block rewrite | prune index | invalidate edge |
| Recall shown to user | chip = injected set (F5) | — | — | — | — | — |

Benchmarks, for scale only: on LongMemEval an independent run measured Mem0 at 49% and Zep at 63%; vendors dispute each other's LOCOMO numbers. The survey literature now frames the lifecycle as Formation → Evolution (consolidation, forgetting) → Retrieval, with a security lifecycle of Write · Store · Retrieve · Execute · Share · Forget/Rollback. Duct's design already names every one of those stages; the gaps above are all in Retrieval.

## 06 · What to do, in order

1. **Per-turn recall lite (F2).** One FTS query per user message, ≤4 entries, de-duplicated, chip attached to the message. Backend: `routes/agents.py::send_message` beside `_refresh_autonomy`; reuse `search(query=…, time_aware=True, rank=True)`. App: MEMORY_RECALLED gains `client_message_id`; the reducer places the chip under that row. Half a day.
2. **Query-aware digest budget (F3).** `render_digest`: shrink static sections when a query exists, exclude `entity` from recent unless matched, add the kind-count line. Existing tests cover section disjointness; add one for the counts. Half a day.
3. **Touch on search (F4).** One line. Do it with #2.
4. **Chip semantics (F5).** App-only: split cited vs in-context. With the eval set from Phase 3, track chip click-through on cited entries — that is the number that says whether recall is helping.
5. **Metrics into consolidation (F6).** Only after the stale-fact rate is being measured; it is the one change here that can add noise.

None of this touches the write path, the schema, or the invariants in the design doc. It is all in how much of what is known reaches which turn.

## 07 · Sources

- [LangChain — Memory overview](https://docs.langchain.com/oss/python/concepts/memory) (hot path vs background) · [Memory for agents](https://www.langchain.com/blog/memory-for-agents)
- [deepagents — Memory](https://docs.langchain.com/oss/python/deepagents/memory) (always-loaded files, edit_file writes, cron consolidation)
- [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (just-in-time retrieval, progressive disclosure)
- [Claude Cookbook — Context engineering: memory, compaction, and tool clearing](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools) (check-memory-first protocol; 48% peak-context reduction across sessions)
- [Letta — Sleep-time agents](https://docs.letta.com/guides/agents/architectures/sleeptime/) · [Agent memory](https://www.letta.com/blog/agent-memory/)
- [Zep: A temporal knowledge graph architecture for agent memory](https://arxiv.org/abs/2501.13956) · [Mem0 vs Zep compared (2026)](https://vectorize.io/articles/mem0-vs-zep)
- [Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers](https://arxiv.org/abs/2603.07670) (2026 survey) · [A Survey on the Security of Long-Term Memory in LLM Agents](https://arxiv.org/html/2604.16548v1) (six-phase lifecycle)
- Claude Code auto memory and ChatGPT "Dreaming": as documented in [2026-08-28-agent-memory-research.md](2026-08-28-agent-memory-research.md) §02, unchanged since.
