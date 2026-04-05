# Google Ads API — Tool Design Document

**Product:** Duct (https://getduct.ai)  
**Document version:** 1.0  
**Last updated:** April 2026  

Word copy (with embedded prototype image): [`google-ads-api-tool-design-document.docx`](google-ads-api-tool-design-document.docx). Regenerate with `python scripts/build_google_ads_design_docx.py`.

---

## 1. Company Name

**Duct** (public site: https://getduct.ai)

---

## 2. Business Model

Duct is a **software product** that helps advertisers understand **Google Ads performance** through **structured reports** and **goal-oriented analysis** (for example: efficiency, ROAS, scaling, or spend audits). The product is developed and operated by our company; we are **not** a traditional agency managing third-party ad accounts as the primary business, though **end users** (including marketers and agencies) may use Duct with **their own** Google Ads accounts where permitted.

We use the Google Ads API **only to read** performance and account metadata that the authenticated user is authorized to access. We **do not** use the API to **create Google Ads accounts**, **create or edit campaigns or ads**, or to run **Keyword Planner** as a service.

---

## 3. Tool Access / Use

### Who uses the tool

- **Primary:** Authenticated users (internal team during development; external customers as the product matures) who connect their Google Ads account via OAuth and run reports on demand.
- **Access model:** Users initiate a report generation flow in the web app: they choose data sources (Google Ads), select account (when multiple are accessible), analysis goal, optional business context, and date range. The backend calls the Google Ads API with that user's refresh token for that session/request and returns a JSON brief rendered in the UI. Users may save reports for local viewing in the app (e.g. browser storage for demos); production deployments may persist reports according to our data policy.

### What we do not do (today)

- We **do not** expose our Google Ads developer token to arbitrary third-party tools.
- We **do not** run a scheduled batch job (e.g. hourly) that mutates Google Ads entities for inventory or stock status. Duct's current implementation is **read-only** toward Google Ads.
- We **do not** grant agency partners direct login to our app unless they are normal product users; any sharing of exported insights (PDF/screenshot/email) is outside the API tool's access boundary.

---

## 4. Tool Design

### Architecture (high level)

- **Web client (Next.js)** — Pages for connections (OAuth), generate report (wizard: sources → configuration → review → generate), and report viewing.
- **Application backend (FastAPI)** — Serves REST APIs under `/api/…`, validates API key on protected routes, performs OAuth redirects for Google (browser flow), and orchestrates fetch → brief → optional LLM synthesis.
- **Google Ads API** — Read-only access using `GoogleAdsClient` with developer token, OAuth client id/secret, user refresh token, and optional `login_customer_id` (MCC) when listing or querying client accounts under a manager.

### Data flow

- **OAuth:** User completes Google OAuth (scope: `https://www.googleapis.com/auth/adwords`). Refresh token is stored in the browser for the demo-style flow (`sessionStorage`) and sent to our backend only when requesting account list or generation; production should move to server-side token storage tied to user identity.
- **Account listing:** Backend calls `CustomerService.list_accessible_customers`, then `GoogleAdsService.search_stream` with a small `customer` query to attach names and currency.
- **Reporting:** Backend runs GAQL via `GoogleAdsService.search_stream` over user-selected date ranges. Campaign-level metrics are always fetched; additional slices (search terms, device, geography, ad group) are invoked when the analysis agent selects those tools for the user's goal.
- **Brief + synthesis:** Raw aggregates are turned into a typed brief (deterministic structure). An LLM may add narrative synthesis; no LLM output is written back to Google Ads.

### User interface

- Reporting is interactive in the browser (scrollable report, optional synthesis sections).
- PDF export is not currently implemented; MVP focuses on on-screen report and local save.

### Data flow diagram

```
Browser (Next.js)  →  HTTPS + API key  →  FastAPI /api  →  Google Ads API (read-only)
Browser  →  OAuth 2.0 redirect  →  Google
FastAPI  →  Brief builder  →  Goal-driven tools (optional)  →  Google Ads API
```

---

## 5. API Services Called (Read-Only)

All access is read-only via `GoogleAdsService.search_stream` (GAQL) and `CustomerService.list_accessible_customers`. We **do not** call mutate services (no `CampaignService.mutate`, `AdGroupAdService`, `KeywordPlanIdeaService`, etc.).

| Purpose | Google Ads API Usage |
|---------|----------------------|
| List accessible accounts | `CustomerService.list_accessible_customers`; then `GoogleAdsService.search_stream` on `customer` (id, name, currency, time zone, manager flag). |
| Campaign performance | `GoogleAdsService.search_stream` — GAQL `FROM campaign` with `segments.date`, metrics (clicks, impressions, cost, conversions, conversion value), `campaign.advertising_channel_type`. Excludes `REMOVED` campaigns. |
| Search terms (top by spend) | `GoogleAdsService.search_stream` — `FROM search_term_view`. |
| Device segmentation | `GoogleAdsService.search_stream` — `FROM campaign` with `segments.device`. |
| Geography | `GoogleAdsService.search_stream` — `FROM geographic_view`. |
| Ad group rollups | `GoogleAdsService.search_stream` — `FROM ad_group`. |

**Campaign types:** We do not filter by channel in code; any non-removed campaign returned by reporting is in scope (Search, Performance Max, Display, Shopping, Video, etc., per Google's classification).

---

## 6. Security and Compliance

- **Transport:** HTTPS between client and backend.
- **Authentication:** `X-API-Key` on `/api/…` routes (except health and OAuth redirect endpoints).
- **Secrets:** Developer token, OAuth client secret, and LLM keys are environment variables on the server, not committed to source control.
- **Logging:** We avoid logging full OAuth refresh tokens; operational logs may record customer id and errors for support.
- **Token handling:** Aligned with Google's OAuth and Ads API policies; prefer server-stored refresh tokens per end-user account for production.

---

## 7. Tool Mockups / Screenshots

Required for externally accessible tools: embed 3–6 screenshots or mock-ups. Below is a prototype of the primary reporting UI; additional captures of the connection and generate flows can be added for a fuller set.

### 7.1 Prototype — Paid Ads Performance Report

This mock-up shows how users view Google Ads performance in the product: date window, headline ROAS with week-over-week context, 7-day spend sparkline, ROAS by campaign bars (Search vs Display), CAC / Spend / Conversions cards with target and period comparisons, and a signals area for notable issues.

![Paid Ads Performance Report — prototype / demo UI](assets/google-ads-report-prototype.png)

*Figure 1: Prototype report surface. Production UI is data-driven from API-backed briefs.*

### 7.2 Additional Captures (recommended for submission)

| # | Screen | Route / Area |
|---|--------|--------------|
| 1 | Connections — Google Ads connect / status | `/connections` |
| 2 | Generate — data sources step | `/generate` step 1 |
| 3 | Generate — account + goal + date range | `/generate` step 2 |
| 4 | Generate — review before run | `/generate` step 3 |
| 5 | In-progress / generating state | `/generate` during API call |
| 6 | Live report | `/generate` after success or `/reports/[slug]` |

---

## 8. Declaration Alignment

Use these answers on the Google token application form:

- **Capabilities:** Reporting (read-only). Not: account/campaign creation or management via API; not Keyword Planner; not App Conversion Tracking / Remarketing API.
- **Token use with someone else's tool:** No (token is for Duct's own backend).
- **Campaign types:** All types returned in campaign reporting (Search, Performance Max, Display, Shopping, Video, etc.).

---

*End of document.*
