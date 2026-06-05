"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PostViewport from "@/components/content/PostViewport";
import { getActiveProjectId } from "@/lib/projects";

/**
 * Start a new draft_post session.
 *
 * Query params:
 *   - plan_id      (optional)  — anchor the draft to a specific plan
 *   - day          (optional)  — which Day in the plan we're drafting
 *   - topic, pillar (optional) — for standalone (no-plan) drafts
 *
 * Reached from PlanViewport's "Draft this post →" button on a day card.
 */
export default function NewPostDraftPage() {
  const router = useRouter();
  const search = useSearchParams();
  const [projectId, setProjectId] = useState(null);

  const planId    = search.get("plan_id") || undefined;
  const dayIndex  = search.get("day");
  const topic     = search.get("topic") || undefined;
  const pillar    = search.get("pillar") || undefined;
  const channel   = search.get("channel") || undefined;

  useEffect(() => {
    const id = getActiveProjectId();
    if (!id) { router.replace("/content"); return; }
    setProjectId(id);
  }, [router]);

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">Loading session…</p>
      </div>
    );
  }

  return (
    <div className="h-full">
      <ContentWorkspace
        mode="draft_post"
        context={{
          projectId,
          planId,
          dayIndex: dayIndex !== null && dayIndex !== undefined ? Number(dayIndex) : undefined,
          topic,
          pillar,
          channel,
        }}
        renderViewport={({ payload }) => <PostViewport payload={payload} />}
      />
    </div>
  );
}
