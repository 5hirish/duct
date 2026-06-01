"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { numericField } from "../../lib/insightData";

const COLORS = ["#2563eb", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];

export default function PieChartBlock({ title, rows, xField, yField, insightNote = "" }) {
  if (!rows?.length || !xField || !yField) return null;
  const chartData = rows.map((row) => ({ name: String(row?.[xField] ?? "-"), value: numericField(row, yField) }));

  return (
    <section>
      <p className="rpt-section-label">{title || "Composition"}</p>
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
