function toNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function extractRows(maybeData) {
  if (!maybeData) return [];
  if (Array.isArray(maybeData)) return maybeData;
  if (Array.isArray(maybeData.rows)) return maybeData.rows;
  if (Array.isArray(maybeData.data)) return maybeData.data;
  if (Array.isArray(maybeData.results)) return maybeData.results;
  return [];
}

function sortRows(rows, sortBy, sortOrder = "desc") {
  if (!sortBy) return rows;
  const dir = sortOrder === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = a?.[sortBy];
    const bv = b?.[sortBy];
    const an = Number(av);
    const bn = Number(bv);
    if (Number.isFinite(an) && Number.isFinite(bn)) {
      return (an - bn) * dir;
    }
    return String(av ?? "").localeCompare(String(bv ?? "")) * dir;
  });
}

export function resolveInsightSources({ brief, briefs, supplementary, synthesis }) {
  const primaryBrief = brief || briefs?.google_ads || briefs?.ga4 || briefs?.gsc || null;
  return {
    brief: primaryBrief,
    briefs: briefs || {},
    supplementary: supplementary || {},
    synthesis: synthesis || null,
  };
}

export function resolveDataSourceRows(dataSource, sources) {
  const brief = sources.brief;
  const supplementary = sources.supplementary || {};

  const map = {
    campaign_performance: brief?.campaigns || [],
    search_terms: extractRows(supplementary.fetch_search_terms),
    device_performance: extractRows(supplementary.fetch_device_performance),
    geo_performance: extractRows(supplementary.fetch_geo_performance),
    ad_group_performance: extractRows(supplementary.fetch_ad_group_performance),
    ga4_landing_pages: extractRows(supplementary.fetch_ga4_landing_pages),
    ga4_conversion_paths: extractRows(supplementary.fetch_ga4_conversion_paths),
    gsc_query_performance: extractRows(supplementary.fetch_gsc_query_performance),
    gsc_page_performance: extractRows(supplementary.fetch_gsc_page_performance),
    synthesis: [],
  };

  return map[dataSource] || [];
}

export function resolveBlockData(spec, sources) {
  const rows = resolveDataSourceRows(spec.data_source, sources);
  const sorted = sortRows(rows, spec.sort_by, spec.sort_order);
  if (spec.limit && spec.limit > 0) return sorted.slice(0, spec.limit);
  return sorted;
}

export function metricValueForField(brief, field) {
  const summary = brief?.account_summary || {};
  const candidate = summary?.[field];
  if (candidate && typeof candidate === "object") {
    if (typeof candidate.formatted === "string") return candidate.formatted;
    if (candidate.value !== undefined) return String(candidate.value);
  }
  if (candidate !== undefined) return String(candidate);
  return "-";
}

export function metricDeltaForField(brief, field) {
  const delta = brief?.period_comparison?.[field]?.delta;
  return delta?.formatted || "";
}

export function numericField(row, field) {
  return toNumber(row?.[field]);
}
