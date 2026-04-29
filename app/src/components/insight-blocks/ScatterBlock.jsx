"use client";

import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { numericField } from "../../lib/insightData";

export default function ScatterBlock({ title, rows, xField, yField, insightNote = "" }) {
  if (!rows?.length || !xField || !yField) return null;
  const chartData = rows.map((row) => ({
    ...row,
    __x: numericField(row, xField),
    __y: numericField(row, yField),
  }));

  return (
    <section>
      <p className="rpt-section-label">{title || "Scatter"}</p>
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" dataKey="__x" name={xField} />
            <YAxis type="number" dataKey="__y" name={yField} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} />
            <Scatter data={chartData} fill="var(--rpt-accent)" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
