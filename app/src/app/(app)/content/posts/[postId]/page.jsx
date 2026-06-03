"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import PostViewport from "@/components/content/PostViewport";
import PublishModal from "@/components/content/PublishModal";
import { getPost } from "@/lib/contentApi";
import { getActiveProjectId } from "@/lib/projects";

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
  const { postId } = useParams();
  const router = useRouter();
  const [post, setPost] = useState(null);
  const [revise, setRevise] = useState(false);
  const [err, setErr] = useState("");
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
        if (!cancelled) setErr(e.message || "Failed to load post.");
      }
    })();
    return () => { cancelled = true; };
  }, [postId]);

  if (err) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-destructive">{err}</p>
      </div>
    );
  }
  if (!post) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">Loading post…</p>
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
            planId:   post.plan_id || undefined,
            dayIndex: post.day_index ?? undefined,
            topic:    post.topic   || undefined,
            pillar:   post.pillar  || undefined,
          }}
          renderViewport={({ payload }) => (
            <PostViewport payload={payload || { type: "post", ...post }} />
          )}
        />
      </div>
    );
  }

  const canPublish = post.status !== "posted";

  return (
    <div className="h-full flex flex-col">
      <header className="border-b border-border/60 px-4 py-2 flex items-center justify-between shrink-0 gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{post.topic || post.post_dir_slug}</p>
          <p className="text-xs text-muted-foreground truncate">
            {post.pillar} · {post.status}
            {post.posted_at ? ` · posted ${new Date(post.posted_at).toLocaleDateString()}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {canPublish && (
            <button
              type="button"
              onClick={() => setPublishOpen(true)}
              className="rounded-md border border-border bg-background px-3 py-1 text-xs font-medium hover:bg-muted/50"
            >
              Publish…
            </button>
          )}
          <button
            type="button"
            onClick={() => router.push(`/content/posts/${postId}?revise=1`)}
            className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            Revise with Duct →
          </button>
        </div>
      </header>
      <div className="flex-1 overflow-hidden">
        <PostViewport payload={{ type: "post", ...post }} />
      </div>

      <PublishModal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        post={post}
        onPublished={(updated) => setPost(updated)}
      />
    </div>
  );
}
