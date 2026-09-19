"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { numericField } from "../../lib/insightData";
import { useLingui } from "@lingui/react/macro";

// The theme's series, not a sixth hand-picked palette. These are checked
// against both canvases in scripts/check-contrast.mjs, so adjacent slices stay
// apart for a low-vision reader and the chart follows the theme.
const COLORS = [
  "var(--chart-1)", "var(--chart-5)", "var(--chart-3)",
  "var(--chart-2)", "var(--chart-4)", "var(--primary)",
];

export default function PieChartBlock({ title, rows, xField, yField, insightNote = "" }) {
  const { t } = useLingui();
  if (!rows?.length || !xField || !yField) return null;
  const chartData = rows.map((row) => ({ name: String(row?.[xField] ?? "-"), value: numericField(row, yField) }));

  return (
    <section>
      <p className="rpt-section-label">{title || t`Composition`}</p>
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie data={chartData} dataKey="value" nameKey="name" outerRadius={90}>
              {chartData.map((entry, index) => (
                <Cell key={`${entry.name}-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
