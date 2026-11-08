"use client";

// Your memory — the Memory page opened on the private tab. The active
// project's shared memory is the other tab, so both kinds are one switch
// apart wherever you arrive from.

import { useEffect, useState } from "react";
import MemoryPage, { SCOPE_YOU } from "@/components/memory/MemoryPage";
import { getActiveProjectId } from "@/lib/projects";

export default function UserMemoryPage() {
  // Read after mount: the active project lives in browser storage.
  const [projectId, setProjectId] = useState("");
  useEffect(() => {
    setProjectId(getActiveProjectId() || "");
  }, []);

  return <MemoryPage key={projectId} projectId={projectId} initialScope={SCOPE_YOU} />;
}
