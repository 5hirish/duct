"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { numericField } from "../../lib/insightData";

export default function TimeSeriesBlock({ title, rows, xField, yField, insightNote = "" }) {
  if (!rows?.length || !xField || !yField) return null;
  const chartData = rows.map((row) => ({ ...row, __value: numericField(row, yField) }));

  return (
    <section>
      <p className="rpt-section-label">{title || "Time series"}</p>
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xField} />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="__value" stroke="var(--rpt-accent)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
