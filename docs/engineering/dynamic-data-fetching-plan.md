# Plan: Dynamic Account Data Fetching + Gemini 2.5 Flash Synthesis

## Context

The Duct backend currently generates Google Ads reports from hardcoded demo data or manually exported CSVs — neither works for real client demos or daily use. This plan adds a live data path: a form in the Next.js app where you input a Google Ads account ID + OAuth credentials + date range, a FastAPI backend fetches real campaign data via the Google Ads API, Gemini 2.5 Flash synthesizes the findings into structured JSON, and the existing `GoogleAdsReport.js` renderer displays it unchanged.

Minimum new code — reuse everything already working:
- `GoogleAdsBrief` schema — untouched
- Deterministic math in `google_ads_brief.py` — untouched
- `GoogleAdsReport.js` renderer — untouched
- Prompt template at `briefs/templates/google_ads_weekly_brief.md` — used as Gemini system prompt

Gemini 2.5 Flash handles only the synthesis fields: `highlights`, `risks`, `recommended_actions`, `narrative`.

**Dependency management:** Poetry (`backend/pyproject.toml`). No `requirements.txt` — backend has none currently.

---

## Architecture

```
[Next.js App — /run page]
  Form: customer_id, OAuth creds, date_from, date_to
  ↓ POST /api/report/google-ads
[FastAPI Server — backend/server.py]
  ↓
[Google Ads API Fetcher — backend/scripts/google_ads_api_fetch.py]
  Two GAQL queries (current + previous period) → raw campaign rows
  Same dict shape as demo_raw_payload()
  ↓
[backend/scripts/google_ads_brief.py — add one function]
  build_brief() → deterministic: account_summary, period_comparison, campaigns[]
  synthesize_with_gemini_dict() → Gemini 2.5 Flash: highlights, risks, actions, narrative
  → saved to backend/data/google_ads/generated/{customer_id}-{date_to}.json
  ↓
[Next.js → GoogleAdsReport.js renders — zero changes]
```

---

## Files

### New

| File | Purpose |
|------|---------|
| `backend/pyproject.toml` | Poetry project + all Python dependencies |
| `backend/server.py` | FastAPI HTTP server |
| `backend/scripts/google_ads_api_fetch.py` | Google Ads API client |
| `backend/.env.example` | Credential template |
| `app/src/app/run/page.jsx` | "Run Report" form (client component) |
| `app/src/lib/api.js` | Fetch wrapper |

### Modified

| File | Change |
|------|--------|
| `backend/scripts/google_ads_brief.py` | Add `synthesize_with_gemini_dict()` |
| `app/src/app/layout.js` | Add "Run" nav link (one line) |

---

## Detailed Spec

### 1. `backend/pyproject.toml`

Poetry project. Python ≥ 3.11.

```toml
[tool.poetry]
name = "duct-backend"
version = "0.1.0"
description = "Duct reporting backend"
packages = [{ include = "briefs" }, { include = "scripts" }]

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.111"
uvicorn = { version = "^0.29", extras = ["standard"] }
google-ads = "^24.0"
google-genai = "^1.0"          # new unified SDK — google-generativeai deprecated Nov 2025
python-dotenv = "^1.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

Run with: `cd backend && poetry install`
Dev server: `poetry run uvicorn server:app --reload --port 8000`

---

### 2. `backend/scripts/google_ads_api_fetch.py`

```python
def fetch_campaigns(
    customer_id: str,           # "123-456-7890" or "1234567890" — strip dashes before API
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    date_from: str,             # "YYYY-MM-DD"
    date_to: str,
    account_name: str = "",
    currency_code: str = "USD",
    login_customer_id: str = "",  # required for MCC/manager accounts
) -> dict                         # same shape as demo_raw_payload()
```

**Client setup:**
```python
from google.ads.googleads.client import GoogleAdsClient

creds = {
    "developer_token": developer_token,
    "client_id": client_id,
    "client_secret": client_secret,
    "refresh_token": refresh_token,
    "use_proto_plus": True,
}
if login_customer_id:
    creds["login_customer_id"] = login_customer_id.replace("-", "")
client = GoogleAdsClient.load_from_dict(creds)
```

**GAQL query** — run twice (current period, then auto-computed previous period of equal length):
```sql
SELECT
  campaign.id, campaign.name, campaign.status,
  campaign.advertising_channel_type,
  metrics.clicks, metrics.impressions, metrics.cost_micros,
  metrics.conversions, metrics.conversions_value,
  metrics.ctr, metrics.average_cpc, metrics.cost_per_conversion
FROM campaign
WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
  AND campaign.status != 'REMOVED'
ORDER BY metrics.cost_micros DESC
```

**Critical unit conversions** (API returns micros):
- `cost_micros` ÷ 1,000,000 → `spend`
- `average_cpc` ÷ 1,000,000 → `average_cpc`
- `cost_per_conversion` ÷ 1,000,000 → `cost_per_conversion`
- `ctr` → already a float fraction, no change
- `roas` → compute as `conversions_value / spend` (not in API response)

**Output:** Identical dict shape to `demo_raw_payload()` in `google_ads_brief.py`:
- `source_metadata` with `source: "google_ads_api"`, both window strings, account info
- `rows[]` each with `"previous": {...}` populated from the second query

Give it a `main()` + argparse for standalone CLI testing.

---

### 3. Modify `backend/scripts/google_ads_brief.py`

Add one function — operates on plain dicts to avoid writing a dataclass deserializer:

```python
def synthesize_with_gemini_dict(
    brief_dict: dict,
    raw_payload: dict,
) -> dict:
    """
    Replaces narrative, highlights, risks, recommended_actions in brief_dict
    with Gemini 2.5 Flash output. Falls back silently to input dict on any error.
    """
```

**Gemini 2.5 Flash call (google-genai SDK):**
```python
from google import genai
from google.genai import types
import os, json

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    return brief_dict  # fallback — rule-based result kept

client = genai.Client(api_key=api_key)

config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=SYNTHESIS_SCHEMA,     # Pydantic model or dict schema
    thinking_config=types.ThinkingConfig(thinking_budget=1024),  # light reasoning for quality
    temperature=0.3,
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=config,
)
synthesis = json.loads(response.text)
```

**`SYNTHESIS_SCHEMA`** — a Pydantic model (or inline dict) covering only the 4 mutable fields:
`narrative` (verdict, summary, operator_takeaway), `highlights[]`, `risks[]`, `recommended_actions[]`.
Mirrors `briefs/schemas/google_ads_brief.py` shape. Define inline in this file — no separate file needed.

**Prompt:** Load `briefs/templates/google_ads_weekly_brief.md` as system context, then append the
compact campaign data JSON and schema instructions.

**Patch pattern:**
```python
brief_dict["narrative"] = synthesis.get("narrative", brief_dict["narrative"])
brief_dict["highlights"] = synthesis.get("highlights", brief_dict["highlights"])
brief_dict["risks"] = synthesis.get("risks", brief_dict["risks"])
brief_dict["recommended_actions"] = synthesis.get("recommended_actions", brief_dict["recommended_actions"])
return brief_dict
```

Wrap entire Gemini call in `try/except` — return original `brief_dict` on any failure.

**Server call pattern:**
```python
brief = build_brief(raw_payload, theme=theme)
brief_dict = brief.to_dict()
if os.environ.get("GEMINI_API_KEY"):
    brief_dict = synthesize_with_gemini_dict(brief_dict, raw_payload)
```

---

### 4. `backend/server.py`

FastAPI + Uvicorn. Load `.env` via `python-dotenv` at startup.

**Request model:**
```python
class ReportRequest(BaseModel):
    customer_id: str
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    date_from: str              # YYYY-MM-DD
    date_to: str
    account_name: str = ""
    currency_code: str = "USD"
    theme: str = "paid_ads"
    login_customer_id: str = ""  # MCC manager accounts
    use_demo: bool = False        # skip API, use demo_raw_payload()
```

**POST /api/report/google-ads:**
1. If `use_demo`: call `demo_raw_payload()` from `google_ads_brief.py`
2. Else: call `fetch_campaigns()` from `google_ads_api_fetch.py`
3. `build_brief(raw_payload, theme=theme)` → `brief.to_dict()`
4. If `GEMINI_API_KEY` set: `synthesize_with_gemini_dict(brief_dict, raw_payload)`
5. Save to `backend/data/google_ads/generated/{customer_id}-{date_to}.json`
6. Return dict

**Other endpoints:**
- `GET /api/report/latest` — most recent `*.json` brief from `backend/data/google_ads/generated/`
- `GET /health` — `{"status": "ok"}`

**CORS:** `http://localhost:3000`

**Credential fallback:** request body → `GOOGLE_ADS_*` env vars → `HTTPException(422)`

**Run:** `cd backend && poetry run uvicorn server:app --reload --port 8000`

---

### 5. `app/src/app/run/page.jsx`

`"use client"` — React form component.

**Fields:**
- Customer ID (text)
- Developer Token (password)
- Client ID (password)
- Client Secret (password)
- Refresh Token (password)
- Login Customer ID (text, optional — for MCC)
- Date From (date, default: 7 days ago)
- Date To (date, default: today)

**States:** `idle | loading | success | error`

**On submit:** POST to `http://localhost:8000/api/report/google-ads`

**Rendering:**
- Form always visible (re-run with different params)
- `loading` → "Fetching campaign data… Generating AI insights…"
- `success` → `<GoogleAdsReport payload={report} />` below the form (existing component, zero changes)
- `error` → error message

**Demo mode button:** sends `{use_demo: true}` — no credentials required — for verifying the pipeline.

Import `GoogleAdsReport` from `"../../components/GoogleAdsReport"`.

---

### 6. `app/src/lib/api.js`

```javascript
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function runGoogleAdsReport(params) {
  const res = await fetch(`${BASE}/api/report/google-ads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  return res.json();
}
```

---

### 7. `backend/.env.example`

```bash
# Google Ads API
# Developer token: Google Ads → Tools → API Center
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_REFRESH_TOKEN=
GOOGLE_ADS_CUSTOMER_ID=   # optional default (dashes OK)

# Gemini (aistudio.google.com/app/apikey)
GEMINI_API_KEY=

# Server
PORT=8000
```

---

## Key Gotchas

| Issue | Fix |
|-------|-----|
| API returns micros for all cost fields | Divide `cost_micros`, `average_cpc`, `cost_per_conversion` by 1,000,000 |
| Customer ID format | `customer_id.replace("-", "")` before all API calls |
| MCC / manager accounts | Pass `login_customer_id` in request and client creds dict |
| `google-generativeai` is deprecated | Use `google-genai` (new SDK, `from google import genai`) |
| Gemini structured output + tool calls conflict | Do not pass tool definitions — structured output only works without tools |
| Thinking budget | Set `thinking_budget=1024` for light reasoning; use `0` to disable if too slow |
| CORS in dev | `CORSMiddleware` allowing `localhost:3000` required |
| Demo report overwrite | Reports named `{customer_id}-{date_to}.json` — never collides with demo file |

---

## Implementation Sequence (for Cursor)

1. `backend/pyproject.toml` — run `cd backend && poetry install` to verify
2. `backend/scripts/google_ads_api_fetch.py` — test standalone via CLI
3. `backend/scripts/google_ads_brief.py` — add `synthesize_with_gemini_dict()`, test with demo data + real Gemini key
4. `backend/server.py` — wire together, test with curl and demo mode first
5. `app/src/lib/api.js` + `app/src/app/run/page.jsx`
6. `app/src/app/layout.js` — add "Run" nav link
7. `backend/.env.example`

---

## Verification

1. `cd backend && poetry install`
2. Copy `backend/.env.example` → `backend/.env`, add `GEMINI_API_KEY`
3. `poetry run uvicorn server:app --reload --port 8000`
4. `cd app && npm run dev`
5. Go to `http://localhost:3000/run`
6. Click "Demo mode" — verify report renders end-to-end without credentials
7. Fill in real Google Ads credentials + date range → submit
8. Confirm `backend/data/google_ads/generated/{customer_id}-{date_to}.json` written
9. Confirm report in main list at `/`
10. Check `narrative.verdict` — Gemini output is prose, rule-based fallback is template string

---

## Out of Scope (Phase 2+)

- Dagster scheduling / cron
- Resend email delivery
- Saved credentials (Supabase)
- OAuth web flow for clients
- Meta Ads, GA4, other platforms
