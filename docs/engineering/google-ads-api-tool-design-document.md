# Google Ads API — Tool Design Document

**Company:** Alleviate Lab  
**Product:** Duct (https://getduct.ai)  
**Document version:** 1.0  
**Last updated:** April 2026  

Word copy (with embedded prototype image): [`google-ads-api-tool-design-document.docx`](google-ads-api-tool-design-document.docx).

---

## 1. Company Name

**Alleviate Lab** (product: Duct — https://getduct.ai)

---

## 2. Business Model

Duct is a software product that helps advertisers understand Google Ads performance through structured reports and goal-oriented analysis (for example: efficiency, ROAS, scaling, or spend audits). The product is developed and operated by our company; we are not a traditional agency managing third-party ad accounts as the primary business, though end users (including marketers and agencies) may use Duct with their own Google Ads accounts where permitted.

We use the Google Ads API **only to read** performance and account metadata that the authenticated user is authorized to access. We do not use the API to create Google Ads accounts, create or edit campaigns or ads, or to run Keyword Planner as a service.

---

## 3. Tool Access / Use

### Who uses the tool

- **Primary:** Authenticated users (internal team during development; external customers as the product matures) who connect their Google Ads account via OAuth and run reports on demand.
- **Access model:** Users initiate a report generation flow in the web app: they choose Google Ads as a data source, select an account, an analysis goal, optional business context, and a date range. The backend calls the Google Ads API with that user's OAuth credentials and returns a structured report rendered in the UI. Users may save reports locally; production deployments persist reports according to our data policy.

### What we do not do

- We do not expose our developer token to third-party tools.
- We do not run scheduled batch jobs that mutate Google Ads entities. Duct is **read-only** toward Google Ads.
- We do not grant agency partners direct login unless they are normal product users.

---

## 4. Tool Design

Duct is a three-tier web application: a browser-based client, a server-side backend, and the Google Ads API (read-only). Users authenticate via Google OAuth with the Google Ads scope, then request on-demand reports. The backend fetches performance data via GAQL queries, normalizes it into a structured report, and optionally adds AI-powered narrative synthesis. No data is written back to Google Ads.

---

## 5. API Services Called (Read-Only)

All access is **read-only** via the Google Ads Reporting API (GAQL) and the Customer Service for account discovery. We do not call any mutate or write services.

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
- **Secrets:** Developer token, OAuth client secret, and other credentials are server-side environment variables, not committed to source control.
- **Logging:** We do not log OAuth refresh tokens. Operational logs may record customer ID and errors for support.
- **Token handling:** Aligned with Google's OAuth and Ads API policies; server-stored refresh tokens per end-user account for production.
- **Compliance:** We comply with the Google Ads API Terms of Service and Required Minimum Functionality (RMF) requirements for reporting tools.

---

## 7. Tool Mockups / Screenshots

Below is a prototype of the primary reporting UI. Additional captures of the connection and report generation flows are available on request.

### Prototype — Paid Ads Performance Report

This screen shows how users view Google Ads performance: headline ROAS with period-over-period context, spend sparkline, ROAS by campaign, key metric cards (CPA, spend, conversions) with trend indicators, and a signals section for notable issues.

![Paid Ads Performance Report — prototype / demo UI](assets/google-ads-report-prototype.png)

*Figure 1: Prototype report surface. Production UI is data-driven from live Google Ads data.*

---

*End of document.*
