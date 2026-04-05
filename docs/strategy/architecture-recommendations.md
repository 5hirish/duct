# Duct Architecture & Stack Recommendations

## Context

**Nomadtools** is a multi-agent platform built with Python/FastAPI/LangChain/SQLModel/Supabase. It has a well-established architecture with abstract base agents, streaming events, per-agent service layers, and a Streamlit UI.

**Duct** is a SaaS product that synthesizes cross-tool data (Mixpanel, GA4, HubSpot, etc.) into weekly intelligence briefs and real-time anomaly alerts. Currently only a static HTML marketing site exists. The MVP plan calls for: data ingestion → query/transform → Claude API synthesis → Resend/Slack delivery. BYOK model (customers bring their own Anthropic API key).

**Deployment constraint:** Everything deploys on **Cloudflare**. Landing page is already on Cloudflare Pages.

---

## 1. Stack Recommendation: Don't follow Nomadtools stack. Go Cloudflare-native.

### Recommendation: **TypeScript + Cloudflare Workers. Drop Python, FastAPI, and LangChain.**

**Why NOT Python/FastAPI for Duct:**
- **Cloudflare Workers don't run Python** (Pyodide support is experimental, can't use pip packages like PyAirbyte, DuckDB, Dagster)
- Deploying FastAPI on CF would require a separate container host (Railway/Fly), defeating the "all on Cloudflare" goal
- The MVP plan's heavy Python deps (PyAirbyte, DuckDB, dbt, Dagster) are **overkill for the 0→1 phase** — you're doing semi-manual pilots with 3-5 customers first

**Why TypeScript + Cloudflare Workers:**
- CF Workers is the native compute platform — zero cold starts, global edge deployment
- Direct API calls to data sources (GA4 API, Mixpanel API, HubSpot API, etc.) replace PyAirbyte for MVP
- Anthropic TS SDK supports structured outputs (tool_use + Zod schemas) — replaces Instructor
- CF Cron Triggers + Queues replace Dagster for scheduling
- Supabase JS SDK is first-class (better than the Python SDK honestly)
- One language across the entire stack (web app, API, workers)

**Why NOT LangChain (same reasoning as before):**
- Duct isn't building conversational agents — it's a data pipeline with LLM synthesis
- Anthropic SDK + Zod schemas for structured outputs is simpler and more predictable
- No need for: conversation history, tool calling loops, streaming chat, agent memory

### Cloudflare-native MVP stack mapping:

| MVP Need | Nomadtools (Python) | Duct (Cloudflare-native) |
|----------|---------------------|---------------------------|
| API server | FastAPI | **CF Workers + Hono** |
| Web app | Streamlit | **Next.js on CF Pages** (or Remix/Astro) |
| Landing page | — | **CF Pages** (already deployed) |
| Database | SQLModel + Supabase Postgres | **Supabase Postgres** (via Hyperdrive connection pooler) |
| File storage | Supabase S3 | **Cloudflare R2** |
| Scheduled jobs | Dagster | **CF Cron Triggers** |
| Job queues | — | **CF Queues** |
| KV cache | — | **Workers KV** (brief caching, rate limits) |
| Data connectors | PyAirbyte | **Direct REST API calls** from Workers |
| Data transforms | dbt + DuckDB | **SQL views in Supabase** + Worker logic |
| LLM synthesis | LangChain + Instructor | **Anthropic TS SDK** + Zod structured outputs |
| Auth | Supabase Auth + API keys | **Supabase Auth** + BYOK API keys |
| Email delivery | — | **Resend** (API call from Worker) |
| Alerts | Telegram bots | **Slack webhooks** (API call from Worker) |
| Error tracking | Sentry (Python SDK) | **Sentry** (JS SDK, CF Workers compatible) |
| Monitoring | Phoenix tracing | **CF Workers Analytics** + Sentry |

---

## 2. Should Duct follow the same structure as Nomadtools?

### Recommendation: **Reuse architectural patterns, not the code structure.**

**Patterns worth carrying over from nomadtools:**
- Environment-driven config (nomadtools uses Pydantic Settings → Duct uses `wrangler.toml` + CF secrets/env vars)
- Service layer separation (routes ↔ services ↔ data layer)
- Structured error hierarchy (custom exception classes)
- Auth middleware pattern (validate API key / JWT before route handlers)
- Per-domain organization (nomadtools has per-agent dirs → Duct has per-domain dirs)

**Don't carry over:**
- `BaseAgent` / agent hierarchy — no interactive agents in Duct
- Streaming events system — Duct delivers async briefs, not real-time chat
- Streamlit — Duct needs a proper web app
- LangChain anything — wrong tool for this job
- SQLModel/Alembic — use Supabase migrations directly
- Per-agent database schemas — unnecessary complexity for Duct's domain

---

## 3. Monorepo: YES — all on Cloudflare

### Recommendation: **Monorepo with Cloudflare-native deployment per app.**

**Why monorepo:**
1. **Speed of iteration** — atomic commits across web app + API + workers during 0→1 phase
2. **Shared types** — TypeScript across the entire stack means shared Zod schemas, shared types
3. **Single CI/CD** — Cloudflare Pages auto-deploys from repo, Workers deploy via wrangler
4. **Small team** — no need for independent release cycles yet

**Proposed monorepo structure:**
```
duct/
├── apps/
│   ├── web/                    # Web app — CF Pages (Next.js or Astro)
│   │   ├── src/
│   │   │   ├── app/            # Pages (onboarding, dashboard, brief history, settings)
│   │   │   ├── components/     # UI components
│   │   │   └── lib/            # Client-side utilities, Supabase client
│   │   ├── package.json
│   │   └── wrangler.toml       # CF Pages config (if using next-on-pages)
│   │
│   └── landing/                # Static marketing site — CF Pages (existing repo content)
│       ├── index.html
│       ├── for-product-intelligence.html
│       ├── for-organic-growth.html
│       ├── for-paid-ads.html
│       ├── blog/
│       └── assets/
│
├── workers/
│   ├── api/                    # Main API worker — CF Workers (Hono)
│   │   ├── src/
│   │   │   ├── index.ts        # Hono app entry point
│   │   │   ├── routes/
│   │   │   │   ├── auth.ts     # Auth endpoints
│   │   │   │   ├── connectors.ts # Connector CRUD
│   │   │   │   ├── briefs.ts   # Brief endpoints
│   │   │   │   ├── alerts.ts   # Alert config
│   │   │   │   └── webhooks.ts # Incoming webhooks
│   │   │   ├── services/
│   │   │   │   ├── auth.ts     # Supabase auth service
│   │   │   │   ├── briefs.ts   # Brief generation orchestration
│   │   │   │   └── alerts.ts   # Alert management
│   │   │   └── middleware/
│   │   │       ├── auth.ts     # JWT / API key validation
│   │   │       └── sentry.ts   # Error tracking
│   │   ├── wrangler.toml
│   │   └── package.json
│   │
│   ├── pipeline/               # Scheduled pipeline worker — CF Workers + Cron Triggers
│   │   ├── src/
│   │   │   ├── index.ts        # Cron trigger handler
│   │   │   ├── connectors/     # Data source API clients
│   │   │   │   ├── base.ts     # Base connector interface
│   │   │   │   ├── ga4.ts      # Google Analytics Data API
│   │   │   │   ├── mixpanel.ts # Mixpanel Export API
│   │   │   │   ├── hubspot.ts  # HubSpot API
│   │   │   │   ├── salesforce.ts
│   │   │   │   ├── intercom.ts
│   │   │   │   └── linear.ts
│   │   │   ├── synthesis/      # LLM intelligence layer
│   │   │   │   ├── signals.ts      # Signal extraction
│   │   │   │   ├── anomalies.ts    # Anomaly detection
│   │   │   │   ├── brief.ts        # Brief generation (Anthropic SDK + Zod)
│   │   │   │   └── schemas.ts      # Zod schemas for structured LLM output
│   │   │   └── delivery/       # Output channels
│   │   │       ├── email.ts    # Resend
│   │   │       └── slack.ts    # Slack webhooks
│   │   ├── wrangler.toml       # Cron trigger config: [triggers] crons = ["0 8 * * 1"]
│   │   └── package.json
│   │
│   └── shared/                 # Shared code between workers
│       ├── src/
│       │   ├── types.ts        # Shared TypeScript types
│       │   ├── schemas.ts      # Shared Zod schemas (brief format, alert format, etc.)
│       │   ├── supabase.ts     # Supabase client factory
│       │   ├── errors.ts       # Error hierarchy
│       │   └── config.ts       # Environment variable helpers
│       ├── package.json
│       └── tsconfig.json
│
├── supabase/                   # Supabase project config
│   ├── migrations/             # SQL migrations
│   │   ├── 001_organizations.sql
│   │   ├── 002_connectors.sql
│   │   ├── 003_briefs.sql
│   │   └── 004_alerts.sql
│   ├── seed.sql
│   └── config.toml
│
├── docs/                       # Planning docs (see docs/README.md)
│   ├── README.md
│   ├── strategy/
│   ├── gtm/
│   ├── mvp/
│   ├── engineering/
│   ├── design/
│   └── guides/
│
├── package.json                # Root — workspace config (pnpm/npm workspaces)
├── pnpm-workspace.yaml         # Workspace definition
├── tsconfig.base.json          # Shared TypeScript config
├── CLAUDE.md
└── README.md
```

### Deployment model (all Cloudflare):

| App | Cloudflare Service | Deploy Method |
|-----|-------------------|---------------|
| `apps/landing/` | CF Pages | Auto-deploy from repo (already set up) |
| `apps/web/` | CF Pages | `next-on-pages` or Astro CF adapter |
| `workers/api/` | CF Workers | `wrangler deploy` |
| `workers/pipeline/` | CF Workers + Cron | `wrangler deploy` (cron in wrangler.toml) |
| `supabase/` | Supabase (external) | `supabase db push` |

### Web app framework recommendation for CF Pages:
- **Next.js** with `@cloudflare/next-on-pages` — most mature, biggest ecosystem
- **Astro** with `@astrojs/cloudflare` — lighter, better for content-heavy apps (blog could migrate here)
- **Remix** — excellent CF Workers support, but smaller ecosystem

---

## 4. Key Differences: Nomadtools vs. Duct Architecture

| Aspect | Nomadtools | Duct (Recommended) |
|--------|-----------|---------------------|
| Language | Python | **TypeScript** |
| Runtime | Server (FastAPI on Render/Railway) | **Cloudflare Workers** (edge) |
| Core pattern | Interactive LLM agents | Data pipeline + LLM synthesis |
| LLM framework | LangChain (agents, tools, streaming) | **Anthropic TS SDK** + Zod (structured output) |
| Orchestration | FastAPI request/response | **CF Cron Triggers + Queues** |
| Data ingestion | Supabase direct queries | **Direct REST API calls** to data sources |
| Data transforms | SQLModel ORM | **Supabase SQL views** + Worker logic |
| Frontend | Streamlit | **Next.js/Astro on CF Pages** |
| Storage | Supabase S3 | **Cloudflare R2** |
| Delivery | API responses + Telegram bots | **Email (Resend) + Slack webhooks** |
| Auth | API key + Supabase Auth | **Supabase Auth + BYOK API keys** |
| Deploy | Docker container | **CF Workers + CF Pages** (serverless) |

---

## 5. MVP Phasing on Cloudflare

### Phase 2 (Manual Pilots — Weeks 0-2):
- Set up monorepo with `workers/api/` (Hono) + `supabase/` migrations
- Build first connector: GA4 Data API client in `workers/pipeline/connectors/ga4.ts`
- Build brief generator: Anthropic SDK + Zod in `workers/pipeline/synthesis/brief.ts`
- Wire Resend email delivery in `workers/pipeline/delivery/email.ts`
- Manual trigger via API endpoint (no cron yet)

### Phase 3 (Automation — Weeks 3-4):
- Add CF Cron Trigger for weekly Monday 8am brief generation
- Add remaining connectors (Mixpanel, HubSpot)
- Add CF Queues for async processing (connector fetch → synthesis → delivery)

### Phase 4 (Self-serve — Weeks 5-8):
- Build `apps/web/` — onboarding flow, connector OAuth, brief history dashboard
- Add anomaly detection + Slack alerts
- Add Stripe billing (via CF Worker)

---

## 6. What about Dagster/dbt/DuckDB/PyAirbyte later?

These heavy Python tools become relevant **after PMF** when you have 20+ customers with complex data needs. At that point:
- **Option A:** Add a `services/pipeline/` Python container alongside CF (hybrid), triggered by CF Queues
- **Option B:** Use managed Airbyte Cloud + managed Dagster Cloud, triggered from CF Workers via API

For MVP with 3-5 pilot customers, direct API calls from CF Workers are simpler, cheaper, and faster to iterate on. Don't over-engineer the pipeline before validating the product.
