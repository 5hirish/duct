"use client";

import InsightBlock from "./insight-blocks/InsightBlock";
import { resolveBlockData, resolveInsightSources } from "../lib/insightData";

function defaultBlockSpec() {
  return [
    {
      block_id: "default_kpis",
      block_type: "kpi_strip",
      title: "Core KPIs",
      data_source: "synthesis",
      kpi_fields: ["spend", "conversions", "cost_per_conversion", "roas"],
    },
    {
      block_id: "default_roas_campaign",
      block_type: "bar_chart",
      title: "ROAS by campaign",
      data_source: "campaign_performance",
      x_field: "campaign_name",
      y_field: "roas",
      sort_by: "roas",
      sort_order: "desc",
      limit: 10,
    },
    {
      block_id: "default_signals",
      block_type: "signal_list",
      title: "Signals",
      data_source: "synthesis",
    },
    {
      block_id: "default_campaigns_table",
      block_type: "table",
      title: "Campaign breakdown",
      data_source: "campaign_performance",
      x_field: "campaign_name",
      y_field: "spend",
      sort_by: "spend",
      sort_order: "desc",
    },
    {
      block_id: "default_actions",
      block_type: "action_list",
      title: "Recommended actions",
      data_source: "synthesis",
    },
  ];
}

export default function InsightDashboard({ brief, briefs, synthesis, supplementary }) {
  const sources = resolveInsightSources({ brief, briefs, synthesis, supplementary });
  const blockSpecs = synthesis?.dashboard_spec?.blocks?.length ? synthesis.dashboard_spec.blocks : defaultBlockSpec();

  return (
    <div className="rpt-sheet">
      <div className="rpt-body">
        {blockSpecs.map((spec) => (
          <InsightBlock
            key={spec.block_id}
            spec={spec}
            rows={resolveBlockData(spec, sources)}
            brief={sources.brief}
            synthesis={sources.synthesis}
          />
        ))}
      </div>
    </div>
  );
}
