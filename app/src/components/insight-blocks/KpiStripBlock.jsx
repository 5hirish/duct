"use client";

import { metricDeltaForField, metricValueForField } from "../../lib/insightData";

export default function KpiStripBlock({ title, brief, kpiFields = [], insightNote = "" }) {
  if (!brief?.account_summary) return null;
  const fields = kpiFields.length ? kpiFields : ["spend", "conversions", "cost_per_conversion", "roas"];

  return (
    <section>
      <p className="rpt-section-label">{title || "KPI strip"}</p>
      <div className="kpi-strip">
        {fields.map((field) => (
          <div key={field} className="kpi-chip kpi-chip--accent-grey">
            <p className="kpi-label">{field.replace(/_/g, " ")}</p>
            <p className="kpi-value">{metricValueForField(brief, field)}</p>
            <p className="kpi-delta">{metricDeltaForField(brief, field)}</p>
          </div>
        ))}
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
