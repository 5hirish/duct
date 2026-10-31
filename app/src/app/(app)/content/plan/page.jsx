"use client";

import { useSearchParams } from "next/navigation";
import { Trans } from "@lingui/react/macro";
import { useActiveProjectId, useProjectSwitched } from "@/hooks/useActiveProjectId";
import PlanBoard from "@/components/content/PlanBoard";

export default function PlanBoardPage() {
  const searchParams = useSearchParams();
  const requestedPlanId = searchParams.get("plan") || "";
  const projectId = useActiveProjectId();
  // ?plan= names a plan of the project this page opened on; after a switch
  // from the sidebar it would open that plan on the new project's board.
  const switched = useProjectSwitched();

  if (!projectId) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <Trans>Select a project in the sidebar to view its plan.</Trans>
      </div>
    );
  }

  return (
    <div className="h-full p-4">
      <PlanBoard key={projectId} projectId={projectId} initialPlanId={switched ? "" : requestedPlanId} />
    </div>
  );
}
