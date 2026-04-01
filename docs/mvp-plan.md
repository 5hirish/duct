# Duct MVP Plan — Engineering & Product

**Version:** v0.1
**Status:** Approved · March 2026
**Authors:** Marvin, Shirish

> This document covers the technical stack decisions, OSS tool choices, and build sequence for the Duct MVP. It is the companion to `product-plan.md` — that document covers the what and why, this one covers the how.

---

## Architecture

Data lives in the client's own destination. Client self-manages Airbyte to sync their source tools to their own Postgres/BigQuery/Snowflake. Duct connects to that destination with read-only credentials, synthesises with Claude API (using the client's own API key), and delivers the brief.

```
Client's source tools (Mixpanel, GA4, HubSpot, Salesforce, Intercom, Linear)
         ↓  Airbyte — client-owned, client-managed
Client's destination (their Postgres / BigQuery / Snowflake)
         ↓  DuckDB + Ibis — Duct reads with a read-only connection
Duct synthesis layer (Python + Claude API + Instructor)
         ↓
Delivery: HTML email (Resend) + Slack webhooks
```

**BYOK model:** For MVP, clients bring their own Anthropic API key. Duct is the platform and orchestration layer — not the AI cost centre. Duct infra cost at 10 customers: ~$10/mo.

---

## OSS Tool Stack

### Data Ingestion — Airbyte (client-owned)

Client sets up Airbyte (Cloud or self-hosted) to sync their tools to their own destination. Duct only needs a read-only connection string to that destination. Zero Airbyte infra for Duct to run or maintain.

**Connector status for target tools:**

| Tool | Airbyte Status |
|---|---|
| GA4, Search Console | Strong — incremental sync |
| HubSpot, Salesforce | Strong — incremental sync |
| Intercom | Good — incremental sync |
| Mixpanel | Partial — 60 req/hr limit, user profile stream re-fetches everything |
| Linear | Weak — full refresh only, requires Linear Plus plan |

**Early pilots (before clients have Airbyte set up):** Use **PyAirbyte** (`pip install airbyte`). Runs the same connectors directly in Python with no Docker or infrastructure. Data lands in a local Postgres or DuckDB. Use for Phase 2 manual delivery — swap out for client-managed Airbyte in Phase 3.

---

### Query Layer — DuckDB + Ibis

**DuckDB** reads from any client destination without moving data. Connects to Postgres, BigQuery, Snowflake, and S3/Parquet via extensions. Runs in-process — zero infra, ~150MB memory regardless of query size.

**Ibis** is a Python DataFrame API that translates to the right SQL dialect per backend. Write signal queries once — they run on Postgres, BigQuery, or Snowflake identically. If a client switches destinations, zero code changes needed on Duct's side.

---

### Transformation Layer — dbt

Airbyte lands raw data as JSON blobs in `_airbyte_raw_*` tables. dbt normalises these into clean, typed models with standardised column names across all source tools. Duct's synthesis layer queries dbt models — never raw Airbyte output.

- One staging model per source tool
- One marts model for cross-tool signal joins
- dbt tests catch broken connectors before synthesis runs
- Dagster understands dbt model dependencies natively as assets

---

### Orchestration — Dagster

Dagster (over Prefect) chosen because:

- Asset-based model — "the weekly brief for customer X" is a managed asset with full lineage
- Native dbt integration — dbt models are first-class Dagster assets
- `dagster-airbyte` integration — can trigger client Airbyte syncs as part of the graph
- Observability UI shows exactly which data sources went into each brief
- Self-hosted, Apache 2.0, ~10k GitHub stars, production-ready

---

### Synthesis — Claude API + Instructor

**Instructor** wraps Claude API calls to return typed Pydantic objects. A `WeeklyBrief` Pydantic model defines the exact output structure (critical signals, cross-tool findings, recommended actions, impact estimates). Claude returns a validated, structured object — no JSON parsing, automatic retry on validation failure, type-safe rendering.

This enforces brief consistency at scale. The prompt templates are the core product IP — vertical-specific (PM brief, RevOps brief) and iterated with pilot customers before automation is built.

---

### Delivery

**Resend** — transactional email, 3k emails/mo free tier, clean REST API. The HTML email brief is the primary customer-facing surface. This is where design investment goes — not a dashboard.

**Slack Incoming Webhooks** — customer pastes a webhook URL during onboarding. No OAuth, no infra. Anomaly alerts delivered as Slack Block Kit messages with full signal context.

---

### Auth + Workspace — Supabase

Supabase (open-source Firebase): Postgres for workspace and brief storage, Auth for Duct app login (magic link + Google OAuth), row-level security ensures customers only see their own data. Free tier covers the first 20 customers.

---

## Full Tool List

| Layer | Tool | Licence | Why |
|---|---|---|---|
| Data ingestion | **Airbyte** (client-managed) | MIT | Client owns their data pipeline |
| Early pilot ingestion | **PyAirbyte** | MIT | No infra, connectors run in Python |
| Query layer | **DuckDB** | MIT | In-process, connects to any destination |
| Multi-DB API | **Ibis** | Apache 2 | Write once, any backend |
| Transformation | **dbt** | Apache 2 | Normalise Airbyte output, data tests |
| Orchestration | **Dagster** | Apache 2 | dbt + Airbyte integration, asset lineage |
| Structured LLM output | **Instructor** | MIT | Typed Pydantic briefs from Claude |
| Auth + DB | **Supabase** | Apache 2 | Postgres + Auth + RLS, managed |
| Email | **Resend** | Free tier | 3k/mo, simple REST API |
| Alerts | **Slack Webhooks** | Free | No OAuth needed |
| AI model | **Claude API** | Client BYOK | Client brings their own Anthropic key |

---

## Visualisation & Dashboard

Duct's positioning: no dashboard to log into — briefs come to you. Visualisation is secondary.

**Layer 1 — MVP:**
- HTML email brief — the primary product UI. Design matters here.
- Slack Block Kit alerts — rich messages with signal context and recommended action

**Layer 2 — Brief archive (Phase 3, only if customers ask):**
**Evidence.dev** (MIT) — BI as code. SQL + Markdown renders to polished static pages. Connects to Supabase Postgres. Each customer gets a private brief history page deployed as static HTML — no dashboard to operate.

**Layer 3 — Signal exploration (Phase 4, only if customers want drill-down):**
**Lightdash** (MIT) — built for dbt teams. Metrics defined in dbt YAML, zero duplication with Duct's existing models. Natural language queries built in. Customers explore their own data without a custom frontend build.

**Skip for now:** Apache Superset (heavy infra), Metabase (not dbt-native), Streamlit (Python-only).

---

## Build Sequence

### Phase 2 — Manual pilots (this week)

Validate the brief format before automating anything. Customer shares read-only DB credentials. Run PyAirbyte manually to pull GA4 or HubSpot data. Feed to Claude with the PM brief prompt template. Send via Resend. Target ~2 hours per customer per week. Do not automate until 3 pilots confirm the brief format is right.

Add `backend/briefs/templates/` to this repo with the vertical prompt templates — versioned alongside the product thinking.

### Week 1–2 — Core loop

Supabase project → PyAirbyte GA4 connector → DuckDB + Ibis signals query → Instructor + Claude brief → Resend HTML email. End goal: one customer, one tool, one brief delivered end-to-end.

### Week 3–4 — All connectors + orchestration

Add connectors: Mixpanel, HubSpot, Salesforce, Intercom, Linear. Add dbt staging models per tool and a cross-tool marts model. Wire into Dagster asset graph. Schedule: Monday 7am per customer timezone.

### Week 5–6 — Anomaly detection

Hourly Dagster job for cross-tool anomaly detection. Slack webhook alert delivery. Supabase stores alert history.

### Week 7–8 — Self-serve onboarding (optional)

Simple HTML onboarding page. Customer enters destination connection string + Anthropic API key. Dagster auto-provisions new customer schedule.

---

## What NOT to Build

| Tool | Reason to skip |
|---|---|
| Paperclip | 3 weeks old, 375 open issues, not production-ready |
| Full Airbyte platform (Docker/K8s) | Client manages it — not Duct's responsibility |
| Temporal | Overkill. Dagster handles Duct's scheduling needs |
| n8n | Fair-code licence restricts SaaS use. Wrong abstraction for batch data pipelines |
| Custom auth | Supabase Auth handles it |
| Custom job scheduler | Dagster handles it |
| Nango / OAuth infra | Not needed — clients provide read-only destination credentials, not OAuth tokens |

---

*getduct.ai — MVP Engineering Plan v0.1 · Confidential · March 2026*
