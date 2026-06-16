"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Images, Smartphone } from "lucide-react";
import { buildSlideDoc } from "@/lib/slideDoc";

/**
 * Phone-framed slide carousel — renders ONE structured slide at a time, scaled
 * to fit, with prev/next + dots + keyboard + swipe. The preview is rendered
 * client-side from the structured `slides` (live as the user edits) using the
 * CSS the backend already inlined (passed as `headHtml`). See lib/slideDoc.js.
 *
 * Props:
 *   - slides: structured slide objects (post.slides)
 *   - headHtml: <link>/<style> extracted from slides_html (extractStyleHead)
 *   - index, onIndexChange: controlled current-slide index
 *   - maxHeight: cap for the rendered phone height (px)
 */
export default function SlidesCarousel({ slides = [], headHtml = "", index = 0, onIndexChange, maxHeight = 600 }) {
  const boxRef = useRef(null);
  const [boxW, setBoxW] = useState(340);
  const swipeX = useRef(null);

  useEffect(() => {
    const el = boxRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width;
      if (w) setBoxW(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const total = slides.length;
  const clamped = Math.max(0, Math.min(index, Math.max(0, total - 1)));
  const current = slides[clamped];

  // Debounce the rendered slide so typing a caption doesn't reload the iframe
  // on every keystroke (which would flicker).
  const currentKey = useMemo(() => JSON.stringify(current ?? null), [current]);
  const [debKey, setDebKey] = useState(currentKey);
  useEffect(() => {
    const t = setTimeout(() => setDebKey(currentKey), 180);
    return () => clearTimeout(t);
  }, [currentKey]);

  const zoom = Math.min((boxW || 340) / 1080, maxHeight / 1920);
  const w = Math.max(1, Math.round(1080 * zoom));
  const h = Math.max(1, Math.round(1920 * zoom));

  const srcDoc = useMemo(() => {
    let slide;
    try { slide = JSON.parse(debKey); } catch { slide = null; }
    return slide ? buildSlideDoc(slide, clamped + 1, headHtml, zoom) : "";
  }, [debKey, clamped, headHtml, zoom]);

  function go(delta) {
    if (total < 2) return;
    const next = Math.max(0, Math.min(clamped + delta, total - 1));
    if (next !== clamped) onIndexChange?.(next);
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

  if (total === 0) {
    return (
      <div className="overflow-hidden rounded-2xl border border-border bg-muted/20">
        <CarouselHeader index={0} total={0} />
        <div className="flex aspect-[9/16] max-h-[520px] w-full flex-col items-center justify-center gap-2 text-center text-muted-foreground/60">
          <Images className="size-8" />
          <p className="text-sm font-medium">No slides yet</p>
          <p className="max-w-[16rem] text-xs">Slides appear here as the agent drafts them.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-muted/20">
      <CarouselHeader index={clamped} total={total} />

      <div
        ref={boxRef}
        tabIndex={0}
        onKeyDown={onKeyDown}
        className="relative flex items-center justify-center bg-black/80 p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
      >
        <div className="relative" style={{ width: w, height: h }}>
          <iframe
            title={`slide ${clamped + 1} preview`}
            sandbox="allow-same-origin"
            srcDoc={srcDoc}
            scrolling="no"
            className="block rounded-xl border-0 bg-white shadow-lg"
            style={{ width: w, height: h }}
          />
          {/* transparent layer to catch swipes over the iframe */}
          <div
            className="absolute inset-0 z-10 cursor-grab"
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
          />
        </div>

        {total > 1 && clamped > 0 && (
          <NavButton side="left" onClick={() => go(-1)} />
        )}
        {total > 1 && clamped < total - 1 && (
          <NavButton side="right" onClick={() => go(1)} />
        )}
      </div>

      {total > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-1.5 px-3 py-2.5">
          {slides.map((s, i) => (
            <button
              key={s.slide_id || i}
              type="button"
              onClick={() => onIndexChange?.(i)}
              title={`Slide ${i + 1}${s.kind && s.kind !== "photo" ? ` · ${s.kind}` : ""}`}
              className={`h-1.5 rounded-full transition-all ${
                i === clamped ? "w-6 bg-primary" : "w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/60"
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CarouselHeader({ index, total }) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 px-3 py-1.5">
      <span className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Smartphone className="size-3.5" /> Slides preview
      </span>
      <span className="text-[10px] text-muted-foreground/70">
        {total > 0 ? `${index + 1} / ${total}` : "sandboxed"}
      </span>
    </div>
  );
}

function NavButton({ side, onClick }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={side === "left" ? "Previous slide" : "Next slide"}
      className={`absolute top-1/2 z-20 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur transition-colors hover:bg-black/80 ${
        side === "left" ? "left-2" : "right-2"
      }`}
    >
      <Icon className="size-5" />
    </button>
  );
}
