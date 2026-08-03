# Ads Intelligence — learnings from the Gads engagement

**Version:** v0.1
**Status:** Strategy note — informs the Ads Intelligence relaunch
**Date:** July 2026
**Author:** Shirish (with Claude)

> Product learnings from a live "Claude Code as PPC analyst" engagement (the private **Gads** repo: a Google Ads audit + remediation of a real SaaS account), applied to Duct's half-built `paid_ads` insights mode. TL;DR: the valuable product is not a ROAS brief — it is a **measurement-integrity audit with a mandatory cross-tool cross-check, followed by approval-gated execution**. Relaunch Ads Intelligence in that shape, on the agent-session + lead-magnet chassis already proven by the SEO audit.

---

## 1 · Context

**The Gads engagement.** A working repo (outside this monorepo) that turned Claude Code into the Google Ads analyst/operator for one live SaaS account: stdlib-Python fetch scripts (Google Ads REST/GAQL v24 + GA4 + GSC) → raw JSON → offline analysis → self-contained HTML audit reports → approval-gated account mutations, plus a set of reusable playbooks (SOPs) encoding PPC domain expertise. The audit found an account spending ~$792/mo whose Smart Bidding was optimizing toward ~10k/mo fake page-load "conversions" while the only real revenue event fired 0.1×/month.

**Duct's `paid_ads` mode today.** The engine is ~80% built and was historically the *default* code path: goals ([`goals/paid_ads.py`](../../backend/agents/insights/goals/paid_ads.py)), a rich synthesis prompt ([`prompts/paid_ads.py`](../../backend/agents/insights/prompts/paid_ads.py)), GAQL fetchers ([`service/google/fetch.py`](../../backend/service/google/fetch.py)), OAuth connector, 9 LangChain tools (5 Ads + 2 GA4 + 2 GSC), typed brief schema, and a frontend renderer ([`GoogleAdsReport.js`](../../app/src/components/GoogleAdsReport.js)). But the mode is `active=False`, there is no frontend route (only `insights/organic-growth/*` exists), and it is shaped as a **one-shot "generate a brief" wizard** — the old architecture, predating the agent-session pattern used by the SEO audit and content agents.

---

## 2 · What the engagement proved (learnings)

### L1 — Measurement-first is the wedge, not optimization

The account's problem was not bad keywords or bids; it was corrupted conversion signals (page-loads and YouTube views marked PRIMARY, the real purchase event nearly silent). Every downstream finding chained back to that. **A ROAS brief generated on corrupted data is confidently wrong.** The audit that *exposes* the corruption is the deliverable people react to — and broken measurement is the common case for SMB accounts, not the exception. Duct's paid-ads prompt does baseline classification, but the product should *lead* with measurement integrity: conversion-action sanity, tag presence, geo leakage, bot-pattern detection.

### L2 — The cross-tool cross-check is the "aha" — and it is literally Duct's thesis

The single most persuasive finding was independent of Google Ads' own reporting: GA4 showed ~2,800 paid sessions producing **$0 attributed revenue** while ~$2,900 of real revenue landed in Direct. That is the "Google Ads says X, GA4 says Y" pitch from [`product-plan.md`](product-plan.md) §02, proven on a real account. Duct already has GA4/GSC tools wired into the paid-ads goal allowlists — but in practice the pipeline stays single-source. **The cross-check must be a mandatory audit section, not optional enrichment.** It is the part of the report no other tool (including Google) has an incentive to show.

### L3 — The product shape is a session, not a report

The engagement's real arc was **audit → remediate → build → operate** (weekly negative sweeps, monthly refresh). Duct has already migrated everything else to that shape: the SEO audit and content agents run as streaming agent sessions on the shared split-workspace chassis. The half-built paid-ads feature is the last artifact of the one-shot architecture. Do **not** ship it by flipping `active=True` and generalizing the organic-growth wizard — ship it on the audit-agent pattern, where the frontend chassis is already paid for.

### L4 — Free audit is the lead magnet; execution is the upsell

This mirrors the existing strategy exactly (free SEO-audit lead magnet at `app/(public)/lead/seo-audit`; execution-upsell test). The Gads audit output sells itself: a plain-English TL;DR ("$792/mo for ~$1 of tracked conversion value"), P0/P1/P2 findings, and **dollars-recoverable framing** on every recommendation. Adopt that framing verbatim — findings priced in money, ranked, with a clear "what we'd fix first."

### L5 — Approval-gated execution is safe, real, and the paid tier

The engagement actually mutated the live account (created a Google Ads conversion action, published a GTM container) behind hard gates: everything built PAUSED by default, every mutation requiring an explicit "yes," non-negotiable guardrails written down so the agent never relitigates them (e.g. "never re-enable campaigns whose bidding history was trained on fake conversions"). This is the template for Duct's insight→action loop: each audit finding carries a **"Fix this"** action that opens an approval-gated execution session. Reads are free; writes are the product.

### L6 — Playbooks are portable domain expertise

The Gads SOPs encode battle-tested PPC judgment: the anti-Google-defaults checklist (Search Partners, Presence-or-Interest, broad match, auto-apply recommendations — all off), SKAG discipline, universal negative-keyword lists, RSA anatomy (15/4, single-pin), conversion-tracking setup, and an intent-checked negative-sweep procedure (pull search terms → judge SERP intent → propose with verdicts → wait for approval). Port this content into `prompts/paid_ads.py` as supplementary guides — it is months of domain expertise Duct does not have to re-derive, and it doubles as the review rubric for agent output (SOP-as-spec, SOP-as-rubric).

---

## 3 · Watch-outs

- **Onboarding friction is real.** Google Ads developer-token approval takes 24–48h, plus OAuth + MCC (`login_customer_id`) setup. The free-audit funnel needs a "connect now, audit lands in your inbox" async flow and/or a CSV-export fallback (which was the original [`google-ads-mvp-plan.md`](../mvp/google-ads-mvp-plan.md) v0.1 design anyway).
- **API version drift.** Duct's entity catalog was audited at Google Ads API **v18**; the Gads scripts run **v24** (with version-probe fallback). Do a compatibility pass on `catalog/google_ads.py` and the GAQL fetchers before relaunch.
- **The DIY threat cuts both ways.** Gads proves a sophisticated operator can build this with Claude Code and zero dependencies in a weekend. Duct's moat is not the analysis — it is packaging (no setup), multi-tenancy, managed connectors, and the **recurring operate loop** (weekly sweeps, anomaly alerts), which is also the retention product. Position accordingly.
- **Distrust platform-reported metrics by default.** A hard-won Gads rule: treat "conversions" columns with suspicion until conversion goals are verified clean. Encode this as a standing directive in the audit prompt.

---

## 4 · Recommended relaunch shape

1. **Free "Google Ads Account Audit" agent.** Measurement-integrity first, GA4 cross-check mandatory, dollar-quantified P0/P1/P2 findings. Built on the agent-session + public lead-magnet pattern proven by the SEO audit (`backend/agents/audit/`, `app/(public)/lead/seo-audit`), registered in `backend/agents/registry.py`.
2. **Reuse the existing paid-ads engine as the tool layer.** `agents/insights/{goals,prompts,tools}` + `service/google/fetch.py` + the connector in `service/google/ads.py`; port Gads playbook content into the prompts. The one-shot `insights/generate` wizard for paid ads stays retired.
3. **Execution as the paid tier.** Approval-gated fixes — conversion-action repair, geo lockdown, negative sweeps, pausing junk spend — following the paused-by-default + explicit-approval safety pattern, per the execution-upsell strategy.
4. **Defer Meta/LinkedIn.** No connectors exist; single-platform depth beats the cross-platform promise the marketing page (`site/for-paid-ads.html`) currently over-advertises. Revisit after the Google Ads audit funnel converts.

---

## 5 · Execution roadmap (added 2026-07-31, from Gads round 2)

The second stretch of the Gads engagement (Jul 21–31) produced **zero Google Ads mutations** — all effort went into measurement plumbing (GA4 admin repair, GTM enhanced-conversions fix, a Mixpanel↔GA4 cross-check that caught a `signup`→`sign_up` rename silently dropping 174 conversions/month). That is the measurement-first thesis (L1) playing out: you don't touch bids on a corrupt signal. What it contributes to Duct is execution *patterns and preconditions*, not portable code (no Ads mutate code exists to port; the campaign/negative/audience builders remain prose specs in the playbooks).

### Principles

- **Staged execution (two-phase commit).** The engagement's one real write surface — GTM — demonstrated the model twice: create a named workspace → stage variable/tag mutations → diff → an explicit, separate publish step (one workspace published live, one deliberately held). Generalize this as Duct's execution primitive for every connector: *propose → render diff/preview → human approves → apply → verify → keep a rollback handle*. Google Ads has no workspace concept; the analogue is paused-by-default entity creation.
- **Gates must be machine-enforced.** In Gads the entire safety layer is prose (`CLAUDE.md` rules, a `# mutation (ask first!)` comment) that the agent happens to read. A SaaS cannot ship that. Dry-run payload rendering, per-entity approval, and per-account **guardrail invariants** (e.g. "never re-enable the paused PMax campaigns — bidding history trained on fake conversions") persisted in the DB are exactly Duct's value over DIY-with-Claude-Code.
- **Measurement-trust precondition.** Execution on bids/budgets/keywords is locked until the audit's measurement-integrity checks pass. This also gives the funnel its narrative: *the free audit is how an account earns the right to execution*.
- **A work order is an execution artifact.** A large share of fixes land where no API reaches (product code, consoles). Gads shipped a fully-specced engineering ticket (tasks, acceptance criteria, QA plan) and an action table with owner + minutes-to-fix columns. Duct can generate these today with zero new API surface.

### Phases

1. **Staged-execution framework** on the agent-session chassis: generic change-set model (propose/diff/approve/apply/verify/rollback), approval UI in the workspace right pane, guardrail-invariant storage per account.
2. **First executors — measurement repair** (low blast radius, real write APIs already proven in Gads): GA4 key-event create/delete + event-name-mismatch repair; GTM workspace/tag fixes; work-order ticket generation for what APIs can't reach.
3. **Ads executors behind the trust gate** (from playbook specs): universal negatives + search-term sweeps, geo lockdown (presence-only + country exclusions), pausing junk spend, budget changes — every entity created PAUSED, every mutation individually approved.

### Constraints to encode

- Execution needs the `adwords` **write** scope (already requested by our OAuth) plus a **Basic-access** developer token — the BYO token flow is therefore also the execution enabler; detect and surface the token's access tier on the Connections card (Explorer tier can't even use `KeywordPlanIdeaService`).
- Dev-token↔Cloud-project pairing is permanent on first API call — warn BYO users before their first request.
- GTM API is ~0.25 QPS (sleep ~5s between calls); GA4 v1alpha endpoints need per-call failure isolation.

---

## 6 · Related docs

- [`product-plan.md`](product-plan.md) — core thesis (§02) and vertical matrix (§04)
- [`../mvp/google-ads-mvp-plan.md`](../mvp/google-ads-mvp-plan.md) — original data contract & section model
- [`../engineering/google-ads-api-tool-design-document.md`](../engineering/google-ads-api-tool-design-document.md) — Google API-access compliance doc
- [`../gtm/paid-growth-plan.md`](../gtm/paid-growth-plan.md), [`../gtm/ads-launch-readiness-audit.md`](../gtm/ads-launch-readiness-audit.md) — Duct's *own* paid GTM (separate thread; informs what the feature should surface)
