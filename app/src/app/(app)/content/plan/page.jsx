"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Trans } from "@lingui/react/macro";
import { getActiveProjectId } from "@/lib/projects";
import PlanBoard from "@/components/content/PlanBoard";

export default function PlanBoardPage() {
  const searchParams = useSearchParams();
  const requestedPlanId = searchParams.get("plan") || "";
  const [projectId, setProjectId] = useState(null);

  useEffect(() => {
    setProjectId(getActiveProjectId() || "");
  }, []);

  if (!projectId) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <Trans>Select a project in the sidebar to view its plan.</Trans>
      </div>
    );
  }

  return (
    <div className="h-full p-4">
      <PlanBoard projectId={projectId} initialPlanId={requestedPlanId} />
    </div>
  );
}
