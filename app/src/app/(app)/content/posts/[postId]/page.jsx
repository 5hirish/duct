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
import { useLeaveOnProjectSwitch } from "@/hooks/useActiveProjectId";
import LoadError from "@/components/LoadError";

/**
 * One post, in one of two places:
 *
 *   the workspace — chat on the left, the post on the right, bound to this
 *     post. A draft (or an unsaved one) always opens here: it is still being
 *     made, and its own chat resumes when it has one. Anything else opens
 *     here with ?revise=1.
 *
 *   the read-only view — a scheduled, posted or failed post, with Publish
 *     and "Revise with Duct". No session starts until that button.
 *
 * Every link to a post is the plain URL; this page decides. Drafts opened on
 * the read-only view from the plan board and the drafts queue (2026-11-08),
 * where nothing could be changed and the chat was one more click away.
 */
// Statuses that open in the workspace without being asked to.
const IN_THE_MAKING = new Set([PostStatus.PENDING, PostStatus.DRAFT]);

export default function PostDetailPage() {
  const { t } = useLingui();
  const { postId } = useParams();
  const router = useRouter();
  const [post, setPost] = useState(null);
  const [revise, setRevise] = useState(false);
  const [err, setErr] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [publishOpen, setPublishOpen] = useState(false);
  // A post belongs to one project; the sidebar naming another is a request
  // to work there.
  useLeaveOnProjectSwitch();

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

  const canPublish = post.status !== PostStatus.POSTED;
  const publishModal = (
    <PublishModal
      open={publishOpen}
      onClose={() => setPublishOpen(false)}
      post={post}
      onPublished={(updated) => setPost(updated)}
    />
  );

  // A post still being made opens in the workspace, bound to this post.
  if (revise || IN_THE_MAKING.has(post.status)) {
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
              canPublish={canPublish}
              onPublish={() => setPublishOpen(true)}
            />
          )}
        />
        {publishModal}
      </div>
    );
  }

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

      {publishModal}
    </div>
  );
}
