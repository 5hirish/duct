"use client";

import { ResponsiveHeatMap } from "@nivo/heatmap";
import { numericField } from "../../lib/insightData";

export default function HeatmapBlock({ title, rows, xField, yField, groupBy, insightNote = "" }) {
  if (!rows?.length || !xField || !yField || !groupBy) return null;

  const xValues = [...new Set(rows.map((row) => String(row?.[xField] ?? "-")))];
  const grouped = rows.reduce((acc, row) => {
    const key = String(row?.[groupBy] ?? "-");
    if (!acc[key]) acc[key] = {};
    acc[key][String(row?.[xField] ?? "-")] = numericField(row, yField);
    return acc;
  }, {});

  const data = Object.entries(grouped).map(([id, values]) => ({
    id,
    data: xValues.map((x) => ({ x, y: values[x] ?? 0 })),
  }));

  return (
    <section>
      <p className="rpt-section-label">{title || "Heatmap"}</p>
      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveHeatMap
          data={data}
          margin={{ top: 30, right: 60, bottom: 60, left: 100 }}
          valueFormat=">-.2f"
          axisTop={null}
          axisRight={null}
          axisBottom={{ tickSize: 5, tickPadding: 5, tickRotation: -30 }}
          axisLeft={{ tickSize: 5, tickPadding: 5, tickRotation: 0 }}
          colors={{ type: "sequential", scheme: "blues" }}
          emptyColor="#f3f4f6"
          borderWidth={1}
          borderColor="#ffffff"
          labelTextColor="#111827"
        />
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
