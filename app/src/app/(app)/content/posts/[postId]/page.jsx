"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Trans, useLingui } from "@lingui/react/macro";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PostViewport from "@/components/content/PostViewport";
import PublishModal from "@/components/content/PublishModal";
import PostMetricsForm from "@/components/content/PostMetricsForm";
import { getPost } from "@/lib/contentApi";
import { PostStatus } from "@/lib/contentEnums";
import { getActiveProjectId } from "@/lib/projects";
import LoadError from "@/components/LoadError";

/**
 * Per-post draft workspace. Two routes here:
 *
 *   /content/posts/{postId}         — existing post; renders viewport
 *                                      seeded from GET /api/content/posts/{id};
 *                                      no SSE session is started unless the
 *                                      user clicks "Ask Duct to revise".
 *
 *   /content/posts/{postId}?revise=1 — open the workspace AND start a
 *                                      draft_post SSE session bound to
 *                                      this post id (for re-drafting).
 *
 * For MVP this page always starts a draft_post session if the URL carries
 * ?revise=1, otherwise it shows the existing post in a read-only viewport
 * wrapped in a "Revise with Duct →" CTA.
 */
export default function PostDetailPage() {
  const { t } = useLingui();
  const { postId } = useParams();
  const router = useRouter();
  const [post, setPost] = useState(null);
  const [revise, setRevise] = useState(false);
  const [err, setErr] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [publishOpen, setPublishOpen] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      setRevise(url.searchParams.get("revise") === "1");
    }
  }, []);

  useEffect(() => {
    if (!postId) return;
    let cancelled = false;
    (async () => {
      try {
        const p = await getPost(postId);
        if (!cancelled) setPost(p);
      } catch (e) {
        if (!cancelled) setErr(e.message || "");
      }
    })();
    return () => { cancelled = true; };
  }, [postId, reloadKey]);

  if (err) {
    return (
      <div className="mx-auto w-full max-w-2xl px-4">
        <LoadError what={t`this post`} detail={err} onRetry={() => { setErr(""); setReloadKey((k) => k + 1); }} />
      </div>
    );
  }
  if (!post) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground"><Trans>Loading post…</Trans></p>
      </div>
    );
  }

  // Revise mode → open a workspace + SSE session targeting this post.
  if (revise) {
    const projectId = post.project_id || getActiveProjectId();
    return (
      <div className="h-full">
        <ContentWorkspace
          mode="draft_post"
          context={{
            projectId,
            postId:   post.id,
            planId:   post.plan_id || undefined,
            topic:    post.topic   || undefined,
            pillar:   post.pillar  || undefined,
            channel:  (Array.isArray(post.platforms) && post.platforms[0]) || undefined,
            // Resume this post's prior conversation when one exists (set by the
            // backend on GET /content/posts/{id}); otherwise open fresh. Pass the
            // artifact so that even a stale conversation id falls back to (or
            // rebinds) this post's active conversation rather than orphaning one.
            artifactType: "post",
            artifactId:   post.id,
            ...(post.active_conversation_id
              ? { conversationId: post.active_conversation_id, resume: true }
              : {}),
          }}
          renderViewport={({ payload, onSendMessage }) => (
            <PostViewport
              payload={payload || { type: "post", ...post }}
              onSendMessage={onSendMessage}
            />
          )}
        />
      </div>
    );
  }

  const canPublish = post.status !== PostStatus.POSTED;

  return (
    <div className="h-full">
      <PostViewport
        payload={{ type: "post", ...post }}
        canPublish={canPublish}
        onPublish={() => setPublishOpen(true)}
        onRevise={() => router.push(`/content/posts/${postId}?revise=1`)}
      >
        {/* Only perf changes on a metrics save; taking the whole reply would
            drop active_conversation_id, which only GET /posts/{id} carries. */}
        {post.status === PostStatus.POSTED && (
          <PostMetricsForm
            key={post.id}
            post={post}
            onSaved={(updated) => setPost((prev) => ({ ...prev, perf: updated.perf }))}
          />
        )}
      </PostViewport>

      <PublishModal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        post={post}
        onPublished={(updated) => setPost(updated)}
      />
    </div>
  );
}
