"use client";

import { useEffect, useState } from "react";
import InsightsList from "./InsightsList";
import { getActiveProjectId } from "../lib/projects";

export default function InsightsPageClient({ serverReports, mode = null, showGenerateButton = true }) {
  const [projectId, setProjectId] = useState(null);

  useEffect(() => {
    setProjectId(getActiveProjectId() || null);
  }, []);

  return (
    <InsightsList
      serverReports={serverReports}
      projectId={projectId}
      mode={mode}
      showGenerateButton={showGenerateButton}
    />
  );
}
