"use client";

// The autonomous insights session. Deliberately has no setup screen: the point
// of the rewrite is that a project and a sentence are the whole input, so the
// page opens straight into the conversation and the agent asks for anything
// else it needs.

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import InsightsWorkspace from "@/components/insights/InsightsWorkspace";
import { getActiveProjectId } from "@/lib/projects";

function Session() {
  const params = useSearchParams();
  // ?q= lets another surface hand a question straight in (an audit finding, a
  // saved brief, a link). Absent, the agent opens the conversation itself.
  const prompt = params.get("q") || "";
  const projectId = params.get("project") || getActiveProjectId() || "";

  return (
    <div className="h-[calc(100vh-4rem)]">
      <InsightsWorkspace projectId={projectId} initialPrompt={prompt} />
    </div>
  );
}

export default function InsightsSessionPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading…</div>}>
      <Session />
    </Suspense>
  );
}
