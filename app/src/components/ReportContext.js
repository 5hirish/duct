"use client";

import { createContext, useContext, useMemo } from "react";

const ReportContext = createContext(null);

function formatDateWindow(windowCurrent = "") {
  const [from = "", to = ""] = windowCurrent.split(" to ");
  return { from, to };
}

function buildSummaryText(chatPayload) {
  const lines = [
    `Goal: ${chatPayload.goal || "unknown"}`,
    `Connectors: ${(chatPayload.connectors || []).join(", ") || "none"}`,
    `Account: ${chatPayload.account?.name || "unknown"} (${chatPayload.account?.currency || "USD"})`,
    `Date window: ${chatPayload.date_window?.current?.from || "?"} to ${chatPayload.date_window?.current?.to || "?"}`,
    `Narrative: ${chatPayload.narrative?.summary || "n/a"}`,
    `Operator takeaway: ${chatPayload.narrative?.operator_takeaway || "n/a"}`,
    `Actions: ${(chatPayload.recommended_actions || []).join(" | ") || "n/a"}`,
  ];
  return lines.join("\n");
}

function buildChatPayload(entry, brief, synthesis, liveRefresh) {
  const metadata = entry?.payload?.metadata || {};
  const routine = entry?.routine || {};
  const ui = entry?.ui || {};
  const narrative = synthesis?.narrative ?? brief?.narrative ?? {};
  const highlights = synthesis?.highlights ?? brief?.highlights ?? [];
  const risks = synthesis?.risks ?? brief?.risks ?? [];
  const findings = [
    ...highlights.map((finding) => ({ ...finding, category: "win" })),
    ...risks.map((finding) => ({ ...finding, category: "risk" })),
  ];
  const accountSummary = brief?.account_summary || {};
  const periodComparison = brief?.period_comparison || {};
  const campaigns = brief?.campaigns || [];
  const recommendations = [
    ...highlights.map((finding) => finding?.recommended_action).filter(Boolean),
    ...risks.map((finding) => finding?.recommended_action).filter(Boolean),
  ];

  const currentWindow = formatDateWindow(brief?.source_metadata?.window_current);
  const previousWindow = formatDateWindow(brief?.source_metadata?.window_previous);

  const payload = {
    report_id: entry?.slug || "",
    generated_at: metadata.generated_at || brief?.source_metadata?.generated_at || "",
    last_refreshed_at: liveRefresh?.last_refreshed_at || null,
    goal: metadata.goal || routine.goal || "",
    custom_goal: routine.custom_goal || "",
    connectors: metadata.connectors_used || routine.connections || [],
    date_window: {
      current: currentWindow,
      previous: previousWindow,
    },
    account: {
      name: brief?.source_metadata?.account_name || "",
      currency: brief?.source_metadata?.currency_code || "USD",
    },
    kpis: {
      spend: accountSummary?.spend?.formatted || "",
      conversions: accountSummary?.conversions?.formatted || "",
      cpa: accountSummary?.cost_per_conversion?.formatted || "",
      roas: accountSummary?.roas?.formatted || "",
    },
    trends: {
      spend: periodComparison?.spend?.delta || null,
      conversions: periodComparison?.conversions?.delta || null,
      cpa: periodComparison?.cost_per_conversion?.delta || null,
      roas: periodComparison?.roas?.delta || null,
    },
    narrative,
    findings,
    recommended_actions: recommendations,
    campaigns: campaigns.map((campaign) => ({
      name: campaign.campaign_name,
      spend: campaign.spend,
      roas: campaign.roas,
      cpa: campaign.cost_per_conversion,
      action: campaign.action,
    })),
    annotations: ui.annotations || [],
    action_items: ui.action_items || [],
    business_context: routine.business_context || {},
  };
  payload.summary_text = buildSummaryText(payload);
  return payload;
}

export function ReportContextProvider({ entry, liveBriefs, children }) {
  const value = useMemo(() => {
    const payload = entry?.payload || null;
    if (!payload) {
      return {
        entry: null,
        brief: null,
        synthesis: null,
        chatPayload: null,
      };
    }
    const isEnvelope = Boolean(payload.briefs);
    const brief = liveBriefs?.google_ads || (isEnvelope ? payload.briefs?.google_ads : payload);
    const synthesis = isEnvelope ? payload.synthesis : null;
    const chatPayload = brief ? buildChatPayload(entry, brief, synthesis, entry?.refresh || null) : null;
    return { entry, brief, synthesis, chatPayload };
  }, [entry, liveBriefs]);

  return <ReportContext.Provider value={value}>{children}</ReportContext.Provider>;
}

export function useReportContext() {
  const context = useContext(ReportContext);
  if (!context) {
    throw new Error("useReportContext must be used within ReportContextProvider");
  }
  return context;
}
