"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// The five chart series the theme defines, which are contrast-checked against
// both canvases (scripts/check-contrast.mjs) and move when the theme does; the
// six fixed hexes here did neither, and three of them were the status hues at
// values no status token uses.
const CHART_COLORS = [
  "var(--chart-1)", "var(--chart-3)", "var(--chart-5)",
  "var(--chart-2)", "var(--chart-4)", "var(--primary)",
];

/**
 * A chart artifact, drawn. A module of its own so `ArtifactRenderer` can load
 * it lazily: Recharts is the single largest library in the app, and every
 * screen that shows an artifact card was paying for it to render markdown.
 * `spec` arrives already parsed and validated by `ChartJsonView`.
 */
export default function ChartSpecView({ spec }) {
  const ChartComp = spec.type === "line" ? LineChart : BarChart;
  return (
    <>
      {spec.title && <p className="text-sm font-medium mb-1 px-1">{spec.title}</p>}
      <ResponsiveContainer>
        <ChartComp data={spec.data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey={spec.x} fontSize={12} />
          <YAxis fontSize={12} />
          <Tooltip />
          <Legend />
          {spec.series.map((s, i) =>
            spec.type === "line" ? (
              <Line key={s.key} dataKey={s.key} name={s.label || s.key} stroke={CHART_COLORS[i % CHART_COLORS.length]} dot={false} />
            ) : (
              <Bar key={s.key} dataKey={s.key} name={s.label || s.key} fill={CHART_COLORS[i % CHART_COLORS.length]} />
            )
          )}
        </ChartComp>
      </ResponsiveContainer>
    </>
  );
}
