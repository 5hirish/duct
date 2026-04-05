# Google Ads API — Tool Design Document

**Product:** Duct (https://getduct.ai)  
**Document version:** 1.0  
**Last updated:** April 2026  

Word copy (with embedded prototype image): [`google-ads-api-tool-design-document.docx`](google-ads-api-tool-design-document.docx).

---

## 1. Company Name

**Duct** (public site: https://getduct.ai)

---

## 2. Business Model

Duct is a **software product** that helps advertisers understand **Google Ads performance** through **structured reports** and **goal-oriented analysis** (for example: efficiency, ROAS, scaling, or spend audits). The product is developed and operated by our company; we are **not** a traditional agency managing third-party ad accounts as the primary business, though **end users** (including marketers and agencies) may use Duct with **their own** Google Ads accounts where permitted.

We use the Google Ads API **only to read** performance and account metadata that the authenticated user is authorized to access. We **do not** use the API to create Google Ads accounts, create or edit campaigns or ads, or to run Keyword Planner as a service.

---

## 3. Tool Access / Use

### Who uses the tool

- **Primary:** Authenticated users (internal team during development; external customers as the product matures) who connect their Google Ads account via OAuth and run reports on demand.
- **Access model:** Users initiate a report generation flow in the web app: they choose data sources (Google Ads), select an account (when multiple are accessible), an analysis goal, optional business context, and a date range. The backend calls the Google Ads API with that user's OAuth credentials for that request and returns a structured report rendered in the UI. Users may save reports locally in the app; production deployments may persist reports according to our data policy.

### What we do not do (today)

- We **do not** expose our Google Ads developer token to arbitrary third-party tools.
- We **do not** run scheduled batch jobs that mutate Google Ads entities. Duct's current implementation is **read-only** toward Google Ads.
- We **do not** grant agency partners direct login to our app unless they are normal product users; any sharing of exported insights (PDF/screenshot/email) is outside the API tool's access boundary.

---

## 4. Tool Design

### Architecture (high level)

- **Web client** — Pages for connecting Google Ads (OAuth), generating reports (wizard: sources → configuration → review → generate), and viewing saved reports.
- **Application backend** — REST API server that validates requests, handles OAuth redirects for Google, and orchestrates data fetching, report building, and optional AI-powered synthesis.
- **Google Ads API** — Read-only access using the Google Ads client library with developer token, OAuth client credentials, user refresh token, and optional MCC login customer ID when querying client accounts under a manager.

### Data flow

- **OAuth:** User completes Google OAuth with the Google Ads scope. The refresh token is sent to our backend when the user requests an account list or report generation. Production deployments use server-side token storage tied to user identity.
- **Account listing:** Backend lists the user's accessible Google Ads accounts, then queries account metadata (name, currency, time zone, manager status).
- **Reporting:** Backend runs Google Ads Query Language (GAQL) queries over user-selected date ranges. Campaign-level metrics are always fetched; additional data slices (search terms, device breakdown, geography, ad group performance) are fetched when the analysis goal requires them.
- **Report building:** Raw performance data is normalized into a structured report. An AI model may add narrative synthesis and recommendations; no AI output is written back to Google Ads.

### User interface

- Reporting is interactive in the browser (scrollable report with performance cards, charts, and signal alerts).
- PDF export is not currently implemented; the MVP focuses on on-screen reports and local save.

### Data flow diagram

```
Browser  →  HTTPS  →  Application Backend  →  Google Ads API (read-only)
Browser  →  OAuth 2.0 redirect  →  Google
Application Backend  →  Report Builder  →  Analysis Tools (optional)  →  Google Ads API
```

---

## 5. API Services Called (Read-Only)

All access is **read-only** via the Google Ads Reporting API (GAQL) and the Customer Service for account discovery. We **do not** call any mutate or write services.

| Purpose | Google Ads API Usage |
|---------|----------------------|
| List accessible accounts | Customer Service — list accessible customers; then query account metadata (id, name, currency, time zone, manager flag). |
| Campaign performance | Reporting API — query campaign resource with date segments, performance metrics (clicks, impressions, cost, conversions, conversion value), and channel type. Excludes removed campaigns. |
| Search terms (top by spend) | Reporting API — query search term view. |
| Device segmentation | Reporting API — query campaign resource with device segment. |
| Geography | Reporting API — query geographic view. |
| Ad group rollups | Reporting API — query ad group resource. |

**Campaign types:** We do not filter by channel; any non-removed campaign returned by reporting is in scope (Search, Performance Max, Display, Shopping, Video, etc., per Google's classification).

---

## 6. Security and Compliance

- **Transport:** HTTPS between client and backend.
- **Authentication:** API key on protected backend routes; OAuth 2.0 for Google Ads access.
- **Secrets:** Developer token, OAuth client secret, and other credentials are environment variables on the server, not committed to source control.
- **Logging:** We avoid logging OAuth refresh tokens; operational logs may record customer ID and errors for support.
- **Token handling:** Aligned with Google's OAuth and Ads API policies; prefer server-stored refresh tokens per end-user account for production.

---

## 7. Tool Mockups / Screenshots

Required for externally accessible tools: embed 3–6 screenshots or mock-ups. Below is a prototype of the primary reporting UI; additional captures of the connection and generate flows can be added for a fuller set.

### 7.1 Prototype — Paid Ads Performance Report

This mock-up shows how users view Google Ads performance in the product: date window, headline ROAS with week-over-week context, 7-day spend sparkline, ROAS by campaign bars (Search vs Display), CAC / Spend / Conversions cards with target and period comparisons, and a signals area for notable issues.

![Paid Ads Performance Report — prototype / demo UI](assets/google-ads-report-prototype.png)

*Figure 1: Prototype report surface. Production UI is data-driven from API-backed reports.*

### 7.2 Additional Captures (recommended for submission)

| # | Screen | Description |
|---|--------|-------------|
| 1 | Connections page | Google Ads connect / OAuth status |
| 2 | Generate — step 1 | Data source selection |
| 3 | Generate — step 2 | Account, goal, and date range configuration |
| 4 | Generate — step 3 | Review before generating |
| 5 | Generate — loading | Report generation in progress |
| 6 | Report view | Completed report with performance data |

---

## 8. Declaration Alignment

Use these answers on the Google token application form:

- **Capabilities:** Reporting (read-only). Not: account/campaign creation or management via API; not Keyword Planner; not App Conversion Tracking / Remarketing API.
- **Token use with someone else's tool:** No (token is for Duct's own backend).
- **Campaign types:** All types returned in campaign reporting (Search, Performance Max, Display, Shopping, Video, etc.).

---

*End of document.*
