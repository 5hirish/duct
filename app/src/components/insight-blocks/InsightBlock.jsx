"use client";

import ActionListBlock from "./ActionListBlock";
import BarChartBlock from "./BarChartBlock";
import HeatmapBlock from "./HeatmapBlock";
import KpiStripBlock from "./KpiStripBlock";
import NarrativeBlock from "./NarrativeBlock";
import PieChartBlock from "./PieChartBlock";
import ScatterBlock from "./ScatterBlock";
import SignalListBlock from "./SignalListBlock";
import TableBlock from "./TableBlock";
import TimeSeriesBlock from "./TimeSeriesBlock";

export default function InsightBlock({ spec, rows, brief, synthesis }) {
  const common = {
    title: spec.title,
    rows,
    xField: spec.x_field,
    yField: spec.y_field,
    groupBy: spec.group_by,
    highlightThreshold: spec.highlight_threshold,
    insightNote: spec.insight_note,
  };

  switch (spec.block_type) {
    case "narrative":
      return <NarrativeBlock title={spec.title} synthesis={synthesis} insightNote={spec.insight_note} />;
    case "kpi_strip":
      return (
        <KpiStripBlock
          title={spec.title}
          brief={brief}
          kpiFields={spec.kpi_fields || []}
          insightNote={spec.insight_note}
        />
      );
    case "bar_chart":
      return <BarChartBlock {...common} />;
    case "time_series":
      return <TimeSeriesBlock {...common} />;
    case "scatter":
      return <ScatterBlock {...common} />;
    case "heatmap":
      return <HeatmapBlock {...common} />;
    case "table":
      return <TableBlock {...common} />;
    case "signal_list":
      return <SignalListBlock title={spec.title} synthesis={synthesis} insightNote={spec.insight_note} />;
    case "action_list":
      return <ActionListBlock title={spec.title} synthesis={synthesis} insightNote={spec.insight_note} />;
    case "pie_chart":
      return <PieChartBlock {...common} />;
    default:
      return null;
  }
}
