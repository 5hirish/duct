"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { fetchModes, getModeByKey, FALLBACK_MODES, DEFAULT_MODE_KEY } from "../../../lib/modes";
import ReportsPageClient from "../../../components/ReportsPageClient";

export default function InsightsModeSelector({ serverReports }) {
  const [modes, setModes] = useState(FALLBACK_MODES);
  const [selectedMode, setSelectedMode] = useState(DEFAULT_MODE_KEY);

  useEffect(() => {
    fetchModes()
      .then(setModes)
      .catch(() => {}); // stay on fallback
  }, []);

  const modeConfig = getModeByKey(modes, selectedMode);

  return (
    <>
      <div className="mode-selector" role="tablist" aria-label="Intelligence mode">
        {modes.map((m) => (
          <button
            key={m.key}
            role="tab"
            aria-selected={selectedMode === m.key}
            disabled={!m.active}
            className={[
              "mode-pill",
              selectedMode === m.key ? "mode-pill--active" : "",
              !m.active ? "mode-pill--disabled" : "",
            ].filter(Boolean).join(" ")}
            onClick={() => m.active && setSelectedMode(m.key)}
            title={!m.active ? "Coming Soon" : m.tagline}
          >
            <span aria-hidden="true">{m.emoji}</span>
            {m.short_label}
            {!m.active && <span className="mode-pill-coming-soon">Soon</span>}
          </button>
        ))}
      </div>

      <div className="mode-header-row">
        <p className="app-subtle mode-tagline">
          {modeConfig?.tagline ?? ""}
        </p>
        <Button variant="outline" size="default" asChild>
          <Link href={`/insights/generate?mode=${selectedMode}`}>Generate Insight</Link>
        </Button>
      </div>

      <ReportsPageClient serverReports={serverReports} mode={selectedMode} />
    </>
  );
}
