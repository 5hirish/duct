---
name: add-connector
description: Research-first evaluation of a third-party data source for Duct (OAuth, scopes, quotas, APIs) using official docs via web search, then map findings to repo structure—no step-by-step coding walkthrough.
argument-hint: "<VendorOrProduct> [optional slug for saved memo]"
---

Evaluate and scaffold a new **Duct connector** in two layers: (1) a **Connector research memo** backed by **current official documentation**, discovered through **heavy use of web search** (and fetching doc pages when snippets are thin); (2) a **compact map** of where wiring lives in this monorepo. **Do not** treat this skill as a line-by-line implementation guide—implementation starts only after the memo is reviewed.

## When to use

- User names a product or API (e.g. Mixpanel, GA4 Data API, Google Search Console, Stripe Billing read-only).
- User wants go/no-go facts: auth model, scopes, quotas, prerequisites, and which endpoints support **read-only** reporting.

## Usage

```
/add-connector "<VendorOrProduct>" [memo-slug]
```

Examples:

```
/add-connector "Google Analytics 4 Data API"
/add-connector "Mixpanel" mixpanel
```

If the user does **not** ask for a file, deliver the **Connector research memo** in chat. If they ask to save it, write `docs/engineering/connectors/<slug>-research.md` (create `docs/engineering/connectors/` if missing).

---

## Phase 0 — Web search protocol (mandatory)

Complete this **before** filling the memo. Prefer **primary sources** over blogs or forums.

1. **Start official:** Search vendor developer docs (e.g. narrow to the vendor domain or `site:developers.google.com` for Google APIs). Use queries like `"<product> API authentication"`, `"<product> OAuth scopes"`, `"<product> rate limits"`.
2. **Follow up:** Run additional searches for OAuth app verification / consent, quotas, pagination, API versioning, deprecation notices, and **sandbox vs production**.
3. **Cross-check freshness:** Many analytics APIs version by year or have sunset dates—confirm the doc revision or announcement date; prefer the latest stable API name.
4. **Conflicts:** If sources disagree, **vendor documentation wins** over Stack Overflow or generic tutorials.
5. **Deep pages:** When search results are vague, open or fetch the exact doc URL (overview + auth + reference) until specifics (URLs, scope strings, limits) are confirmed.

Use **web search and official documentation** tools available in the environment repeatedly until each memo subsection has support (or a stated “not documented / N/A”).

**Citations:** Where possible, every subsection (A1–A7) should reference **at least one official doc URL**. Use full URLs in the memo.

---

## Phase A — Connector research memo (main deliverable)

Produce markdown with these sections. Use **today’s** docs; note the API/product version if the vendor names one.

### A1. Product fit for Duct

- What **read-only** metrics or entities would feed a brief/report (align with normalize → brief → synthesis).
- What is **out of scope** (write/mutation APIs, PII-heavy surfaces, enterprise-only gates).

### A2. Authentication model (deep dive)

- **Mechanism:** OAuth 2.0 (authorization code + PKCE?), API keys, service accounts, signed JWTs, partner tokens, etc.
- **User-vs-server:** Suitable for **browser OAuth** (user connects, refresh token to app) like current Google Ads, or **server secrets only**?
- **Token lifetime:** Access vs refresh, rotation, revocation—note implications for client `sessionStorage` vs future server-side token storage (describe current Duct pattern briefly: OAuth callback can redirect with tokens for the web app—see `backend/routes/auth.py`—without mandating architecture changes).

### A3. OAuth specifics (if applicable)

If the product does **not** use OAuth, state that and skip to A4.

- **Grant types** supported; which grant Duct should use for server-side reporting.
- **Authorization and token endpoints** (and JWKS if relevant).
- **Scopes** as **full strings**: minimum set for read-only reporting vs broader; incremental / additive consent if offered.
- **Consent and verification:** Internal vs public app, sensitive or restricted scopes, **OAuth verification** or **security assessment** requirements and timelines.
- **Redirect URIs:** HTTPS rules, localhost in dev, path matching—compatibility with a public API origin (e.g. `{API_PUBLIC_URL}/auth/connectors/{id}/oauth/callback` or vendor-required paths).

### A4. Permissions, policies, and limitations

- **Account model:** Workspaces, properties, sites, MCCs—what the user must **select after connect**.
- **Roles:** Minimum role for API access; org policies that block APIs.
- **Rate limits, quotas, pagination:** Documented defaults; batch or async patterns.
- **Data freshness and history:** Latency, retention, backfill limits.
- **Compliance / region:** Data residency, PCI/HIPAA notes if relevant (e.g. payment data).

### A5. Prerequisites and setup (operator checklist)

- **Vendor-side:** Projects, apps, API enablement, billing, domain verification, approvals.
- **Duct-side (conceptual):** Env var **names** you expect later in `backend/config.py` (no implementation).

### A6. APIs Duct can use (inventory)

From the **official API reference**, list:

- **Reports/queries/endpoints** suited to periodic briefs (dimensions, metrics, date ranges).
- **Required identifiers** (property id, site URL, account id, etc.).
- **Official SDKs** (e.g. Python) vs REST—maintenance tradeoff.

### A7. Risks and open questions

- Doc gaps, deprecations, sunset dates.
- **Sandbox/test** behavior vs production.

---

## Phase B — Duct repo structure (template only)

After the memo, add a **short** section for implementers: **what layers exist**, not how to code them. **Google Ads** is the reference implementation in-tree.

| Concern | Purpose | Typical locations |
| --- | --- | --- |
| Connector registry | `ConnectorMeta` + adapter registration | `backend/service/connectors.py`; implementation under `backend/service/...`; ensure registration import in `backend/server.py` |
| OAuth entrypoints | Browser authorize/callback | `backend/routes/auth.py` (currently connector-specific branches for Google Ads) |
| Account listing API | `GET /api/connectors/{id}/accounts` when `CAP_ACCOUNTS` is set | `backend/routes/connectors.py` |
| Generate pipeline | Fetch, normalize, `UnifiedReport.briefs` | `backend/routes/generate.py`; pattern under `backend/service/google/` |
| Typed brief contract | JSON shape consumed by the app | e.g. `backend/service/google/schema.py` for Ads |
| App surfaces | Connections UI, generate flow, report icons | `app/src/app/(app)/connections/page.jsx`, `app/src/app/(app)/generate/page.jsx`, `app/src/lib/api.js`, `app/src/components/ReportsList.jsx` |

**Template rule:** The research memo drives whether you reuse a Google-family OAuth stack, implement `list_accounts`, add a new `briefs.<connector_id>` shape, and extend `/api/generate`. **No code changes** are implied until Phase A is approved.

---

## Phase C — Handoff

Close with:

1. **Recommendation:** feasible for Duct MVP, feasible with conditions, or not recommended—with reasons tied to memo sections.
2. **Suggested `connector_id` slug** (lowercase, snake_case, stable) if implementation proceeds.
3. **Open questions** requiring product or security review.

---

## Notes

- Detailed backend conventions: `backend/AGENTS.md`.
- Google Ads remains the only fully wired connector; use it as the **on-repo shape**, not as a requirement that every connector use OAuth.
