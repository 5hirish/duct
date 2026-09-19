"use client";

// The autonomous insights session. Deliberately has no setup screen: the point
// of the rewrite is that a project and a sentence are the whole input, so the
// page opens straight into the conversation and the agent asks for anything
// else it needs.

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useLingui } from "@lingui/react/macro";
import InsightsWorkspace from "@/components/insights/InsightsWorkspace";
import { SkeletonDocument } from "@/components/ui/skeleton";
import { getActiveProjectId } from "@/lib/projects";

function Session() {
  const params = useSearchParams();
  // ?q= lets another surface hand a question straight in (an audit finding, a
  // saved brief, a link). Absent, the agent opens the conversation itself.
  const prompt = params.get("q") || "";
  // ?conversation= re-opens a stored thread and ?artifact= puts one of its
  // documents in the right pane. Both come from the desk, where opening a
  // brief means opening the thread that argued for it.
  const conversationId = params.get("conversation") || "";
  const artifactId = params.get("artifact") || "";
  const projectId = params.get("project") || getActiveProjectId() || "";

  return (
    <div className="h-full">
      <InsightsWorkspace
        projectId={projectId}
        initialPrompt={prompt}
        conversationId={conversationId}
        artifactId={artifactId}
      />
    </div>
  );
}

export default function InsightsSessionPage() {
  const { t } = useLingui();

  return (
    <Suspense fallback={<SkeletonDocument className="p-8" label={t`Loading the thread`} />}>
      <Session />
    </Suspense>
  );
}
