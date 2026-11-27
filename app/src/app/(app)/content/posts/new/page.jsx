"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Trans } from "@lingui/react/macro";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PostViewport from "@/components/content/PostViewport";
import PublishModal from "@/components/content/PublishModal";
import { getPlan } from "@/lib/contentApi";
import { getActiveProjectId } from "@/lib/projects";
import { useLeaveOnProjectSwitch } from "@/hooks/useActiveProjectId";

/**
 * Start a new draft_post session.
 *
 * Query params:
 *   - plan_id      (optional)  — anchor the draft to a specific plan
 *   - day          (optional)  — which Day in the plan we're drafting
 *   - topic, pillar (optional) — for standalone (no-plan) drafts
 *   - channel      (optional)  — the platform to write for (tiktok, linkedin,
 *                                twitter); picks the agent's playbook
 *   - clone_url    (optional)  — a TikTok post to model the draft on
 *
 * Reached from PlanViewport's "Draft this post →" button on a day card, and
 * from "New post" and "Clone a TikTok" on the Posts tab.
 *
 * This address is for a post that does not exist yet. Once the session makes
 * one, the address becomes the post's own, and a plan day that already holds
 * a post opens that post: reloading here used to start a second session on
 * the saved draft, which asked what to do with it and showed nothing on the
 * right, while the conversation the person was in sat unresumed (2026-11-27).
 */
export default function NewPostDraftPage() {
  const router = useRouter();
  const search = useSearchParams();
  const [projectId, setProjectId] = useState(null);
  // A plan day is checked for a post before any session starts.
  const [checked, setChecked] = useState(false);
  // The post to publish, set from the viewport: a draft made here is
  // published from here, not after a trip to its own page.
  const [publishing, setPublishing] = useState(null);
  // The draft is written into the project the page opened on.
  useLeaveOnProjectSwitch();

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

  useEffect(() => {
    if (!planId || dayIndex === null) { setChecked(true); return; }
    let cancelled = false;
    getPlan(planId)
      .then((plan) => {
        if (cancelled) return;
        const postId = plan?.days?.[Number(dayIndex)]?.post_id;
        if (postId) router.replace(`/content/posts/${postId}`);
        else setChecked(true);
      })
      .catch(() => { if (!cancelled) setChecked(true); });
    return () => { cancelled = true; };
  }, [planId, dayIndex, router]);

  if (!projectId || !checked) {
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
        renderViewport={({ payload, idle, failed, onSendMessage }) => (
          <>
          <PostAddress postId={payload?.id} />
          <PostViewport
            payload={payload}
            onSendMessage={onSendMessage}
            channel={channel}
            idle={idle}
            failed={failed}
            canPublish={Boolean(payload?.id)}
            onPublish={(post) => setPublishing(post || payload)}
          />
          </>
        )}
      />
      <PublishModal
        open={Boolean(publishing)}
        onClose={() => setPublishing(null)}
        post={publishing}
        onPublished={() => setPublishing(null)}
      />
    </div>
  );
}

/**
 * Once the session has made the post, the address is the post's, swapped in
 * place: no navigation, so the live session and its stream stay as they are,
 * and a reload opens the post with this conversation resumed.
 */
function PostAddress({ postId }) {
  useEffect(() => {
    if (!postId) return;
    const own = `/content/posts/${postId}`;
    if (window.location.pathname !== own) window.history.replaceState(window.history.state, "", own);
  }, [postId]);
  return null;
}
