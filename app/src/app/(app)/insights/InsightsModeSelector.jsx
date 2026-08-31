"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { fetchModes, getModeByKey, FALLBACK_MODES, DEFAULT_MODE_KEY } from "../../../lib/modes";
import InsightsPageClient from "../../../components/InsightsPageClient";

const COMING_SOON_PREVIEWS = {
  product_intelligence: {
    title: "Product Intelligence",
    description: "Unify product, support, and delivery signals into one weekly operating brief.",
    chips: ["Activation drops", "Release impact", "Ticket correlations"],
  },
  paid_ads: {
    title: "Paid Ads Intelligence",
    description: "See cross-channel ad performance in one view with clear budget actions.",
    chips: ["Spend shifts", "Creative fatigue", "ROAS signals"],
  },
  sales_revops: {
    title: "Sales / RevOps",
    description: "Connect pipeline movement and funnel leakage to the actions your team controls.",
    chips: ["Stage conversion", "Win/loss reasons", "Forecast health"],
  },
  ecommerce_dtc: {
    title: "E-commerce / DTC",
    description: "Track merchandising, acquisition, and retention metrics in a single commerce brief.",
    chips: ["AOV trends", "Channel mix", "Repeat purchase"],
  },
  customer_success: {
    title: "Customer Success",
    description: "Surface expansion and churn risk signals before they become revenue surprises.",
    chips: ["Health score shifts", "Renewal risks", "Expansion cues"],
  },
};

function getComingSoonPreview(mode) {
  const fallback = {
    title: mode?.label || "Upcoming Intelligence Mode",
    description: "This mode is in progress and will include focused insights and recommended next steps.",
    chips: ["Signal detection", "Action priorities", "Team-ready brief"],
  };
  return COMING_SOON_PREVIEWS[mode?.key] || fallback;
}

export default function InsightsModeSelector({ serverReports }) {
  const [modes, setModes] = useState(FALLBACK_MODES);
  const [selectedMode, setSelectedMode] = useState(DEFAULT_MODE_KEY);

  useEffect(() => {
    fetchModes()
      .then(setModes)
      .catch(() => {});
  }, []);

  const orderedModes = [...modes].sort((a, b) => {
    if (a.key === "organic_growth") return -1;
    if (b.key === "organic_growth") return 1;
    return 0;
  });

  const modeConfig = getModeByKey(modes, selectedMode);
  const comingSoonPreview = getComingSoonPreview(modeConfig);

  return (
    <>
      <div className="mb-5 flex w-full gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Intelligence mode">
        {orderedModes.map((m) => {
          const isActive = selectedMode === m.key;
          return (
            <button
              key={m.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setSelectedMode(m.key)}
              className={[
                "flex-none whitespace-nowrap rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
                isActive ? "border-primary bg-primary/10 text-foreground" : "border-border bg-background text-muted-foreground hover:text-foreground",
                !m.active ? "opacity-70" : "",
              ].filter(Boolean).join(" ")}
            >
              <span aria-hidden="true" className="mr-1.5">{m.emoji}</span>
              {m.label}
              {!m.active && (
                <span className="ml-2 text-[10px] leading-none text-muted-foreground">
                  • Coming soon
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="mb-5 flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {modeConfig?.tagline ?? ""}
        </p>
        {modeConfig?.active && (
          <Button size="default" asChild>
            <Link href="/insights/session">Start a session</Link>
          </Button>
        )}
      </div>

      {!modeConfig?.active && (
        <div
          className="mb-5 max-w-xl rounded-md border border-border bg-card/50 p-3 text-card-foreground"
          role="status"
          aria-label="Coming soon preview"
        >
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className="text-sm font-semibold">{comingSoonPreview.title}</p>
            <span className="text-[10px] leading-none text-muted-foreground">Coming soon</span>
          </div>
          <p className="mb-2 text-xs text-muted-foreground">{comingSoonPreview.description}</p>
          <div className="flex flex-wrap gap-1.5">
            {comingSoonPreview.chips.map((chip) => (
              <span
                key={chip}
                className="rounded-sm border border-border px-1.5 py-0.5 text-[10px] leading-none text-muted-foreground"
              >
                {chip}
              </span>
            ))}
          </div>
        </div>
      )}

      <InsightsPageClient
        serverReports={serverReports}
        mode={selectedMode}
        showGenerateButton={Boolean(modeConfig?.active)}
      />
    </>
  );
}
