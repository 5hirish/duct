# Plan: Add GA4 and Google Search Console Connectors

## Context

The Duct backend has a Google Ads connector that powers the paid ads report. The user wants two additional **supplementary connectors** — GA4 and Google Search Console — to enrich the Google Ads report with post-click behavior (GA4) and organic search overlap (GSC) data. These don't produce their own briefs; they add supplementary tool data that the LLM synthesis agent cross-references with Google Ads campaigns.

The existing architecture already supports this via the supplementary tool mechanism (search_terms, device, geo, ad_group are fetched the same way). We're extending that pattern with 4 new tools across 2 new data sources.

**Decisions:**
- All 4 tools (2 GA4 + 2 GSC)
- Separate OAuth per connector (each has its own authorize flow, scope, and refresh_token)

---

## Files to Modify (existing)

| File | Change |
|------|--------|
| `backend/service/google/schema.py` | Add `GA4`, `GSC` to `EvidenceDataSource`; add `LANDING_PAGE`, `CONVERSION_PATH`, `ORGANIC_QUERY`, `ORGANIC_PAGE` to `EvidenceEntityType` |
| `backend/service/connectors.py` | No changes needed (registry is generic) |
| `backend/agents/reporter/tools.py` | Add tool creators for 4 new tools; extend `ALL_TOOL_NAMES` and `GOAL_TOOL_PRIORITIES`; add GA4/GSC input schemas |
| `backend/agents/reporter/agent.py` | Add 4 new entries to `_TOOL_CREATORS` |
| `backend/agents/reporter/goals.py` | Update `GOAL_DIRECTIVES` to reference GA4/GSC data |
| `backend/agents/reporter/prompts.py` | Add 4 new entries to `SUPPLEMENTARY_ANALYSIS_GUIDES`; update `ANALYSIS_PROTOCOL` Step 3 cross-reference list |
| `backend/routes/generate.py` | Extend `_build_fetch_fns()` for GA4/GSC; update `generate()` to accept GA4/GSC connections; pass GA4/GSC identifiers |
| `backend/routes/schemas.py` | Add `ga4_property_id`, `ga4_refresh_token`, `gsc_site_url`, `gsc_refresh_token` to `GenerateRequest` |
| `backend/config.py` | Add `ga4_property_id`, `gsc_site_url` env var defaults |
| `backend/routes/auth.py` | Add GA4 and GSC OAuth authorize/callback handlers (separate flows, separate scopes) |

## Files to Create (new)

| File | Purpose |
|------|---------|
| `backend/service/google/ga4.py` | GA4 connector class + registration + fetch functions |
| `backend/service/google/gsc.py` | GSC connector class + registration + fetch functions |

---

## Step-by-Step Implementation

### Step 1: Extend Enums (`backend/service/google/schema.py`)

```python
class EvidenceDataSource(StrEnum):
    GOOGLE_ADS = "google_ads"
    GA4 = "ga4"                    # NEW
    GSC = "gsc"                    # NEW

class EvidenceEntityType(StrEnum):
    CAMPAIGN = "campaign"
    AD_GROUP = "ad_group"
    SEARCH_TERM = "search_term"
    DEVICE = "device"
    GEO = "geo"
    LANDING_PAGE = "landing_page"        # NEW (GA4)
    CONVERSION_PATH = "conversion_path"  # NEW (GA4)
    ORGANIC_QUERY = "organic_query"      # NEW (GSC)
    ORGANIC_PAGE = "organic_page"        # NEW (GSC)
```

### Step 2: Create GA4 Connector (`backend/service/google/ga4.py`)

**Connector registration** — follows `ads.py` pattern:
- `GA4Connector` class implementing `ConnectorAdapter` protocol
- `list_accounts(auth)` → calls GA4 Admin API to list accessible properties
- `GA4_META = ConnectorMeta(id="ga4", label="Google Analytics 4", oauth_scope="https://www.googleapis.com/auth/analytics.readonly", capabilities=frozenset({CAP_ACCOUNTS}))`
- Module-level `register_connector(GA4_META, GA4Connector())`

**Fetch functions** — follows `fetch.py` supplementary pattern:
- Uses `google-analytics-data` Python client (`google.analytics.data_v1beta`)
- OAuth refresh_token from request (same pattern as Google Ads)

**`fetch_ga4_landing_pages(property_id, date_from, date_to, *, refresh_token, client_id, client_secret)`**
- GA4 Data API RunReport request
- Dimensions: `pagePath`, `sessionSourceMedium`
- Metrics: `sessions`, `bounceRate`, `engagementRate`, `averageSessionDuration`, `conversions`, `totalRevenue`
- Filter: `sessionSourceMedium` contains "google / cpc" (paid traffic)
- Order by: sessions DESC, limit 100
- Returns: `{report_type: "ga4_landing_pages", date_range, row_count, rows}`

**`fetch_ga4_conversion_paths(property_id, date_from, date_to, *, refresh_token, client_id, client_secret)`**
- GA4 Data API RunReport request  
- Dimensions: `sessionSourceMedium`, `sessionDefaultChannelGroup`
- Metrics: `conversions`, `totalRevenue`, `sessions`, `engagedSessions`
- No source filter (need all channels to see assisted conversions)
- Order by: conversions DESC, limit 100
- Returns: `{report_type: "ga4_conversion_paths", date_range, row_count, rows}`

**Credential pattern**: Same as Google Ads — uses `google.oauth2.credentials.Credentials` with refresh_token + client_id + client_secret, no developer_token needed.

### Step 3: Create GSC Connector (`backend/service/google/gsc.py`)

**Connector registration**:
- `GSCConnector` class implementing `ConnectorAdapter`
- `list_accounts(auth)` → calls Search Console API `sites.list()` to list verified sites
- `GSC_META = ConnectorMeta(id="gsc", label="Google Search Console", oauth_scope="https://www.googleapis.com/auth/webmasters.readonly", capabilities=frozenset({CAP_ACCOUNTS}))`
- Module-level registration

**Fetch functions** — uses `googleapiclient.discovery` (Search Console API v3):

**`fetch_gsc_query_performance(site_url, date_from, date_to, *, refresh_token, client_id, client_secret)`**
- Search Analytics API `searchanalytics.query()` 
- Dimensions: `query`
- Metrics: clicks, impressions, ctr, position
- Row limit: 100, ordered by impressions DESC
- Returns: `{report_type: "gsc_query_performance", date_range, row_count, rows}`
- Each row: `{query, clicks, impressions, ctr, avg_position}`

**`fetch_gsc_page_performance(site_url, date_from, date_to, *, refresh_token, client_id, client_secret)`**
- Search Analytics API `searchanalytics.query()`
- Dimensions: `page`
- Metrics: clicks, impressions, ctr, position
- Row limit: 100, ordered by clicks DESC
- Returns: `{report_type: "gsc_page_performance", date_range, row_count, rows}`
- Each row: `{page, clicks, impressions, ctr, avg_position}`

### Step 4: Add Tool Creators (`backend/agents/reporter/tools.py`)

**New input schemas** (GA4 and GSC tools don't use `customer_id`):

```python
class GA4FetchInput(BaseModel):
    property_id: str = Field(description="GA4 property ID (digits only, e.g. '123456789')")
    date_from: str = Field(description="Start date in YYYY-MM-DD format")
    date_to: str = Field(description="End date in YYYY-MM-DD format")

class GSCFetchInput(BaseModel):
    site_url: str = Field(description="Search Console site URL (e.g. 'https://example.com')")
    date_from: str = Field(description="Start date in YYYY-MM-DD format")
    date_to: str = Field(description="End date in YYYY-MM-DD format")
```

**New tool creators** (same `_make_tool` pattern but with different input schemas):

```python
def _make_ga4_tool(fetch_fn, name, description):
    # Same pattern as _make_tool but uses GA4FetchInput

def _make_gsc_tool(fetch_fn, name, description):
    # Same pattern as _make_tool but uses GSCFetchInput

def create_ga4_landing_pages_tool(fetch_fn): ...
def create_ga4_conversion_paths_tool(fetch_fn): ...
def create_gsc_query_performance_tool(fetch_fn): ...
def create_gsc_page_performance_tool(fetch_fn): ...
```

**Update `ALL_TOOL_NAMES`**:
```python
ALL_TOOL_NAMES = [
    "fetch_search_terms",
    "fetch_device_performance",
    "fetch_geo_performance",
    "fetch_ad_group_performance",
    "fetch_ga4_landing_pages",         # NEW
    "fetch_ga4_conversion_paths",      # NEW
    "fetch_gsc_query_performance",     # NEW
    "fetch_gsc_page_performance",      # NEW
]
```

**Update `GOAL_TOOL_PRIORITIES`**:
```python
LOWER_CAC: [...existing, "fetch_ga4_landing_pages", "fetch_gsc_query_performance"]
MAXIMIZE_ROAS: [...existing, "fetch_ga4_conversion_paths"]
SCALE_CONVERSIONS: [...existing, "fetch_ga4_landing_pages", "fetch_gsc_query_performance"]
AUDIT_SPEND: [...existing, "fetch_gsc_query_performance", "fetch_ga4_landing_pages"]
CUSTOM: [...existing]
```

### Step 5: Register Tool Creators in Agent (`backend/agents/reporter/agent.py`)

Add to `_TOOL_CREATORS`:
```python
_TOOL_CREATORS = {
    ...existing...,
    "fetch_ga4_landing_pages": create_ga4_landing_pages_tool,
    "fetch_ga4_conversion_paths": create_ga4_conversion_paths_tool,
    "fetch_gsc_query_performance": create_gsc_query_performance_tool,
    "fetch_gsc_page_performance": create_gsc_page_performance_tool,
}
```

### Step 6: Add Analysis Guides (`backend/agents/reporter/prompts.py`)

**New `SUPPLEMENTARY_ANALYSIS_GUIDES` entries**:

```python
"ga4_landing_pages": (
    "ANALYZE GA4 landing page data by:\n"
    "- Cross-reference with Google Ads campaigns: which campaigns drive traffic to high-bounce pages?\n"
    "- Identify landing pages with >60% bounce rate receiving significant paid traffic — landing page fix needed\n"
    "- Compare engagement rate across landing pages — low engagement + high CPC = wasted spend\n"
    "- Flag campaigns where avg session duration <30s — users leave immediately after clicking\n"
    "- Look for landing pages with strong engagement but low conversions — conversion funnel issue\n"
    "- Quantify wasted ad spend on high-bounce landing pages (CPC × bounced sessions)"
),

"ga4_conversion_paths": (
    "ANALYZE GA4 conversion path data by:\n"
    "- Identify channels that ASSIST conversions but don't get last-click credit\n"
    "- Cross-reference with Google Ads campaign ROAS: campaigns with low last-click ROAS but high assisted conversions deserve budget\n"
    "- Flag campaigns that appear early in conversion paths — cutting them may reduce overall conversions\n"
    "- Compare session-level vs user-level conversion rates by channel\n"
    "- Look for channel combinations that convert at higher rates than individual channels"
),

"gsc_query_performance": (
    "ANALYZE GSC organic query data by:\n"
    "- OVERLAP DETECTION: cross-reference organic queries with Google Ads search terms\n"
    "- Flag queries where organic CTR >20% AND position <3 — you rank well organically, consider reducing paid bids\n"
    "- Identify queries with high organic impressions but low organic CTR (position 5-15) — paid amplification opportunity\n"
    "- CANNIBALIZATION: queries where both organic AND paid appear — calculate if paid CPC justifies the incremental clicks\n"
    "- Quantify potential savings from reducing bids on queries with strong organic presence\n"
    "- Find high-volume queries with NO organic presence — these depend entirely on paid"
),

"gsc_page_performance": (
    "ANALYZE GSC page performance data by:\n"
    "- Cross-reference with GA4 landing pages to get full picture: organic traffic + paid traffic + engagement\n"
    "- Identify pages with strong organic traffic that could reduce paid dependency\n"
    "- Flag landing pages with declining organic impressions — may need more paid support\n"
    "- Look for pages receiving organic traffic but NOT used as ad landing pages — opportunity to align\n"
    "- Compare organic CTR vs paid CTR for same pages — identify messaging gaps"
),
```

**Update `ANALYSIS_PROTOCOL` Step 3** — add cross-reference dimensions:
```
- GA4 landing pages × campaign: which paid campaigns send traffic to high-bounce pages?
- GA4 conversion paths × campaign ROAS: campaigns with assisted conversions that low last-click ROAS undervalues?
- GSC queries × search terms: organic/paid keyword overlap — are you paying for free clicks?
- GSC pages × landing pages: combined organic + paid traffic picture for each page
```

**Update `GOAL_DIRECTIVES`** — append GA4/GSC-aware lines to each goal directive.

### Step 7: Update Request Schema (`backend/routes/schemas.py`)

Add to `GenerateRequest`:
```python
ga4_property_id: str = ""
ga4_refresh_token: str = ""   # May differ from Google Ads token if different Google account
gsc_site_url: str = ""
gsc_refresh_token: str = ""
```

### Step 8: Update Config (`backend/config.py`)

Add fallback env vars:
```python
ga4_property_id: str = ""
gsc_site_url: str = ""
```

### Step 9: Update Generate Route (`backend/routes/generate.py`)

1. **Relax the google_ads-only check** — allow `ga4` and `gsc` in connections list
2. **Build GA4 fetch functions** (when `"ga4"` in connections and ga4_property_id provided):
   ```python
   ga4_cred_kwargs = dict(
       refresh_token=req.ga4_refresh_token or rt,  # fall back to Google Ads token
       client_id=cid,
       client_secret=secret,
   )
   fetch_fns["fetch_ga4_landing_pages"] = partial(fetch_ga4_landing_pages, **ga4_cred_kwargs)
   fetch_fns["fetch_ga4_conversion_paths"] = partial(fetch_ga4_conversion_paths, **ga4_cred_kwargs)
   ```
3. **Build GSC fetch functions** (when `"gsc"` in connections and gsc_site_url provided):
   ```python
   gsc_cred_kwargs = dict(
       refresh_token=req.gsc_refresh_token or rt,
       client_id=cid,
       client_secret=secret,
   )
   fetch_fns["fetch_gsc_query_performance"] = partial(fetch_gsc_query_performance, **gsc_cred_kwargs)
   fetch_fns["fetch_gsc_page_performance"] = partial(fetch_gsc_page_performance, **gsc_cred_kwargs)
   ```
4. **Pass identifiers to Phase 1** — the agent needs to inject `property_id` or `site_url` into tool calls (like it injects `customer_id`). Update `fetch_supplementary_data()` to accept and inject these.
5. **Update connectors_used** in the response envelope.

### Step 10: Update Agent Tool Injection (`backend/agents/reporter/agent.py`)

Update `fetch_supplementary_data()` to accept `ga4_property_id` and `gsc_site_url` params, and inject them into tool calls alongside `customer_id`:
```python
# For GA4 tools, inject property_id instead of customer_id
if "ga4" in tool_name:
    tool_args.setdefault("property_id", ga4_property_id)
# For GSC tools, inject site_url instead of customer_id
elif "gsc" in tool_name:
    tool_args.setdefault("site_url", gsc_site_url)
else:
    tool_args.setdefault("customer_id", customer_id)
```

### Step 11: Update OAuth Routes (`backend/routes/auth.py`)

Separate OAuth flows per connector (user chose this over single combined flow):
- `_ga4_authorize()` — same `create_google_oauth_flow` pattern, scope = `https://www.googleapis.com/auth/analytics.readonly`, own state key `CONNECTOR_GA4`
- `_ga4_callback()` — exchange code, return refresh_token to frontend via `#ga4_refresh_token=...`
- `_gsc_authorize()` — same pattern, scope = `https://www.googleapis.com/auth/webmasters.readonly`, own state key `CONNECTOR_GSC`
- `_gsc_callback()` — exchange code, return refresh_token via `#gsc_refresh_token=...`
- Extend `connector_oauth_authorize()` and `connector_oauth_callback()` switch logic for `ga4` and `gsc` connector IDs
- Frontend stores separate refresh tokens per connector and passes them in `GenerateRequest`

### Step 12: Register Connector Imports

Ensure `ga4.py` and `gsc.py` modules are imported at app startup so their `register_connector()` calls execute. Add imports in the app's startup path (likely `main.py` or wherever `ads.py` is imported).

---

## Python Dependencies

- `google-analytics-data` — GA4 Data API client (`pip install google-analytics-data`)
- `google-api-python-client` — GSC uses discovery-based client (likely already installed for other Google APIs)
- `google-auth` — OAuth credential handling (already installed)

---

## Verification

1. **Unit test**: Each fetch function returns the expected `{report_type, date_range, row_count, rows}` shape
2. **Integration test**: `POST /api/generate` with `connections: ["google_ads", "ga4", "gsc"]` returns a unified report with enriched synthesis
3. **Connector registry**: `get_connector("ga4")` and `get_connector("gsc")` resolve correctly
4. **OAuth**: `/auth/connectors/ga4/oauth/authorize` and `/auth/connectors/gsc/oauth/authorize` redirect to Google with correct scopes
5. **Tool selection**: Verify the LLM receives GA4/GSC tools when those connectors are in the connections list, and that priority hints are correct per goal
6. **Synthesis quality**: Verify the LLM produces cross-connector findings (e.g., "Campaign X has high CPA in Google Ads AND high bounce rate in GA4")
7. **Run existing tests**: `cd backend && python -m pytest` to verify no regressions
