"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { numericField } from "../../lib/insightData";

export default function BarChartBlock({ title, rows, xField, yField, insightNote = "" }) {
  if (!rows?.length || !xField || !yField) return null;
  const chartData = rows.map((row) => ({ ...row, __value: numericField(row, yField) }));

  return (
    <section>
      <p className="rpt-section-label">{title || "Bar chart"}</p>
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xField} />
            <YAxis />
            <Tooltip />
            <Bar dataKey="__value" fill="var(--rpt-accent)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
