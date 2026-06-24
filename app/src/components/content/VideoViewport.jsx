"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Film, Smartphone } from "lucide-react";
import { mediaUrl } from "@/lib/contentApi";

/**
 * Phone-framed video viewport — the right-pane preview for a video post
 * (post_type === "video"). Reuses the slideshow carousel UX (one item at a time,
 * prev/next + dots + keyboard + swipe + a position label), but its STACK is:
 *
 *   1. the generated clip (post.video_url) on top,
 *   2. [older versions — once we keep video version history; not wired yet],
 *   3. the storyboard beat keyframes (post.video_storyboard) in beat order.
 *
 * The player is the NATIVE <video> element — fastest + lightest + zero deps. It's
 * polished for UX: poster = the opening keyframe (instant first paint, no video
 * download until play), preload="metadata", playsInline, loop, native controls.
 * Only the current carousel item is mounted, so off-screen items never load.
 *
 * Props:
 *   - post: the post draft object (video_url, video_aspect_ratio, video_storyboard, …)
 */
export default function VideoViewport({ post }) {
  const beats = Array.isArray(post?.video_storyboard) ? post.video_storyboard : [];
  const videoUrl = post?.video_url || "";
  // Opening keyframe → the video's poster (instant frame before the clip loads).
  // Prefer the transient preview so a freshly generated keyframe paints instantly.
  const opening = beats.find((b) => b?._preview_uri || b?.image_url);
  const posterUrl = opening?._preview_uri || opening?.image_url || "";

  // Build the stack: clip first, then keyframes in sequence. A transformation
  // beat contributes BOTH its first frame and its 'after' frame so the user can
  // review/iterate on each (the 'after' was generated but never shown before).
  const items = [];
  if (videoUrl) {
    items.push({ kind: "video", url: videoUrl, label: "Generated video", poster: posterUrl });
  }
  beats.forEach((b, i) => {
    const label = b?.role ? prettyRole(b.role) : `Keyframe ${i + 1}`;
    items.push({
      kind: "image",
      url: b?._preview_uri || b?.image_url || "",
      prompt: b?.image_prompt || b?.motion || "",
      onScreenText: b?.on_screen_text || "",
      label,
    });
    const after = b?._end_preview_uri || b?.end_image_url || "";
    if (b?.is_transformation && after) {
      items.push({
        kind: "image",
        url: after,
        prompt: b?.end_image_prompt || "",
        onScreenText: b?.on_screen_text || "",
        label: `${label} · after`,
      });
    }
  });

  const total = items.length;
  const [index, setIndex] = useState(0);
  // Reset to the top of the stack (the clip) when switching to a different post.
  useEffect(() => { setIndex(0); }, [post?.id]);
  const clamped = Math.max(0, Math.min(index, Math.max(0, total - 1)));
  const current = items[clamped];
  const swipeX = useRef(null);
  const aspect = (post?.video_aspect_ratio || "9:16").replace(":", "/");

  function go(delta) {
    if (total < 2) return;
    setIndex(Math.max(0, Math.min(clamped + delta, total - 1)));
  }
  function onKeyDown(e) {
    if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
  }
  function onPointerDown(e) { swipeX.current = e.clientX; }
  function onPointerUp(e) {
    if (swipeX.current == null) return;
    const dx = e.clientX - swipeX.current;
    swipeX.current = null;
    if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
  }

  // Nothing generated or drafted yet → motion-brief placeholder (the old behaviour).
  if (total === 0) {
    return (
      <div className="overflow-hidden rounded-2xl border border-border bg-muted/20">
        <Header label="Video preview" right="clip" />
        <div className="flex items-center justify-center bg-black/80 p-3">
          <div className="relative flex w-full max-w-[340px] flex-col items-center justify-center gap-2 rounded-xl bg-black px-4 py-10 text-center text-white/70" style={{ aspectRatio: aspect }}>
            <Film className="size-8" />
            <p className="text-sm font-medium">No clip yet</p>
            <p className="max-w-[16rem] text-xs text-white/50">
              {post?.video_prompt ? `Will animate: ${post.video_prompt}` : "The clip + keyframes appear here as they're generated."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-muted/20">
      <Header label="Video preview" right={`${current.label} · ${clamped + 1} / ${total}`} />

      <div
        tabIndex={0}
        onKeyDown={onKeyDown}
        className="relative flex items-center justify-center bg-black/80 p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
      >
        <div
          className="relative w-full max-w-[340px] overflow-hidden rounded-xl bg-black shadow-lg"
          style={{ aspectRatio: aspect }}
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
        >
          {current.kind === "video" ? (
            <video
              key={current.url}
              src={mediaUrl(current.url)}
              poster={current.poster ? mediaUrl(current.poster) : undefined}
              controls
              playsInline
              loop
              preload="metadata"
              className="h-full w-full bg-black object-contain"
            />
          ) : current.url ? (
            <>
              <img
                src={mediaUrl(current.url)}
                alt={current.label}
                loading="lazy"
                className="h-full w-full bg-black object-contain"
              />
              {current.onScreenText && (
                <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                  <p className="text-center text-sm font-semibold leading-snug text-white drop-shadow">{current.onScreenText}</p>
                </div>
              )}
            </>
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-4 text-center text-white/60">
              <Film className="size-7" />
              <p className="text-xs font-medium">Keyframe not generated yet</p>
              {current.prompt && <p className="max-w-[15rem] text-[11px] text-white/40">{current.prompt}</p>}
            </div>
          )}
        </div>

        {total > 1 && clamped > 0 && <NavButton side="left" onClick={() => go(-1)} />}
        {total > 1 && clamped < total - 1 && <NavButton side="right" onClick={() => go(1)} />}
      </div>

      {total > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-1.5 px-3 py-2.5">
          {items.map((it, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setIndex(i)}
              title={it.label}
              className={`h-1.5 rounded-full transition-all ${
                i === clamped
                  ? `w-6 ${it.kind === "video" ? "bg-rose-500" : "bg-primary"}`
                  : "w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/60"
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function prettyRole(role) {
  const s = String(role || "").replace(/[_-]+/g, " ").trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "Keyframe";
}

function Header({ label, right }) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 px-3 py-1.5">
      <span className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Smartphone className="size-3.5" /> {label}
      </span>
      <span className="text-[10px] text-muted-foreground/70">{right}</span>
    </div>
  );
}

function NavButton({ side, onClick }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={side === "left" ? "Previous" : "Next"}
      className={`absolute top-1/2 z-20 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur transition-colors hover:bg-black/80 ${
        side === "left" ? "left-2" : "right-2"
      }`}
    >
      <Icon className="size-5" />
    </button>
  );
}
