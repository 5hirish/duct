# Approvals and autonomy for execution

**Author:** Shirish Kadam · **Date:** 2026-09-27

Execution is the part of Duct people pay for: an agent turns a finding into a
change in Google Ads, GA4, GTM or Mixpanel. How a person approves that change
decides whether they trust it enough to keep paying. This record reads the
current flow against the 2026 evidence on agent permissions and on how
marketing tools automate, and proposes what to change. **The short version:
tier the risk in code, make approval a conversation (edit, reject with a
reason) rather than a stamp, earn autonomy from history instead of a settings
toggle, and close the loop with "did it work?", which is also the upsell.**

## Duct today

1. **Proposal.** `ProposeChanges` (`agents/tools/execution_tools.py`) → `propose_change_set` (`service/execution/service.py`): guardrails, OAuth scopes (a missing scope blocks), a dry-run preview that snapshots `current`, then per-change `auto_eligible`.
2. **Auto path.** A set applies without a click only if an agent proposed it, the project is `assisted` or `auto`, and every change is eligible: allowlisted, not destructive, reversible, guardrail- and preview-clean (`service/execution/policy.py`). One ineligible change holds the whole set. `auto` and `assisted` apply the same allowlist; `auto` only means fewer questions.
3. **Chat card** (`components/execution/ChangeSetCard.jsx`): title, account, the agent's free-text context, a diff per change, warnings, a "destructive" badge. **Approve & apply** is one click with no subset or edit; so is **Roll back**.
4. **Executions page** (`app/(app)/execute/page.jsx`): subset approval, approve and apply as separate steps, a red confirm for destructive changes, the autonomy panel, and a guardrails form taking raw `op_types` strings.
5. **Apply** takes a conditional-update lock, re-checks guardrails, scopes and drift, records per-change results, an activity row and an `action` memory. **Rollback** runs no drift check.
6. Only the proposer can see or approve a set; a reject carries no reason; an autonomy change is not written to the activity log.

### What each op can do

| Op | Gate today | Blast radius | Undo in practice |
|---|---|---|---|
| `google_ads.add_negative_keywords` | auto-eligible | cuts traffic | state reverts; lost conversions do not |
| `google_ads.add_keywords` | **auto-eligible** | **spends**: keywords go in ENABLED, any match type, optional uncapped CPC | state reverts; spend is sunk and Smart Bidding may re-enter learning |
| status ops, `pause_campaign` | approval | stops or starts spend instantly; not labelled destructive | reverts |
| `set_campaign_budget`, `set_campaign_bidding` | approval | money; bidding resets learning | the setting reverts, the learning reset does not |
| `ga4.create_key_event` | auto-eligible | changes conversion counting | reverts |
| `ga4.delete_key_event`, `archive_audience`, Ads link delete | destructive | tracking gaps, audience membership rebuilt from zero | partial |
| `gtm.upsert_tag/variable` | auto-eligible | workspace only, not live | full |
| `gtm.publish_version`, `rollback_to_version` | destructive | **changes the live site for every visitor** | republishes the prior version |
| `mixpanel.create_annotation` | auto-eligible | none | full |

### Gaps

- **G1.** `google_ads.add_keywords` is on the auto-apply allowlist, beside the file's own rule that anything moving money stays off it until numeric limits exist.
- **G2.** An agent may roll back any set at any autonomy level, including one whose rollback increases spend (un-pausing, restoring a budget) or republishes a GTM version, and rollback runs no drift check, so it can overwrite a manual change made since.
- **G3.** The same action carries different friction on the two surfaces (a GTM publish is one click in chat, a confirm on the Executions page), and the card's rollback reassurance is shown for every destructive op, including ones rollback cannot fully undo.
- **G4.** One binary "destructive" flag is the only risk label; pausing a campaign has none.
- **G5.** No edit; a rejection is forgotten, so the agent can propose it again.
- **G6.** Nothing checks whether an applied change worked.
- **G7.** Diffs name campaigns by id.
- **G8.** Only `execution_approved` is tracked client-side.

## What the evidence says

1. **Per-action approval becomes a rubber stamp.** Claude Code users approve 93% of prompts (Anthropic, auto mode, 2026-03). *For Duct:* the same card for every set trains the click.
2. **Block by scope; deny and continue.** Auto mode tells the agent why an action was refused and lets it carry on, escalating to a person after repeated denials. *For Duct:* split a mixed set so the independent low-risk changes proceed.
3. **Trust grows with use, and experienced users supervise rather than approve.** Full auto-approve rises from ~20% to over 40% of sessions with experience; interrupts rise too (Anthropic, *Measuring agent autonomy*, 2026-02). *For Duct:* earn autonomy from history; give experienced users undo and interrupt, not more prompts.
4. **Non-technical users write weak rules.** Pre-authored policies blocked 20 points less overreach than per-action approval; 114 of 140 rules were set to "ask" (arXiv 2608.27443, 2026-08). *For Duct:* the raw guardrails form is the pattern that failed; Duct proposes the rule, the person accepts it.
5. **Tier by risk, classify deterministically, bound grants.** Wildcard grants "should not be issued" (AWS Agentic AI Lens, AGENTSEC04-BP02).
6. **"Approve with changes" is a first-class answer.** The Claude Agent SDK has six responses; GitHub's coding agent iterates on review comments.
7. **Risk labels live in code, as untrusted hints to everything else.** (MCP, *Tool annotations as risk vocabulary*; OWASP LLM06 *Excessive Agency*)
8. **Advertisers switch off automation that widens reach first.** Google's auto-apply includes broad-match keywords and excludes budget raises, keeps an upcoming-apply queue and a history, and applies ad suggestions after 14 days unless reviewed. *For Duct:* G1 recreates the setting advertisers turn off first; a visible delayed-apply queue is a familiar pattern here.
9. **Silent automation breaks trust.** Complaints about Meta Advantage+ (secondary sources) are about defaults switched on and settings re-enabled. *For Duct:* promise in the UI that it never widens its own reach, and show every automatic change in one place.
10. **The market uses a review queue or a digest, sent to a role.** Optmyzr changes nothing without approval by default and sends suggestions on a schedule; HubSpot keeps a "Needs approval" inbox; Shopify Sidekick presents changes for review.
11. **Undo beats a warning.** "Never use a warning when you mean undo" (Raskin, 2007); automation complacency is not trained away (Parasuraman & Manzey, 2010).
12. **A reversible setting can have irreversible consequences.** Changing keywords or bidding restarts Google Ads' learning period, which rollback does not undo.
13. **Agents rarely ask at the right moment.** The best model fell from 89% to 24% on underspecified tasks, even with an ask tool (HiL-Bench, 2026-04). *For Duct:* a proposal with money attached that rests on an assumption asks first, whatever the posture.

## Recommendations

| # | Change | What the person sees | Effort | Measure |
|---|---|---|---|---|
| R1 | **Risk tiers on `ExecutorSpec`** (T0 note, T1 staged, T2 reversible tracking config, T3 moves spend, T4 live or irreversible) with `effects: {money, public, data_loss}`; auto-apply T0–T2 only; `add_keywords` off the allowlist now | one plain chip per row ("Staged only", "Moves spend", "Goes live", "Can't fully undo"); the same friction per tier on both surfaces | S + M | approval and rollback rate per tier |
| R2 | **Approve with edits, reject with a reason**: re-previewed edits, `original_payload` kept; a reason written as a `decision` memory on the entity | budget and CPC editable, keywords as removable chips; "Not this": wrong target / too aggressive / already done / not now | M | edit rate; re-proposal of a rejected entity within 30 days → 0 |
| R3 | **Batches and digests**: one set per account per run; background proposals to a Review inbox and a daily or weekly digest; sets expire after 7 days; project members can approve | "Apply all 6 low-risk changes"; T3–T4 each on their own row | M | time to decision; expiry rate |
| R4 | **Undo windows and delayed apply**: a `scheduled` status; T2 auto-applies wait a short window; approved T3 can be scheduled | "Applying in 10 min · Undo"; "Applies tomorrow 09:00 unless you stop it" | M | undo rate in the window |
| R5 | **"Did it work?"**: `ProposeChanges` requires `expected: {metric, direction, window_days}`; on apply, an annotation and a `watch` memory; after the window, a verdict | "Expected CPA down in 14 days → it fell 12%. Worked." / "No clear change" / "Worse → roll back?"; a monthly receipt of changes that helped | M–L | outcome win rate; share of sets with a verdict |
| R6 | **Earned autonomy**: consecutive unedited approvals per (project, op, account, target) earn an offered, scoped, expiring grant, revoked on any rollback; posture (how often it asks) kept separate from permission (what may apply) | "You approved all 6 negative-keyword sets for *Brand – ES* as proposed. Add them here without asking, up to 10 at a time?" and a revocable list of grants | M | grant acceptance; rollback rate after a grant |
| R7 | **Less fatigue, no rule builder**: tiers set the friction; dedupe; suppress rejected entities; one bid or budget change per campaign per learning cycle; a lock on an entity instead of the guardrails form | "Duct never touches this campaign" | S–M | prompts per project per week beside approval rate |
| R8 | **Never, at any autonomy, enforced in tests**: apply T4 without a click on that set; increase spend without a click (a rollback that raises spend included); roll back T3–T4 unprompted; act on a moved target (drift check on rollback); change a budget or bid past a % cap; touch a locked entity | — | S | `tests/test_execution_policy.py` |
| R9 | **Copy**: name the consequence ("Goes live for every visitor; rollback republishes version 41"); names and money, not ids; show the evidence ("8 terms cost €120 in 30 days, 0 conversions"); "Apply 3 changes"; "Done while you were away" with Undo | as described | S (+ `make i18n`) | — |

## What to measure

Server-side, from `execution_change_sets` and `activity_logs`, which are the
source of truth; client events are extras.

| Metric | Where |
|---|---|
| Approval rate per op and tier | available: change statuses + `change_set.approved/rejected` activity |
| Time to decision | available (`approved_at − created_at`); add `decided_at` |
| Edit rate | needs R2 |
| Rollback rate and time, by who applied and who rolled back | available: `change_set.rolled_back` + `applied_by` |
| Outcome win rate | needs R5 |
| Expired share | available: sets `proposed` for over 7 days |
| Auto-applied share, rollback rate after a grant | `applied_by='auto'`; grants once R6 ships |

## Next steps, by value over effort

1. **S, fixes:** take `add_keywords` off the allowlist; put an agent's rollback of T3–T4, and any rollback that raises spend, behind a click; add a drift check to rollback; tests for each.
2. **S, fixes:** the card copy, equal T4 friction on both surfaces, names and money instead of ids.
3. **S–M:** reject with a reason, a rejection memory, re-proposal suppression.
4. **M:** risk tiers and chips, and the approval/rollback-by-tier query.
5. **M:** "did it work?" v1: structured `expected`, a `watch` memory, an annotation, a verdict on the next run that touches the entity.

Then approve-with-edits, digests and the inbox, earned grants, delayed apply.
3–5 and later are new scope and go through `prioritize`.

## Sources

- Anthropic, How we built Claude Code auto mode, 2026-03-25 — https://www.anthropic.com/engineering/claude-code-auto-mode
- Anthropic, Measuring AI agent autonomy in practice, 2026-02-18 — https://www.anthropic.com/research/measuring-agent-autonomy
- Do User-Authored Permission Policies Improve Protection Against AI Agent Overreach?, arXiv 2608.27443 — https://arxiv.org/abs/2608.27443
- Claude Agent SDK, permissions and user input — https://code.claude.com/docs/en/agent-sdk/permissions , https://code.claude.com/docs/en/agent-sdk/user-input
- OWASP LLM06:2025 Excessive Agency — https://genai.owasp.org/llmrisk/llm062025-excessive-agency/
- MCP, Tool Annotations as Risk Vocabulary, 2026-03-16 — https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/
- LangChain, Two Different Types of Agent Authorization, 2026-03-23 — https://www.langchain.com/blog/two-different-types-of-agent-authorization
- AWS Well-Architected Agentic AI Lens, AGENTSEC04-BP02 — https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec04-bp02.html
- HiL-Bench, arXiv 2604.09408 — https://arxiv.org/abs/2604.09408
- Morris, Humans and Agents in Software Engineering Loops, 2026-03-04 — https://martinfowler.com/articles/exploring-gen-ai/humans-and-agents.html
- Google Ads Help: applying recommendations automatically; learning period; custom experiments — https://support.google.com/google-ads/answer/10279006 , https://support.google.com/google-ads/answer/13020501 , https://support.google.com/google-ads/answer/10683687
- Optmyzr, Automation in Rule Engine — https://help.optmyzr.com/en/articles/3076120-automation-in-rule-engine
- HubSpot, Review agent output — https://knowledge.hubspot.com/ai/review-agent-output
- Shopify, Sidekick — https://help.shopify.com/en/manual/shopify-admin/productivity-tools/sidekick
- Raskin, Never Use a Warning When You Mean Undo, 2007 — https://alistapart.com/article/neveruseawarning/
- Parasuraman & Manzey, Complacency and Bias in Human Use of Automation, 2010 — https://journals.sagepub.com/doi/10.1177/0018720810376055
