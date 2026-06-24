"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PostViewport from "@/components/content/PostViewport";
import { getActiveProjectId } from "@/lib/projects";

/**
 * Start a draft_post OR clone_post session.
 *
 * Query params:
 *   - plan_id        (optional)  — anchor to a specific plan
 *   - day            (optional)  — which Day in the plan we're drafting
 *   - topic, pillar  (optional)  — for standalone (no-plan) drafts
 *   - clone_post_id  (optional)  — when present, run clone_post against this
 *                                  pending post (it carries clone_source); the
 *                                  agent ingests its reference, then clones it.
 *
 * Reached from the board's "Draft this post →" and the Add-post modal's Draft-now.
 */
export default function NewPostDraftPage() {
  const router = useRouter();
  const search = useSearchParams();
  const [projectId, setProjectId] = useState(null);

  const planId      = search.get("plan_id") || undefined;
  const dayIndex    = search.get("day");
  const topic       = search.get("topic") || undefined;
  const pillar      = search.get("pillar") || undefined;
  const channel     = search.get("channel") || undefined;
  const postType    = search.get("post_type") || undefined;
  const clonePostId = search.get("clone_post_id") || undefined;

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

  const isClone = Boolean(clonePostId);
  const mode = isClone ? "clone_post" : "draft_post";
  const context = isClone
    ? { projectId, postId: clonePostId, planId, channel }
    : {
        projectId,
        planId,
        dayIndex: dayIndex !== null && dayIndex !== undefined ? Number(dayIndex) : undefined,
        topic,
        pillar,
        channel,
        postType,
      };

  return (
    <div className="h-full">
      <ContentWorkspace
        mode={mode}
        context={context}
        renderViewport={({ payload, assessment, phase, steps, onSendMessage }) => (
          <PostViewport payload={payload} assessment={assessment} phase={phase} steps={steps} onSendMessage={onSendMessage} />
        )}
      />
    </div>
  );
}
