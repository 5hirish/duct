"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { fetchModes, getModeByKey, FALLBACK_MODES, DEFAULT_MODE_KEY } from "../../../lib/modes";
import ReportsPageClient from "../../../components/ReportsPageClient";

export default function InsightsModeSelector({ serverReports }) {
  const [modes, setModes] = useState(FALLBACK_MODES);
  const [selectedMode, setSelectedMode] = useState(DEFAULT_MODE_KEY);

  useEffect(() => {
    fetchModes()
      .then(setModes)
      .catch(() => {});
  }, []);

  const modeConfig = getModeByKey(modes, selectedMode);

  return (
    <Tabs value={selectedMode} onValueChange={setSelectedMode}>
      {/* Mode card row */}
      <TabsList
        className="h-auto w-full justify-start gap-2.5 rounded-none bg-transparent p-0 mb-5 overflow-x-auto flex-nowrap"
        aria-label="Intelligence mode"
      >
        {modes.map((m) => (
          <TabsTrigger
            key={m.key}
            value={m.key}
            disabled={!m.active}
            className="h-auto flex-none rounded-none border-0 bg-transparent p-0 data-active:bg-transparent data-active:shadow-none"
          >
            <Card
              size="sm"
              className={[
                "w-36 cursor-pointer gap-3 rounded-2xl px-4 py-4 text-left shadow-sm transition-all",
                "ring-0 data-[state=active]:ring-2 data-[state=active]:ring-primary",
                selectedMode === m.key
                  ? "border-primary bg-primary/5 ring-1 ring-primary"
                  : "hover:border-primary/50",
                !m.active ? "opacity-50 cursor-not-allowed" : "",
              ].filter(Boolean).join(" ")}
            >
              <span className="text-2xl leading-none" aria-hidden="true">{m.emoji}</span>
              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold leading-tight text-foreground">
                  {m.label}
                </span>
                {!m.active && (
                  <Badge variant="secondary" className="w-fit text-[10px]">
                    Coming Soon
                  </Badge>
                )}
              </div>
            </Card>
          </TabsTrigger>
        ))}
      </TabsList>

      {/* Active mode header */}
      <div className="flex items-center justify-between gap-3 mb-5">
        <p className="text-sm text-muted-foreground">
          {modeConfig?.tagline ?? ""}
        </p>
        <Button size="default" asChild>
          <Link href={`/insights/generate?mode=${selectedMode}`}>Generate Insight</Link>
        </Button>
      </div>

      {/* Report list — one TabsContent per mode, only active renders */}
      {modes.map((m) => (
        <TabsContent key={m.key} value={m.key} className="mt-0">
          <ReportsPageClient serverReports={serverReports} mode={m.key} />
        </TabsContent>
      ))}
    </Tabs>
  );
}
