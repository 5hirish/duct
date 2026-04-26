"use client";

import { useEffect, useState } from "react";
import ReportsList from "./ReportsList";
import { getActiveProjectId } from "../lib/projects";

export default function ReportsPageClient({ serverReports, mode = null }) {
  const [projectId, setProjectId] = useState(null);

  useEffect(() => {
    setProjectId(getActiveProjectId() || null);
  }, []);

  return <ReportsList serverReports={serverReports} projectId={projectId} mode={mode} />;
}
