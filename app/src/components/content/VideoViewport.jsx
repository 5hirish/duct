"use client";

import { Film, Smartphone } from "lucide-react";
import { mediaUrl } from "@/lib/contentApi";

/**
 * Phone-framed video preview — the right-pane viewport for a video post
 * (post_type === "video"). Plays the single generated clip (post.video_url) in a
 * 9:16 frame, mirroring SlidesCarousel's framing. While the clip is still being
 * generated (no video_url yet) it shows the motion brief as a placeholder.
 *
 * Props:
 *   - post: the post draft object (reads video_url, video_prompt, video_aspect_ratio)
 */
export default function VideoViewport({ post }) {
  const src = mediaUrl(post?.video_url || "");
  const aspect = (post?.video_aspect_ratio || "9:16").replace(":", "/");

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-muted/20">
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-1.5">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <Smartphone className="size-3.5" /> Video preview
        </span>
        <span className="text-[10px] text-muted-foreground/70">
          {post?.video_duration_seconds ? `${post.video_duration_seconds}s` : "clip"}
        </span>
      </div>

      <div className="flex items-center justify-center bg-black/80 p-3">
        <div
          className="relative w-full max-w-[340px] overflow-hidden rounded-xl bg-black shadow-lg"
          style={{ aspectRatio: aspect }}
        >
          {src ? (
            <video
              key={src}
              src={src}
              controls
              playsInline
              loop
              preload="metadata"
              className="h-full w-full bg-black object-contain"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-4 text-center text-white/70">
              <Film className="size-8" />
              <p className="text-sm font-medium">No clip yet</p>
              <p className="max-w-[16rem] text-xs text-white/50">
                {post?.video_prompt
                  ? `Will animate: ${post.video_prompt}`
                  : "The clip appears here once Higgsfield finishes generating it."}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
