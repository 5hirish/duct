"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Trans } from "@lingui/react/macro";
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
 *   - clone_url    (optional)  — a TikTok post to model the draft on
 *
 * Reached from PlanViewport's "Draft this post →" button on a day card, and
 * from "Clone a TikTok" on the Posts tab.
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
  const cloneUrl  = search.get("clone_url") || undefined;

  useEffect(() => {
    const id = getActiveProjectId();
    if (!id) { router.replace("/content"); return; }
    setProjectId(id);
  }, [router]);

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground"><Trans>Loading session…</Trans></p>
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
          cloneUrl,
        }}
        renderViewport={({ payload, onSendMessage }) => (
          <PostViewport payload={payload} onSendMessage={onSendMessage} />
        )}
      />
    </div>
  );
}
