# Intelligent Insights Architecture — Design Plan

## The Core Idea

Instead of a fixed hardcoded report layout (header + KPI strip + ROAS bars + campaign table), the agent decides what to visualize and how. The backend emits a **dashboard spec** — an ordered list of blocks with typed shapes — and the frontend renders whatever blocks the agent specified. Like lego.

The agent is already doing Phase 1 (deciding which tools to call) and Phase 2 (synthesis). We add **Phase 3: layout** — the agent also specifies what the dashboard looks like.

---

## Question 1: How Does the Agent Know What It Can Fetch?

### Current State

Right now the agent knows about tools via LangChain `StructuredTool` descriptions. There's a static list in `agents/insights/tools.py`:

```
fetch_campaign_performance     → campaign spend, clicks, conversions, ROAS
fetch_search_terms             → top 100 search terms by spend
fetch_device_performance       → campaign × device segmentation
fetch_geo_performance          → campaign × geography
fetch_ad_group_performance     → ad group level detail
fetch_ga4_landing_pages        → landing page behavior (bounce, sessions, revenue)
fetch_ga4_conversion_paths     → channel-level assisted conversions
fetch_gsc_query_performance    → organic query clicks/impressions/CTR/position
fetch_gsc_page_performance     → organic page performance
```

Each tool has a Python `description` string. The agent reads these to decide which to call. This works fine for the data-fetch decision. The problem is the agent has no vocabulary to specify visualization — it can describe findings, but can't say "show this as a bar chart grouped by device."

### The Solution: An Entity Catalog + Visualization Vocabulary

We need **two things the agent knows about**:

1. **Entity catalog** — what data is available per connector, what fields exist, what each field means
2. **Block vocabulary** — a fixed set of chart/widget types the agent can emit in its structured output

#### Entity Catalog Format

A connector's entity catalog is a JSON/Python dict that lives in `backend/agents/insights/catalog/`. It tells the agent:
- What entities exist (campaign, ad_group, search_term, device, geo, etc.)
- What metrics each entity has (spend, impressions, clicks, conversions, roas, cpa, ctr...)
- What dimensions can slice it (campaign_name, device, country, search_term...)
- What aggregations make sense (sum, avg, first)
- What the field names are in the raw data

**Format: Python TypedDict / JSON Schema per entity.**

Example `backend/agents/insights/catalog/google_ads.py`:

```python
ENTITY_CATALOG = {
    "connector_id": "google_ads",
    "entities": [
        {
            "entity_id": "campaign_performance",
            "label": "Campaign Performance",
            "tool": "fetch_campaign_performance",
            "description": "Per-campaign spend, clicks, impressions, conversions, ROAS, CPA. Includes previous-period comparison.",
            "fields": {
                "campaign_name": {"type": "dimension", "label": "Campaign"},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "clicks": {"type": "metric", "unit": "count", "agg": "sum"},
                "impressions": {"type": "metric", "unit": "count", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "conversion_value": {"type": "metric", "unit": "currency", "agg": "sum"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "cpa": {"type": "metric", "field": "cost_per_conversion", "unit": "currency", "agg": "avg"},
                "ctr": {"type": "metric", "unit": "percent", "agg": "avg"},
                "action": {"type": "classification", "values": ["scale", "pause", "monitor", "refine", "refresh", "investigate"]},
            },
            "sortable_by": ["spend", "roas", "cpa", "conversions"],
            "typical_row_count": "5–50 campaigns",
        },
        {
            "entity_id": "search_terms",
            "label": "Search Terms",
            "tool": "fetch_search_terms",
            "description": "Top 100 search terms by spend. Actual user queries that triggered ads. Shows match type, spend, CTR, CPA, ROAS per term.",
            "fields": {
                "search_term": {"type": "dimension", "label": "Search Term"},
                "campaign_name": {"type": "dimension"},
                "match_type": {"type": "dimension", "values": ["EXACT", "PHRASE", "BROAD"]},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "clicks": {"type": "metric", "unit": "count", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "cpa": {"type": "metric", "field": "cost_per_conversion", "unit": "currency", "agg": "avg"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "ctr": {"type": "metric", "unit": "percent", "agg": "avg"},
            },
            "sortable_by": ["spend", "cpa", "roas", "conversions"],
            "typical_row_count": "up to 100 terms",
        },
        {
            "entity_id": "device_performance",
            "label": "Device Performance",
            "tool": "fetch_device_performance",
            "description": "Campaign × device (MOBILE, DESKTOP, TABLET) segmentation. Each row is one campaign × one device.",
            "fields": {
                "campaign_name": {"type": "dimension"},
                "device": {"type": "dimension", "values": ["MOBILE", "DESKTOP", "TABLET"]},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "cpa": {"type": "metric", "field": "cost_per_conversion", "unit": "currency", "agg": "avg"},
            },
        },
        {
            "entity_id": "geo_performance",
            "label": "Geographic Performance",
            "tool": "fetch_geo_performance",
            "description": "Campaign × geography. Top 100 locations by spend.",
            "fields": {
                "campaign_name": {"type": "dimension"},
                "country_criterion_id": {"type": "dimension"},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "cpa": {"type": "metric", "field": "cost_per_conversion", "unit": "currency", "agg": "avg"},
            },
        },
        {
            "entity_id": "ad_group_performance",
            "label": "Ad Group Performance",
            "tool": "fetch_ad_group_performance",
            "description": "Ad group level (within campaigns). Top 100 by spend.",
            "fields": {
                "campaign_name": {"type": "dimension"},
                "ad_group_name": {"type": "dimension"},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "cpa": {"type": "metric", "field": "cost_per_conversion", "unit": "currency", "agg": "avg"},
            },
        },
    ]
}
```

**Why Python dict, not a separate JSON file?** The catalog is injected into prompts and used for validation — Python keeps it as the single source of truth without a separate serialization step.

**Why not MCP or OpenAPI spec?** Those are for external API clients. The catalog is internal prompt context — a schema the LLM reads. A compact Python dict serialized to a prompt-friendly string is the right format here.

#### How the Catalog Enters the Prompt

The catalog description is serialized into the system prompt using a compact function:

```python
def entity_catalog_prompt_block(catalog: dict) -> str:
    """Serialize catalog to a compact, prompt-friendly description."""
    lines = [f"## Available data entities for connector: {catalog['connector_id']}"]
    for ent in catalog["entities"]:
        fields_desc = ", ".join(
            f"{k} ({v['type']}, {v.get('unit','')}{', values: '+str(v['values']) if 'values' in v else ''})"
            for k, v in ent["fields"].items()
        )
        lines.append(f"### {ent['entity_id']} — {ent['label']}")
        lines.append(f"Tool: {ent['tool']}")
        lines.append(ent["description"])
        lines.append(f"Fields: {fields_desc}")
        if "sortable_by" in ent:
            lines.append(f"Sortable by: {', '.join(ent['sortable_by'])}")
    return "\n".join(lines)
```

This block is injected into `get_synthesis_user_prompt()` alongside the raw data. The agent can then name specific entities and fields in its structured output.

---

## Question 2: Dashboard Block Vocabulary (Lego Blocks)

The agent emits a `dashboard_spec` alongside its narrative, findings, and actions. The frontend renders whatever blocks the agent specified.

### Block Types (closed vocabulary)

```
kpi_strip          — 2–6 KPI tiles with value, delta, trend direction
bar_chart          — horizontal or vertical bars (categorical x-axis)
time_series        — line chart over time (needs date dimension)
scatter            — 2-metric scatter (e.g. spend vs ROAS per campaign)
table              — sortable data table with optional highlight column
heatmap            — dimension × metric grid (e.g. device × campaign × ROAS)
signal_list        — findings/risks card list (existing SignalBlock)
action_list        — recommended actions list
narrative          — markdown text block (verdict + summary)
pie_chart          — part-of-whole (use sparingly; only for budget share)
```

**Rules for the agent:**
- Only use block types from this list
- Every block must reference a `data_source` (entity_id from the catalog, or "synthesis")
- Every block must specify `x_field`, `y_field`, `group_by` (where applicable)
- Blocks are ordered — the agent decides the sequence

### Structured Output Schema Extension

Add `dashboard_spec` to `SynthesisSchema`:

```python
class BlockSpec(BaseModel):
    """A single dashboard block specified by the agent."""
    model_config = ConfigDict(extra="forbid")

    block_id: str                           # unique within this insight, e.g. "roas_by_campaign"
    block_type: Literal[
        "kpi_strip", "bar_chart", "time_series", "scatter",
        "table", "heatmap", "signal_list", "action_list",
        "narrative", "pie_chart"
    ]
    title: str                              # display title for the block
    data_source: str                        # entity_id or "synthesis"
    x_field: str = ""                       # dimension field name (for charts)
    y_field: str = ""                       # primary metric field name
    group_by: str = ""                      # secondary dimension (for grouped/heatmap)
    sort_by: str = ""                       # field to sort by
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = 0                          # 0 = no limit
    highlight_threshold: dict = {}          # e.g. {"field": "roas", "below": 1.0, "tone": "red"}
    insight_note: str = ""                  # agent's 1-sentence annotation on this block
    kpi_fields: list[str] = []             # only for kpi_strip: which fields to show


class DashboardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[BlockSpec]


class SynthesisSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative: SynNarrative
    highlights: list[SynFinding] = []
    risks: list[SynFinding] = []
    recommended_actions: list[SynRecommendedAction] = []
    classification_overrides: list[SynClassificationOverride] = []
    analysis_notes: str = ""
    dashboard_spec: DashboardSpec = Field(default_factory=DashboardSpec)  # NEW
```

The system prompt tells the agent:
- What block types are available and when to use each
- That blocks must reference real entity_ids and real field names from the catalog
- That it should order blocks from most to least important for the stated goal
- Not to use `time_series` unless time-series data was fetched

---

## Question 3: Visualization Library Comparison

**Current state:** The app has zero chart libraries installed. All visuals are handwritten SVG (Sparkline in `GoogleAdsReport.js`, ROAS bars as CSS). This works for fixed layouts but won't scale to agent-specified charts.

### What We Need From a Charting Library

| Requirement | Why |
|-------------|-----|
| Bar chart (horizontal + vertical) | campaign ROAS/spend comparisons |
| Line/area chart | time series (future) |
| Scatter plot | spend vs ROAS per campaign |
| Heatmap | device × campaign grid |
| Small/sparkline composability | KPI tiles |
| Dark mode / theme-aware | app uses CSS vars |
| Tree-shakeable | Cloudflare Workers / edge bundle size matters |
| React 19 compatible | app is on React 19 |
| No canvas requirement | SSR-compatible |
| Accessible (ARIA) | production quality |

### Options Evaluated

#### Option A: Recharts
- **Bundle:** ~80 kB gzipped
- **API:** Declarative React components. `<BarChart data={...}><Bar dataKey="roas" /></BarChart>`
- **Strengths:** Most widely used, excellent docs, responsive containers, tooltip/legend out of box, React 19 compatible, SVG-only
- **Weaknesses:** No heatmap, verbose for complex custom visuals, some rough edges in Tailwind 4 theming
- **Verdict:** Best fit for 80% of our block types. Missing heatmap natively.

#### Option B: Nivo
- **Bundle:** Per-package (e.g. `@nivo/bar` ~40kB), ~150 kB total if you import many
- **API:** Declarative React. Has heatmap natively (`@nivo/heatmap`), scatter, bar, line, pie
- **Strengths:** Has every block type we need including heatmap, consistent theming across chart types, SSR-compatible, beautiful defaults
- **Weaknesses:** Larger total bundle if importing many packages, less community than Recharts, slightly more complex theming
- **Verdict:** Has the full vocabulary we need. Better for heatmap/scatter.

#### Option C: Tremor Charts (formerly tremor-raw)
- **Bundle:** ~30 kB gzipped (wraps Recharts internally)
- **API:** High-level components. `<BarChart data={data} categories={["roas"]} />`
- **Strengths:** Designed for dashboards, Tailwind-native, minimal config, dark mode via CSS vars, very fast to implement
- **Weaknesses:** Opinionated styling (sometimes hard to customize), limited to what Tremor exposes, no heatmap, some components marked as beta
- **Verdict:** Fastest time-to-ship for basic charts. Too opinionated for our custom design.

#### Option D: Visx (Airbnb)
- **Bundle:** Modular, very small per package
- **API:** Low-level primitives. You compose everything manually.
- **Strengths:** Maximum control, composable, great performance
- **Weaknesses:** Much more code per chart, needs significant wrapper work for each block type
- **Verdict:** Overkill for MVP. Right choice only if we need extreme custom charts.

#### Option E: Observable Plot
- **Bundle:** ~35 kB gzipped
- **API:** Grammar-of-graphics style. `Plot.plot({ marks: [Plot.barY(data, {x: "name", y: "roas"})] })`
- **Strengths:** Very expressive, small, great for exploratory/generated charts (agent-specified)
- **Weaknesses:** Imperative DOM manipulation doesn't integrate cleanly with React state, requires useEffect wrapper, no built-in React components
- **Verdict:** Philosophically aligned with "agent specifies chart spec" but React integration is awkward.

### Recommendation: **Recharts + one Nivo package**

**Recharts** handles: `bar_chart`, `time_series`, `scatter`, `pie_chart`, `kpi_strip` (sparkline via AreaChart)
**`@nivo/heatmap`** handles: `heatmap`
**Custom** (existing): `signal_list`, `action_list`, `narrative`, `table`

This gives us 100% block type coverage with a minimal install footprint, avoids a full Nivo bundle, and Recharts has the best React 19 support and community docs.

```bash
npm install recharts @nivo/heatmap
```

**Total added bundle:** ~100–120 kB gzipped (lazy-loaded per chart type).

---

## Architecture: Full Data Flow

```
User sets goal + connectors + business context
                ↓
backend: Phase 1 — agent decides which tools to call (fetch_search_terms, etc.)
                ↓
backend: Phase 2 — synthesis: narrative + findings + actions + dashboard_spec
         (agent now emits dashboard_spec using entity catalog vocabulary)
                ↓
UnifiedInsight envelope:
  {
    briefs: { google_ads: { campaigns, account_summary, period_comparison } },
    supplementary: { fetch_search_terms: {...}, fetch_device_performance: {...} },
    synthesis: {
      narrative, highlights, risks, recommended_actions,
      dashboard_spec: {
        blocks: [
          { block_id: "hero_kpis", block_type: "kpi_strip", data_source: "synthesis",
            kpi_fields: ["spend", "conversions", "cpa", "roas"] },
          { block_id: "roas_by_campaign", block_type: "bar_chart", data_source: "campaign_performance",
            x_field: "campaign_name", y_field: "roas", sort_by: "roas", sort_order: "desc",
            insight_note: "Campaign B is 3x above account average — scale budget here." },
          { block_id: "device_cpa", block_type: "heatmap", data_source: "device_performance",
            x_field: "device", y_field: "cpa", group_by: "campaign_name" },
          { block_id: "search_waste", block_type: "table", data_source: "search_terms",
            sort_by: "spend", sort_order: "desc", limit: 20,
            highlight_threshold: {"field": "conversions", "below": 1, "tone": "red"},
            insight_note: "Top 20 terms by spend. Red = zero conversions." },
          { block_id: "signals", block_type: "signal_list", data_source: "synthesis" },
          { block_id: "actions", block_type: "action_list", data_source: "synthesis" },
        ]
      }
    },
    metadata: { generated_at, goal, connectors_used }
  }
                ↓
frontend: InsightDashboard component
  → reads dashboard_spec.blocks in order
  → for each block, looks up data from briefs/supplementary by data_source
  → renders the appropriate chart component (Recharts / Nivo / custom)
  → applies insight_note annotation
```

---

## Implementation Plan

### Backend

#### 1. Entity Catalog (`backend/agents/insights/catalog/`)
- `__init__.py`
- `google_ads.py` — catalog for Google Ads connector (all entities above)
- `ga4.py` — catalog for GA4 connector
- `gsc.py` — catalog for GSC connector
- `base.py` — `get_catalog_for_connector(connector_id)` → dict
- `prompt.py` — `entity_catalog_prompt_block(catalogs)` → str for injection

#### 2. Extend `SynthesisSchema` (`agents/insights/schema.py`)
- Add `BlockSpec`, `DashboardSpec` Pydantic models
- Add `dashboard_spec: DashboardSpec` field to `SynthesisSchema`

#### 3. Update System + User Prompts (`agents/insights/prompts/paid_ads.py`)
- Inject entity catalog block into user prompt (alongside raw data)
- Add block vocabulary section to system prompt:
  - Define each block type and when to use it
  - Instruct agent to reference entity_id and field names from the catalog
  - Instruct agent to order blocks by relevance to goal
  - Cap: no more than 8 blocks per insight

#### 4. Update `generate.py` pipeline
- Pass `supplementary` data in the envelope (currently it's only used internally)
- The frontend needs the raw supplementary data to render agent-specified charts

### Frontend

#### 5. Install libraries
```bash
npm install recharts @nivo/heatmap
```

#### 6. Block renderer components (`app/src/components/insight-blocks/`)
- `KpiStripBlock.jsx` — existing KpiChip pattern, extended
- `BarChartBlock.jsx` — Recharts `<BarChart>` + `<ResponsiveContainer>`
- `TimeSeriesBlock.jsx` — Recharts `<LineChart>`
- `ScatterBlock.jsx` — Recharts `<ScatterChart>`
- `HeatmapBlock.jsx` — `@nivo/heatmap`
- `TableBlock.jsx` — existing camp-table pattern, generalized
- `SignalListBlock.jsx` — existing SignalBlock refactored as standalone
- `ActionListBlock.jsx` — action items list
- `NarrativeBlock.jsx` — verdict + summary text
- `PieChartBlock.jsx` — Recharts `<PieChart>`
- `InsightBlock.jsx` — dispatcher: reads `block_type`, renders appropriate component

#### 7. `InsightDashboard.jsx` — root renderer
```jsx
// Reads synthesis.dashboard_spec.blocks, resolves data from briefs + supplementary
// Falls back to a hardcoded default layout if dashboard_spec is absent
export default function InsightDashboard({ brief, synthesis, supplementary }) {
  const blocks = synthesis?.dashboard_spec?.blocks ?? defaultBlockSpec(brief);
  return (
    <div className="insight-dashboard">
      {blocks.map(block => (
        <InsightBlock key={block.block_id} spec={block}
          brief={brief} synthesis={synthesis} supplementary={supplementary} />
      ))}
    </div>
  );
}
```

#### 8. Data resolution utility (`app/src/lib/insightData.js`)
```javascript
// resolveBlockData(spec, { brief, supplementary, synthesis }) → array of row objects
// Maps data_source entity_id → correct data slice
// Applies sort_by, sort_order, limit
export function resolveBlockData(spec, sources) {
  const DATA_SOURCE_MAP = {
    "campaign_performance": sources.brief?.campaigns,
    "search_terms": sources.supplementary?.fetch_search_terms?.rows,
    "device_performance": sources.supplementary?.fetch_device_performance?.rows,
    "geo_performance": sources.supplementary?.fetch_geo_performance?.rows,
    "ad_group_performance": sources.supplementary?.fetch_ad_group_performance?.rows,
    "synthesis": null,  // synthesis blocks use synthesis directly
  };
  // ... sort + limit
}
```

---

## What Changes in the Insight Envelope

The `UnifiedInsight` (formerly `UnifiedReport`) response needs to include `supplementary` so the frontend can render agent-specified charts that reference it:

```python
class UnifiedInsight(BaseModel):
    version: str = "3"
    connectors_used: list[str]
    briefs: dict[str, Any]
    supplementary: dict[str, Any] = {}  # NEW: raw tool outputs keyed by tool name
    synthesis: dict[str, Any] | None = None
    metadata: InsightMetadata
```

Currently `supplementary` is only used internally in the agent and not surfaced to the frontend.

---

## Fallback Strategy

If `dashboard_spec` is absent (e.g. LLM failed to emit it, or old insight being reopened):

```javascript
function defaultBlockSpec(brief) {
  return [
    { block_type: "kpi_strip", data_source: "synthesis",
      kpi_fields: ["spend", "conversions", "cpa", "roas"] },
    { block_type: "bar_chart", data_source: "campaign_performance",
      x_field: "campaign_name", y_field: "roas" },
    { block_type: "signal_list", data_source: "synthesis" },
    { block_type: "table", data_source: "campaign_performance",
      sort_by: "spend", sort_order: "desc" },
    { block_type: "action_list", data_source: "synthesis" },
  ];
}
```

This replicates the existing `GoogleAdsReport` layout as a fallback, ensuring backward compatibility.

---

## Naming: "Reports" → "Insights"

Rename throughout:
- `UnifiedReport` → `UnifiedInsight`
- `reports/` routes → `insights/` routes (already partially done in app)
- `localReports.js` → `localInsights.js` (or keep file name, change export names)
- `GoogleAdsReport.js` → `InsightDashboard.jsx` (new component)
- `LocalReportDetail.jsx` → `LocalInsightDetail.jsx`
- `ReportContext.js` → `InsightContext.js`
- localStorage key `duct_local_reports` → `duct_local_insights` (with migration)

---

## Files to Create/Modify

| File | Action | What |
|------|--------|-------|
| `backend/agents/insights/catalog/__init__.py` | CREATE | Package |
| `backend/agents/insights/catalog/google_ads.py` | CREATE | Google Ads entity catalog |
| `backend/agents/insights/catalog/ga4.py` | CREATE | GA4 entity catalog |
| `backend/agents/insights/catalog/gsc.py` | CREATE | GSC entity catalog |
| `backend/agents/insights/catalog/base.py` | CREATE | get_catalog_for_connector() |
| `backend/agents/insights/catalog/prompt.py` | CREATE | entity_catalog_prompt_block() |
| `backend/agents/insights/schema.py` | MODIFY | Add BlockSpec, DashboardSpec, extend SynthesisSchema |
| `backend/agents/insights/prompts/paid_ads.py` | MODIFY | Inject catalog + block vocabulary |
| `backend/agents/insights/prompts/organic_growth.py` | MODIFY | Same |
| `backend/routes/schemas.py` | MODIFY | UnifiedReport → UnifiedInsight + supplementary field |
| `backend/routes/generate.py` | MODIFY | Surface supplementary in envelope |
| `app/src/components/insight-blocks/` | CREATE | 10 block renderer components |
| `app/src/components/InsightDashboard.jsx` | CREATE | Root renderer with fallback |
| `app/src/lib/insightData.js` | CREATE | resolveBlockData() utility |
| `app/package.json` | MODIFY | Add recharts + @nivo/heatmap |

---

## Prompt for the Agent (System Prompt Addition)

```
## Dashboard Layout Specification

You must produce a `dashboard_spec` describing how to visualize this insight.

### Available block types:
- `kpi_strip` — 2–6 KPI tiles. Use for top-line account metrics.
- `bar_chart` — Bars sorted by a metric. Use for campaign/ad-group/geo comparisons.
- `time_series` — Line over time. Only use if time-series data was fetched.
- `scatter` — 2-metric scatter. Use for spend vs ROAS, impressions vs CTR analysis.
- `table` — Sortable rows. Use for search terms, ad groups, geo drill-downs.
- `heatmap` — Metric grid across two dimensions. Use for device × campaign analysis.
- `signal_list` — Findings/risks. Always include this.
- `action_list` — Recommended actions. Always include this.
- `narrative` — Text block. Use at the top for the verdict and summary.
- `pie_chart` — Budget share. Use sparingly, only when composition matters.

### Rules:
- Order blocks from most to least important for the stated goal.
- Use at most 8 blocks total.
- `x_field`, `y_field`, `group_by` must be exact field names from the entity catalog.
- `data_source` must be an entity_id from the catalog, or "synthesis" for findings/narrative blocks.
- Add a 1-sentence `insight_note` on any block where a key observation is visible in the data.
- Do not add a block if you did not fetch that entity's data.
```

---

## Verification

1. Generate a paid_ads insight → check `synthesis.dashboard_spec.blocks` in localStorage
2. Each block's `data_source` matches an entity that was actually fetched
3. Frontend renders all blocks without errors — each chart shows real data
4. If synthesis fails, fallback default spec renders the existing layout
5. `@nivo/heatmap` block renders correctly for device × campaign when device data was fetched
6. Old saved insights (no `dashboard_spec`) still load via fallback

---

## Addendum: Entity Catalog Freshness + PyAirbyte + Charting Library Deep Cuts

### A. Entity Catalog Freshness / Versioning

The entity catalog is **static metadata** — it describes what fields exist, their types, and their semantics. It does not hold live data. But it does need to track when it was last audited against the actual API/connector, and flag when it might be stale.

Add these fields at the top of every connector catalog:

```python
ENTITY_CATALOG = {
    "connector_id": "google_ads",
    "schema_version": "1.0.0",       # semver: bump minor when fields added, major when removed/renamed
    "last_audited": "2026-04-28",    # ISO date: when a human last verified fields against the live API
    "api_version": "v18",            # the Google Ads API version this catalog was written against
    "audit_notes": "Verified against google-ads-googleads v26.0.0 Python client",
    "entities": [ ... ]
}
```

**What triggers a version bump?**

| Change | Version bump |
|--------|-------------|
| New field added to an entity | `minor` (1.0.0 → 1.1.0) |
| Field renamed or removed | `major` (1.0.0 → 2.0.0) |
| New entity added | `minor` |
| Description/label text only | no bump needed |
| API version upgrade | `last_audited` + `api_version` updated |

**Runtime freshness check (lightweight):**

A utility `catalog/base.py` exposes `is_catalog_stale(catalog, max_days=90) -> bool` that checks `last_audited` against today. If stale, a warning is logged at startup — it does not block the pipeline. This is a developer signal, not user-facing.

```python
from datetime import date

def is_catalog_stale(catalog: dict, max_days: int = 90) -> bool:
    last = date.fromisoformat(catalog.get("last_audited", "2000-01-01"))
    return (date.today() - last).days > max_days
```

**This is not a data freshness indicator** — data freshness is the job of the `refresh` key in the insight's localStorage entry (the routine/live-refresh mechanism from the persistent insights plan). The catalog only tracks schema freshness.

---

### B. Should We Use PyAirbyte (or an Alternative) for Connector Logic?

**The precise question:** Can we reuse an existing connector's fetch/auth/schema logic — avoiding the need to write custom `fetch_*.py` functions per connector — without adopting a full batch sync pipeline?

**Research verdict: PyAirbyte can return records directly in Python, but has structural problems for per-request agent tool calls. `dlt` is a better fit for this pattern. Neither replaces what we have for Google today.**

#### How PyAirbyte Actually Works (not a batch-only tool)

PyAirbyte's `read()` does return records directly in Python without a remote destination — but it always writes through an in-process DuckDB cache first. You can iterate records as plain dicts:

```python
import airbyte as ab

source = ab.get_source("source-google-ads", config={...})
source.select_streams(["campaigns"])
result = source.read()                    # writes to in-process DuckDB cache
for record in result["campaigns"]:        # iterates dicts from cache
    print(record)
```

Or without a full `read()`:

```python
for record in source.get_records("campaigns"):  # LazyDataset → dicts
    print(record)
```

**The structural problems for agent tool calls:**

| Problem | Detail |
|---------|--------|
| Mandatory cache layer | Even `get_records()` goes through Airbyte's internal caching. Cannot be skipped. |
| Coarse stream granularity | Airbyte streams are whole tables (e.g. all campaigns, all time). Our agent needs `fetch_search_terms` and `fetch_device_performance` as separate targeted queries with date ranges — Airbyte fetches the full stream; we'd filter locally. |
| Server-side filtering lost | GAQL lets us push `WHERE date BETWEEN` and `ORDER BY cost_micros DESC LIMIT 100` to the API. Airbyte fetches everything and filters locally — much more data transferred and slower. |
| Connector startup overhead | Connectors run as subprocess-like workers; startup latency is 2–10s before first record arrives. Not suitable for < 5s agent tool calls. |
| Schema is Airbyte's, not ours | The returned fields use Airbyte's normalized column names, not the field names our entity catalog and agent prompts reference. We'd need a translation layer. |

#### dlt — The Lighter Alternative

`dlt` (data load tool) has the cleanest Python-native API for iterating connector records without a destination:

```python
import dlt

@dlt.source
def google_ads_source(config):
    @dlt.resource
    def campaigns():
        # your existing fetch logic, wrapped
        yield from fetch_campaigns(**config)
    return campaigns

# Iterate directly, no pipeline/destination required
for record in google_ads_source(config).campaigns:
    print(record)
```

dlt has 300+ sources, can iterate records without writing to a destination, and has no subprocess overhead. But for Google Ads specifically, its `source-google-ads` connector has the same GAQL granularity problem — it fetches full streams, not targeted slices.

#### The Honest Answer

For the **three Google connectors we have today** (Google Ads, GA4, GSC), the custom `service/google/fetch.py` approach is **strictly better** than PyAirbyte or dlt for agent tool calls because:

1. **GAQL server-side filtering** — we push date ranges, sorting, and limits to the API. PyAirbyte/dlt fetch full streams and filter locally.
2. **Sub-5s latency** — our functions are 500ms–2s. PyAirbyte adds 2–10s connector startup overhead.
3. **Field names match our catalog** — no translation needed.
4. **Fine-grained tool splitting** — `fetch_search_terms` vs `fetch_device_performance` are separate agent tools with separate GAQL queries. In Airbyte, these are sub-streams of one connector that can't be split independently.

**Where PyAirbyte/dlt fits in Duct's roadmap:**

For **new connectors** (HubSpot, Salesforce, Mixpanel, Linear) that we don't want to hand-code, the right pattern is:

```
Phase 3 architecture (per MVP plan):

Client's tools (HubSpot, Mixpanel, Salesforce...)
    ↓ PyAirbyte/dlt (batch sync on schedule)
DuckDB destination (per-client, local or Railway-hosted)
    ↓ Ibis query layer
Duct synthesis agent — tool calls become DuckDB/Ibis queries
    ↓ (same entity catalog + block spec pattern)
UnifiedInsight envelope
```

In this model:
- PyAirbyte/dlt handles **ingestion** on a schedule (daily/hourly) — we get 300+ connectors for free
- Agent tool calls become **Ibis queries against DuckDB** instead of live API calls
- The entity catalog is derived from Airbyte's stream catalog + our field annotations
- For Google connectors, we can keep the live API path (faster, more targeted) or migrate to DuckDB once data volume justifies caching

**Decision for now:** Keep custom Google fetch functions. When adding the first non-Google connector (HubSpot most likely), use dlt for ingestion into DuckDB and write Ibis query functions as agent tools. Validate the DuckDB query pattern against one real connector before committing to it broadly.

**Practical next step for Phase 3:** Add `dlt` as a dev dependency and write one `service/hubspot/ingest.py` (dlt pipeline) + `service/hubspot/fetch.py` (Ibis queries against DuckDB). Compare the pattern against our existing Google fetch functions.

---

### C. Charting Library — Full Comparison Including D3 and Chart.js

Updated evaluation including all commonly considered options:

| Library | Bundle (gzip) | React 19 | SVG/Canvas | Heatmap | D3 dep | Verdict |
|---------|--------------|----------|------------|---------|--------|---------|
| **Recharts** | ~80 kB | ✅ | SVG | ❌ | Internal | Best React fit for standard charts |
| **@nivo/\*** | ~40 kB/pkg | ✅ | SVG | ✅ (`@nivo/heatmap`) | Yes (peer) | Needs D3 peer dep; heatmap is best-in-class |
| **Chart.js** | ~60 kB | Via `react-chartjs-2` | **Canvas** | Plugin only | ❌ | Canvas breaks SSR; ref-based not idiomatic React |
| **D3** | ~30 kB core | ❌ (imperative) | SVG | DIY | — | Too low-level; requires `useEffect` + ref gymnastics for every chart |
| **Tremor** | ~30 kB (wraps Recharts) | ✅ | SVG | ❌ | No | Too opinionated for our custom design system |
| **Visx** | Modular ~10–15 kB/pkg | ✅ | SVG | DIY | Yes (peer) | Maximum control, maximum code |
| **Observable Plot** | ~35 kB | ❌ (imperative) | SVG/Canvas | ✅ | Yes | Grammar-of-graphics matches agent-spec model, but React integration is awkward |
| **ECharts** | ~120 kB | Via `echarts-for-react` | Canvas+SVG | ✅ | ❌ | Large bundle, Canvas default, Chinese docs ecosystem |

**Why not Chart.js:**
Canvas rendering breaks server-side rendering and means no DOM-based ARIA. Every chart is a `<canvas>` — inspectable only via Chart.js's own accessibility layer, which is incomplete. Ref-based imperative API (`chartRef.current.update()`) fights React's declarative model. For an insight dashboard that the agent generates dynamically, Canvas charts also can't participate in CSS variable theming.

**Why not D3 directly:**
D3 is a DOM manipulation library, not a React component library. Every D3 chart requires a `useEffect` that runs after mount, a ref to attach to, and manual cleanup. This is exactly the wrong pattern for agent-generated block specs where the data and config come from outside. D3 is what Recharts, Visx, and Nivo all use internally — we get D3's math without D3's imperative API. Use D3 for bespoke custom charts only (e.g. a future geo choropleth).

**Why not ECharts:**
120 kB gzipped is too heavy for a Cloudflare Workers edge deployment. Canvas-by-default creates SSR problems. The React wrapper (`echarts-for-react`) is community-maintained, not official.

**Revised Recommendation: Recharts only for MVP, with a Nivo heatmap escape hatch**

For MVP, start with Recharts alone — it covers bar, line, scatter, pie, area (sparkline). The heatmap block type is the only gap. Two options:

1. **Defer heatmap** — don't emit `heatmap` blocks in the agent prompt until Nivo is added. Replace with a `table` showing the same device × campaign data. Add heatmap in a follow-up.
2. **Add `@nivo/heatmap` immediately** — it's a single package (~40 kB), Recharts and Nivo coexist fine, and device × campaign heatmap is one of the most useful views for paid ads analysis.

Recommendation: **Option 2** — add both from the start. The agent prompt references heatmap, and the block renderer handles it. Total install:

```bash
npm install recharts @nivo/heatmap @nivo/core
```

`@nivo/core` is the shared peer used by all Nivo packages (~15 kB, required by `@nivo/heatmap`). D3 is a peer dependency of Nivo but is already a transitive dep of many tools — it won't be a net new addition in most environments.

---

### D. Tool Scaling Problem — How to Manage a Growing Tool Library

**The trajectory:**

| Connectors | Tools |
|------------|-------|
| Now (Google Ads, GA4, GSC) | ~9 |
| + HubSpot | ~15 |
| + Mixpanel | ~20 |
| + Salesforce | ~25 |
| + Linear | ~29 |

LLMs reliably degrade past ~15 tools. With 29 tools described in a single system prompt, the agent:
- Confuses tools with similar descriptions
- Calls irrelevant tools (hallucination of utility)
- Misses relevant tools buried in a long list
- Wastes context window on tool descriptions for connectors the user hasn't connected

**The solution: don't give the agent all tools at once.**

There are three layers of narrowing, applied before the agent ever sees a tool list:

---

#### Layer 1 — Only register tools for connected + available connectors

Already partially in place: `setup_tools_for_goal()` only registers tools for the connectors the user has actually connected. If they only connected Google Ads (not GA4 or GSC), GA4/GSC tools are never registered.

**Extend this:** Each connector registers its tool list in a registry. Only connectors present in `req.connections` contribute tools. At 3 connectors × 3 average tools = 9. At 5 connectors × 4 tools = 20 — still too many.

#### Layer 2 — Goal-scoped tool filtering (already exists, needs hardening)

`GOAL_TOOL_PRIORITIES` already marks which tools are most relevant per goal. Extend this to **hard-filter** rather than soft-hint: instead of giving the agent all tools with some marked `[PRIORITY]`, only give it the tools that are relevant to the current goal + mode combination.

```python
# Current: give all tools, mark some as [PRIORITY]
ALL_TOOL_NAMES = ["fetch_search_terms", "fetch_device_performance", ...]

# Better: give only goal-relevant tools (agent can't call what it can't see)
GOAL_TOOL_ALLOWLIST: dict[Goal, list[str]] = {
    InsightGenerationGoal.LOWER_CAC: [
        "fetch_search_terms",       # find wasteful queries
        "fetch_device_performance", # find device CPA gaps
        "fetch_ga4_landing_pages",  # find bounce rate issues
        "fetch_gsc_query_performance",  # find paid/organic overlap
    ],
    InsightGenerationGoal.MAXIMIZE_ROAS: [
        "fetch_ad_group_performance",
        "fetch_device_performance",
        "fetch_ga4_conversion_paths",
    ],
    # etc.
}
```

With this, a `LOWER_CAC` goal on a paid ads insight that has all Google connectors gets exactly 4 tools — not 9. A HubSpot connector adds 0 tools to a paid ads goal (HubSpot tools only appear in RevOps/pipeline goals).

#### Layer 3 — Two-stage agent architecture (for when we have 20+ tools)

When the total tool library grows beyond ~15, move to a **router + executor** pattern:

```
Stage 1: Router agent
  Input: goal, business context, connected connectors, full tool catalog descriptions
  Task: "Which 3-5 tool categories are most relevant for this goal?"
  Output: a list of tool names to activate (not calling them, just selecting)
  Model: fast/cheap (Gemini Flash, GPT-4o-mini) — no tool calls, just text output
  Latency: ~500ms

Stage 2: Executor agent
  Input: goal, business context, Stage 1's selected tools (only these are registered)
  Task: call the tools, fetch the data
  Output: supplementary datasets
  Model: full model (Gemini Pro, GPT-4o, Claude Sonnet)
  Latency: 2–5s (same as today)
```

The router reads a **compact tool catalog** (one line per tool: name + 10-word description) and selects which tools to activate. The executor only sees those tools. This keeps both stages under 8 tools without any hardcoded goal filtering.

**When to add the router:** When total registered tools across all connectors exceeds 12-15. Estimated trigger: when we add HubSpot + one more connector.

---

#### Concrete Tool Registry Design

To make Layers 1–3 work, tools need a structured registry rather than being scattered across `tools.py` files:

```python
# backend/agents/insights/registry.py

@dataclass
class ToolSpec:
    name: str
    connector_id: str                          # which connector owns this tool
    description_short: str                     # ≤15 words — for router stage
    description_long: str                      # full description — for executor stage
    goal_relevance: dict[str, int]             # goal → relevance score 0-3 (3=essential)
    creator_fn: Callable                       # creates the LangChain StructuredTool

# All tools declared here. add_tool() registers them.
_REGISTRY: dict[str, ToolSpec] = {}

def add_tool(spec: ToolSpec) -> None:
    _REGISTRY[spec.name] = spec

def get_tools_for_request(
    connections: list[str],
    goal: str,
    max_tools: int = 8,
) -> list[ToolSpec]:
    """Return the most relevant tools for this request, capped at max_tools."""
    candidates = [
        spec for spec in _REGISTRY.values()
        if spec.connector_id in connections
    ]
    # Sort by goal relevance, take top max_tools
    scored = sorted(
        candidates,
        key=lambda s: s.goal_relevance.get(goal, 0),
        reverse=True,
    )
    return scored[:max_tools]
```

Each connector's `tools.py` calls `add_tool()` at import time — tools self-register. The pipeline calls `get_tools_for_request()` to get a bounded, goal-relevant tool list regardless of how many connectors are registered. New connectors add their tools to the registry; the pipeline doesn't change.

**Summary of the three-layer approach:**

| Layer | What it does | Implemented when |
|-------|-------------|-----------------|
| L1: Connected-only | Never register tools for disconnected connectors | Now (partially exists) |
| L2: Goal-allowlist | Only expose goal-relevant tools per connector | Now — replace soft hints with hard filter |
| L3: Router agent | Two-stage: route → execute | When tool count exceeds ~15 (HubSpot + one more) |

These three layers together mean tool count stays ≤8 regardless of how many connectors are registered.

---

### E. Updated File List

Additional files from this addendum:

| File | Action | What |
|------|--------|-------|
| `backend/agents/insights/catalog/base.py` | MODIFY | Add `is_catalog_stale()`, `schema_version` validation |
| `backend/service/pipeline.py` | MODIFY | Log stale catalog warnings at startup |
| `backend/agents/insights/registry.py` | CREATE | Central tool registry with `get_tools_for_request()` |
| `backend/agents/insights/tools.py` | MODIFY | All tools call `add_tool()` to self-register |
| `backend/agents/insights/agent.py` | MODIFY | `setup_tools_for_goal()` calls `get_tools_for_request()` instead of `ALL_TOOL_NAMES` |
| `backend/agents/insights/goals/paid_ads.py` | MODIFY | `GOAL_TOOL_PRIORITIES` becomes `GOAL_TOOL_ALLOWLIST` (hard filter) |
| `backend/agents/insights/goals/organic_growth.py` | MODIFY | Same |
