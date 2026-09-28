# Memory freshness: when a remembered state goes stale

**Author:** Shirish Kadam · **Date:** 2026-09-27

A remembered fact about an outside system ("Brand campaign is enabled",
"budget $50/day", "/pricing redirects to /plans") can be recalled weeks later
and stated as current after the system has changed. The measured case that
this is worse than no memory: under drift, append-only memory scored 0.21,
no memory 0.31, and keyed revocation 0.95 (TEPA, arXiv 2608.07429). Duct's
schema already has the right shape (bi-temporal validity, supersession by
state key, provenance), so this is not a new store. The gap is that nothing
tells the model **how old** an open state is, and nothing makes it re-read
the source before asserting one. Extends the 2026-08-28 research, the
2026-08-29 designs and the 2026-09-13 lifecycle review; does not re-research
them.

## Where Duct stands

**Already handled:** supersession in code by `entity_key|attribute|period`
backed by a partial unique index (`service/memory.py`, `models/memory.py`);
superseded rows hidden from search unless asked; `source_type` and
`source_refs` on every row; a prompt line that says to treat entries as
point-in-time and verify against fresh data; consolidation that can close a
state the session showed had ended.

**Where staleness leaks into an answer:**

1. **"present" asserts currency.** Every open, undated row renders as `<start> – present` with no age, so a 90-day-old "enabled" reads like this morning's. The design promised an "N days old" stamp; it was not built, and a test pins "present".
2. The Open section keeps any `status` row until something writes the same key, with no age limit and no "check it still holds" instruction (watches and incidents get one).
3. **Supersession needs a new observation.** If no session re-reads the campaign, the old row is current forever. The eval's 0% stale-fact rate measures only whether superseded rows are served, not drift at the source.
4. **Duct's own changes do not invalidate what it remembers.** A change set that pauses Brand records `change_set:<id>|state`, leaving `campaign:brand|status` saying "enabled".
5. Re-confirming a fact bumps `recorded_at`, not `observed_at`, so it still shows its first date and ranks as old.
6. **No re-runnable evidence.** `RememberFact` takes no evidence; refs name a conversation; `SOURCE_CONNECTOR` is defined and never written.
7. `entity_key` is free text, not normalised: `campaign:Brand`, `campaign:brand` and `campaign:1234` are three states, and a rename breaks the key.
8. Rolling periods (`last-28d`) render verbatim and read as current forever.
9. The recall chip carries no date.
10. The unattended brief uses the same context builder, and nobody reads it before it ships.

## What the sources do

| Mechanism | Source | Fit |
|---|---|---|
| Citations checked just in time before use; a confirmed memory is **stored again to refresh its timestamp**; a contradicted one is corrected | GitHub Copilot memory, 2026-01 | **High.** In Duct the citation is a connector entity plus a window, and re-storing is `remember()`: an identical fact merges, a different one supersedes. Take the refresh, not the 28-day deletion |
| Claims carry versioned evidence and are flagged stale when it changes; stale ≠ wrong | LangChain OpenWiki, 2026-08 | **Medium.** Live API data has no version; Duct's equivalent is a newer row or an applied change set on the same entity |
| Drift states: intact / changed / missing / unverified | mex | **High, for vocabulary:** "could not re-check" is not "contradicted" |
| Fresh evidence revokes the precedent under the same key | TEPA, 2026-08 | **High.** `state_key` is the key; the gap is getting fresh evidence written under it |
| Per-type decay | MemArchitect, 2026-03 | per-kind policy yes; pruning no — drop from the digest, keep searchable |
| Downstream conclusions flagged when an assumption is revised | Graph-native belief revision, 2026-03 | **Medium.** Shared `entity_key` is the edge; no new table |

## Design

### Volatility classes

Derived in Python from `kind`, `period`, `source_type` and the entity prefix.
No new column.

| Class | Rows | Policy | Digest line |
|---|---|---|---|
| Declared | goals, user-scope kinds, user-sourced entities | never ages; superseded when its source changes | `2026-07-01 – in force` |
| Event | events, decisions, milestones, actions, artifacts, metrics with an absolute period | immutable | the date or period |
| **External state** | `status`, agent-written entities, metrics with no or a rolling period | age shown; TTL by entity prefix; verify before asserting; refreshed by re-remembering; out of the digest after 4× TTL unverified (still searchable) | `seen 2026-08-14 · 44d · verify` |
| Open item | incidents, watches | today's opening check, plus `verify` past TTL | as now, plus the marker |
| Belief | conclusions | no TTL; `changed since <date>` when a newer row or an applied change set lands on its entity | plus the marker |

Starting TTLs, named constants to tune with the eval: campaigns, ad groups
and budgets 7 days; pages and sites 14; competitors and audiences 30; default
14. `freshness(row, now, entity_latest) → current | aging | verify | changed`
is a pure function `render_entry` calls, with `seen = max(observed_at,
meta.verified_at)`.

### Verify on recall

Only when the agent is about to state a `verify` or `changed` row as current,
never while building the digest (priming costs under a second; one GA4 pull
was measured at 45). The digest line names the read (`check: FetchData
campaign_performance`), and the session cache makes a repeat free. Outcomes,
all through `remember()`: the same value refreshes `meta.verified_at` (the
Copilot refresh); a different value supersedes; "could not re-read" is
answered "as of <date>, not re-checked" and never closes a row, since absence
of data is not evidence.

### Invalidation as code

- A change set also writes its target's state key (`set_campaign_status` → `campaign:<id>|status`, `source_type=system`); a rollback supersedes it again.
- `remember()` normalises keys (lowercase prefix, trimmed); tool descriptions steer the model to platform ids, with the name in the title.
- Consolidation sees the same freshness markers, so its `close` list can act on them.

### What the person sees

The recall chip reads "as of 14 Aug", and "may have changed" for `verify` or
`changed`, in words, not colour alone. The timeline shows "Last checked" and a
"Needs a re-check" filter. A `/preview` scene and `make i18n`.

### Prompt stanza

Cache-stable, no per-customer text; `make dump-prompts` after.

> Entries marked `verify` or `changed since` describe something outside Duct — a campaign's status, a budget, a redirect — as last seen on their date. Before you state one as current, re-read it (the `check:` hint names the read). If the fresh read agrees, RememberFact the same fact to refresh it; if it differs, RememberFact the new value with the same entity_key and attribute — that closes the old one. If you cannot re-read it, say "as of <date>" and that you could not check. Never write "currently" beside an entry you did not re-read this session. Goals, decisions and dated metrics need no re-check.

### Storage

No new table and no migration: freshness is derived at read time; the
verification stamp lives in `project_memories.meta`; the verification read is
already in `agent_events`; change-set invalidation reads
`execution_change_sets`. Promote `verified_at` to a column only if a sweep ever
has to filter on it in SQL.

## Smallest valuable version, then the rest

**S, about a day, no schema change:** `volatility()`, `freshness()` and TTL
constants in `service/memory.py`; the digest stops saying "present" for
external state and shows age and `verify`; a duplicate merge stamps
`meta.verified_at`, and rendering and recency read it; the prompt stanza; the
chip gets `observed_at` and `freshness`; a FRESHNESS axis in the eval.

**Later (M–L):** an optional `evidence` argument on `RememberFact` written as
`{connector, entity_id, window}` with `SOURCE_CONNECTOR`; change-set state
writes; key normalisation; `changed since` on beliefs; digest exclusion after
4× TTL; background re-verification in the sweep (needs server-side
credentials, which desktop-made Google connections lack); a live replay where
memory says "enabled", the seed says PAUSED, and the reply must fetch before
it claims.

**Eval addition, judge-free, in `tests/eval/memory_recall.py`:** a FRESHNESS
axis with `must_verify` (Brand status, Brand budget, the /pricing redirect, a
rolling-period metric) and `must_not_verify` (a CPA target, a Q2 CPA, June's
conversion rate) questions, scored on the rendered line: a **stale-assertion
rate** (today 100%, since every one says "present"; target 0) and a
**false-alarm rate** (target 0), plus a refresh round-trip and a
contradiction round-trip. Reported beside the existing stale-fact rate; they
answer different questions.

## Sources

- GitHub, Building an agentic memory system for GitHub Copilot, 2026-01-15 — https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/
- GitHub Docs, About GitHub Copilot Memory — https://docs.github.com/en/copilot/concepts/agents/copilot-memory
- LangChain, Building Self-Correcting Memory in OpenWiki, 2026-08-25 — https://www.langchain.com/blog/self-correcting-memory-openwiki
- TEPA: Revoking Stale Memories, arXiv 2608.07429 — https://arxiv.org/abs/2608.07429
- MemArchitect, arXiv 2603.18330 — https://arxiv.org/abs/2603.18330
- Graph-Native Cognitive Memory (belief revision), arXiv 2603.17244 — https://arxiv.org/abs/2603.17244
- Facts as First Class Objects, arXiv 2603.17781 — https://arxiv.org/abs/2603.17781
- StateMemBench, arXiv 2608.19652 — https://arxiv.org/abs/2608.19652
- Microsoft, STATE-Bench, 2026-05-19 — https://opensource.microsoft.com/blog/2026/05/19/introducing-state-bench-a-benchmark-for-ai-agent-memory/
- mex — https://github.com/mex-memory/mex
- Zep / Graphiti, arXiv 2501.13956 — https://arxiv.org/abs/2501.13956
