"use client";

// Project memory — the Memory page opened on this project's shared memory,
// with your private memory one tab away. Everything is MemoryPage's.

import { Suspense, use } from "react";
import { useSearchParams } from "next/navigation";
import { useLingui } from "@lingui/react/macro";
import { SkeletonList } from "@/components/ui/skeleton";
import MemoryPage, { SCOPE_PROJECT } from "@/components/memory/MemoryPage";

function ProjectMemory({ projectId }) {
  const { t } = useLingui();
  // ?m=<id> — a chip in the chat linking to the entry behind an answer.
  const focusId = useSearchParams().get("m") || "";
  return (
    <MemoryPage
      projectId={projectId}
      initialScope={SCOPE_PROJECT}
      focusId={focusId}
      back={{ href: "/projects", label: t`Projects` }}
    />
  );
}

// useSearchParams needs a Suspense boundary in the App Router.
export default function ProjectMemoryPage({ params }) {
  const { t } = useLingui();
  const { projectId } = use(params);
  return (
    <Suspense fallback={<SkeletonList rows={4} label={t`Loading memories`} />}>
      <ProjectMemory projectId={projectId} />
    </Suspense>
  );
}
