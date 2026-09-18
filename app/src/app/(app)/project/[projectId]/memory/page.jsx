"use client";

// Project memory — the timeline of what Duct knows about this account.
//
// Goals and decisions, incidents with when they started and ended, metrics for
// a period, actions taken on the account, artifacts produced. The rows and
// their affordances live in components/memory/MemoryTimeline; this page only
// binds them to the project-scoped API and names the place.

import { Suspense, use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SkeletonList } from "@/components/ui/skeleton";
import MemoryTimeline from "@/components/memory/MemoryTimeline";
import { hasAuthToken } from "@/lib/authFetch";
import { getProjectById } from "@/lib/projects";
import {
  MEMORY_KINDS,
  createMemory,
  deleteMemory,
  getMemory,
  listMemory,
  resetMemory,
  setMemoryPaused,
  updateMemory,
} from "@/lib/memoryApi";

function ProjectMemory({ projectId }) {
  // ?m=<id> — a chip in the chat linking to the entry behind an answer.
  const focusId = useSearchParams().get("m") || "";
  const [projectName, setProjectName] = useState("");
  const [signedIn, setSignedIn] = useState(true);

  useEffect(() => {
    setProjectName(getProjectById(projectId)?.name || "");
    setSignedIn(hasAuthToken());
  }, [projectId]);

  // Bound once per project so the timeline's effects don't re-run every render.
  const api = useMemo(
    () => ({
      list: (opts) => listMemory({ projectId, ...opts }),
      get: ({ memoryId }) => getMemory({ projectId, memoryId }),
      create: (entry) => createMemory({ projectId, ...entry }),
      patch: (patch) => updateMemory({ projectId, ...patch }),
      remove: ({ memoryId }) => deleteMemory({ projectId, memoryId }),
      setPaused: ({ paused }) => setMemoryPaused({ projectId, paused }),
      reset: () => resetMemory({ projectId }),
    }),
    [projectId]
  );

  return (
    <section>
      <div className="page-toolbar">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
          {projectName ? `${projectName} · Memory` : "Memory"}
        </h1>
        <div className="ml-auto flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href={`/project/${projectId}/members`}>
              <Users className="size-4" /> Members
            </Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link href="/projects">
              <ArrowLeft className="size-4" /> All projects
            </Link>
          </Button>
        </div>
      </div>

      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 14 }}>
        What Duct knows about this project. Agents read it before every run — confirm,
        correct, or pin a fact so it stays in view.
      </p>

      <MemoryTimeline
        errorSubject="this project's memory"
        api={api}
        signedIn={signedIn}
        focusId={focusId}
        kinds={MEMORY_KINDS.filter((k) => k !== "artifact")}
        defaultKind="decision"
        resetPrompt="Delete every memory for this project? This cannot be undone."
        emptyHint="Nothing remembered yet. Run an audit, apply a change, or set your targets in project settings — everything an agent concludes lands here with its evidence."
      />
    </section>
  );
}

// useSearchParams needs a Suspense boundary in the App Router.
export default function ProjectMemoryPage({ params }) {
  const { projectId } = use(params);
  return (
    <Suspense fallback={<SkeletonList rows={4} label="Loading memories" />}>
      <ProjectMemory projectId={projectId} />
    </Suspense>
  );
}
