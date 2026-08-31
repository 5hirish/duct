"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Hash,
  Image as ImageIcon,
  Images,
  RefreshCw,
  Send,
  Sparkles,
  Video,
  Wand2,
} from "lucide-react";
import { patchPost } from "../../lib/contentApi";
import { extractStyleHead } from "../../lib/slideDoc";
import { statusMeta } from "../../lib/contentStatus";
import { PostStatus } from "../../lib/contentEnums";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import SlidesCarousel from "./SlidesCarousel";
import { titleCase } from "@/lib/format";
import { Spinner } from "@/components/ui/spinner";

const STREAMING_HINTS = [
  "Picking the hook…",
  "Writing the caption…",
  "Choosing hashtags…",
  "Sketching image prompts…",
];

const TYPE_ICON = { slideshow: Images, video: Video, image: ImageIcon };

/**
 * Post viewport — preview-first. The right pane shows what actually ships: the
 * live slides preview plus the publishable copy (caption + hashtags). Slide
 * layout, image prompts, hook framing and the creative brief are all edited by
 * talking to the agent in chat, so the pane stays focused instead of being a
 * wall of form fields. Those fields still persist (see editedFields) — they're
 * just no longer surfaced here. Works full-page and inside the revise split-pane.
 *
 * Props:
 *   - payload   : { type:"post", id, slides, slides_html, caption, hashtags[], ... }
 *   - canPublish, onPublish, onRevise — optional header actions (detail page)
 *   - onSendMessage(text) — when present (active session), enables the
 *     "approve & generate images" action, which sends a chat turn to the agent.
 *     Absent on the read-only detail page.
 */
// Drop transient client-only fields (e.g. _preview_uri, the instant-paint inline
// data URI) from slides + cells before persisting — the DB stores only real urls.
function stripTransient(slides) {
  if (!Array.isArray(slides)) return slides;
  return slides.map(({ _preview_uri, items, ...s }) => ({
    ...s,
    ...(Array.isArray(items)
      ? { items: items.map(({ _preview_uri: _p, ...it }) => it) }
      : items !== undefined ? { items } : {}),
  }));
}

export default function PostViewport({ payload, canPublish = false, onPublish, onRevise, onSendMessage }) {
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (!payload || payload.type !== "post") return;
    if (!dirty) setDraft(payload);
  }, [payload, dirty]);

  const post = draft || payload;
  // CSS for the live preview comes from the backend-rendered slides_html (it
  // inlines the full style registry + layout CSS, all content-independent).
  const headHtml = useMemo(() => extractStyleHead(post?.slides_html || ""), [post?.slides_html]);

  function patch(field, value) {
    setDraft((prev) => ({ ...(prev || payload || {}), [field]: value }));
    setDirty(true);
  }

  // The editable fields sent on every save. `slides` is the source of truth —
  // we never send slides_html (the backend re-renders it from slides + layout).
  // Caption + hashtags are edited here; the rest are edited via chat but still
  // round-trip so an agent edit + a manual caption tweak persist together.
  function editedFields() {
    return {
      caption: post.caption, hashtags: post.hashtags,
      hook_type: post.hook_type, hook_text: post.hook_text, hook_emotion: post.hook_emotion,
      save_cta: post.save_cta, tiktok_title: post.tiktok_title, audio_note: post.audio_note,
      bridge_text: post.bridge_text, strategic_note: post.strategic_note,
      visual_brief: post.visual_brief, emotional_arc: post.emotional_arc,
      camera_ref_pool: post.camera_ref_pool,
      layout: post.layout, slides: stripTransient(post.slides),
      platforms: post.platforms,
    };
  }

  async function persist(statusValue) {
    if (!post?.id) return;
    setSaving(true);
    setSaveError("");
    try {
      const updated = await patchPost(post.id, { ...editedFields(), status: statusValue });
      setDraft(updated);
      setDirty(false);
      return updated;
    } catch (err) {
      setSaveError(err.message || "Failed to save post.");
      throw err;
    } finally {
      setSaving(false);
    }
  }

  // Save user edits, status unchanged.
  function handleCommit() { return persist(post.status); }

  // Keep the post: promote pending → draft (and persist current edits in the
  // same PATCH). Until this runs, the post is hidden from the board + the agent.
  function handleSave() { return persist(PostStatus.DRAFT); }

  // Persist any pending edits before asking the agent to act, so the agent
  // (which reads the saved post) works against the latest copy.
  async function commitIfDirty() {
    if (dirty) {
      try { await handleCommit(); } catch { /* surfaced via saveError */ }
    }
  }

  function handleDiscard() { setDraft(payload); setDirty(false); setSaveError(""); }

  if (!post || (post.type && post.type !== "post" && !post.id)) {
    return <DraftingPulse />;
  }

  const slides = Array.isArray(post.slides) ? post.slides : [];
  const slideIdx = Math.min(currentIndex, Math.max(0, slides.length - 1));

  const status = post.status || "pending";
  const meta = statusMeta(status);
  const TypeIcon = TYPE_ICON[post.post_type] || Images;
  const platforms = Array.isArray(post.platforms) ? post.platforms : [];
  const dateLabel = post.posted_at
    ? `Posted ${new Date(post.posted_at).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" })}`
    : post.scheduled_at
    ? `Scheduled ${new Date(post.scheduled_at).toLocaleDateString("en", { month: "short", day: "numeric" })}`
    : "Not scheduled";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Unified header */}
      <header className="shrink-0 border-b border-border/60 px-5 py-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold leading-tight">
              {post.topic || post.post_dir_slug || "Untitled post"}
            </h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium ${meta.accentClass}`}>
                <span className={`size-1.5 rounded-full ${meta.dotClass}`} /> {meta.label}
              </span>
              {post.pillar && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 font-medium text-primary">{titleCase(post.pillar)}</span>
              )}
              {post.format_name && (
                <span className="rounded-full border border-border/70 px-2 py-0.5">{post.format_name}</span>
              )}
              <span className="inline-flex items-center gap-1"><TypeIcon className="size-3" /> {post.post_type || "slideshow"}</span>
              {typeof post.slide_count === "number" && post.slide_count > 0 && <span>· {post.slide_count} slides</span>}
              <span>· {dateLabel}</span>
              {platforms.length > 0 && (
                <span className="flex items-center gap-1">
                  {platforms.map((p) => {
                    const pm = platformMeta(p);
                    return (
                      <span key={p} title={pm.label} className="flex size-4 items-center justify-center rounded text-white" style={{ backgroundColor: pm.color }}>
                        <PlatformGlyph platform={p} className="size-2.5" />
                      </span>
                    );
                  })}
                </span>
              )}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {dirty && (
              <button type="button" onClick={handleDiscard} className="text-xs text-muted-foreground hover:text-foreground">
                Discard
              </button>
            )}
            {post?.status === PostStatus.PENDING ? (
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                title="Keep this post — adds it to your board"
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {saving ? "Saving…" : <><Check className="size-3.5" /> Save</>}
              </button>
            ) : (
              <button
                type="button"
                onClick={handleCommit}
                disabled={!dirty || saving}
                className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {saving ? "Saving…" : dirty ? "Commit edits" : <><Check className="size-3.5" /> Saved</>}
              </button>
            )}
            {canPublish && onPublish && (
              <button type="button" onClick={onPublish} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted/50">
                <Send className="size-3.5" /> Publish
              </button>
            )}
            {onRevise && (
              <button type="button" onClick={onRevise} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90">
                <Wand2 className="size-3.5" /> Revise with Duct
              </button>
            )}
          </div>
        </div>
        {saveError && <p className="mt-2 text-xs text-destructive">{saveError}</p>}
      </header>

      {/* Body — the slides preview + the publishable copy (caption + hashtags).
          Slide layout, image prompts, hook and creative-brief edits all happen
          through the agent chat, so the pane stays focused on what ships. */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-2xl space-y-4 p-5">
          <SlidesCarousel slides={slides} headHtml={headHtml} index={slideIdx} onIndexChange={setCurrentIndex} />

          <BulkImageBar slides={slides} onSendMessage={onSendMessage} commitIfDirty={commitIfDirty} currentIndex={slideIdx} />

          <PostCopy post={post} patch={patch} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

function Labeled({ label, hint, children }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {hint && <span className="text-[11px] text-muted-foreground/70">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

const INPUT_CLS =
  "w-full rounded-xl border border-input bg-input/40 px-3 py-2 text-sm outline-none transition-[box-shadow,border-color] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/25 placeholder:text-muted-foreground";

function Textarea({ value, onChange, ...props }) {
  return <textarea value={value} onChange={(e) => onChange(e.target.value)} className={`${INPUT_CLS} resize-y`} {...props} />;
}

// ---------------------------------------------------------------------------
// Hashtags
// ---------------------------------------------------------------------------

function HashtagInput({ value, onChange }) {
  const [draft, setDraft] = useState("");
  function add() {
    const tag = draft.trim().replace(/^#?/, "#");
    if (tag === "#") { setDraft(""); return; }
    if (!value.includes(tag)) onChange([...value, tag]);
    setDraft("");
  }
  function onKey(e) {
    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
    else if (e.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-input bg-input/40 px-2.5 py-2">
      {value.map((tag, i) => (
        <span key={i} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
          {tag}
          <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))} className="text-primary/60 hover:text-primary">×</button>
        </span>
      ))}
      <span className="inline-flex min-w-[120px] flex-1 items-center gap-1 text-muted-foreground">
        <Hash className="size-3" />
        <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={add}
          placeholder="Add a tag, press Enter…" className="flex-1 bg-transparent text-xs outline-none" />
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Publishable copy — caption + hashtags, always visible
// ---------------------------------------------------------------------------

// The only post-level fields surfaced in the viewport: the caption and hashtags
// that actually get published. Everything else (hook framing, slide layout,
// image prompts, creative brief) is edited by asking the agent in chat.
function PostCopy({ post, patch }) {
  return (
    <section className="space-y-4 rounded-2xl border border-border bg-card p-4">
      <Labeled label="Caption" hint="first line is the hook — 2–3 sentences">
        <Textarea rows={4} value={post.caption || ""} onChange={(v) => patch("caption", v)} placeholder="First line is the hook. Keep it 2–3 sentences." />
      </Labeled>
      <Labeled label="Hashtags">
        <HashtagInput value={Array.isArray(post.hashtags) ? post.hashtags : []} onChange={(v) => patch("hashtags", v)} />
      </Labeled>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Slides & images — pending/stale detection drives the batch image action
// ---------------------------------------------------------------------------

function isTargetStale(t) {
  return Boolean(t?.image_url) && (t.image_prompt || "").trim() !== (t.image_prompt_used || "").trim();
}

// Flatten slides into image "units" — one per single-image slide, one per cell
// of a collage / before-after slide. text slides contribute none.
function imageUnits(slides) {
  const units = [];
  slides.forEach((s, si) => {
    if (Array.isArray(s.items) && s.items.length) {
      s.items.forEach((it, ii) => units.push({ s, si, it, ii }));
    } else if (s.kind !== "text") {
      units.push({ s, si, it: null, ii: null });
    }
  });
  return units;
}

// Batch image actions — generate all pending, or regenerate everything stale.
// Auto-hides when there's nothing to do, so it's invisible most of the time.
function BulkImageBar({ slides, onSendMessage, commitIfDirty, currentIndex = 0 }) {
  if (!onSendMessage) return null;
  const units = imageUnits(slides);
  const t = (u) => (u.it ? u.it : u.s);
  const pending = units.filter((u) => (t(u).image_prompt || "").trim() && !t(u).image_url).length;
  // Regenerate is scoped to the slide the user is viewing — never all of them.
  // (The per-slide "outdated" badge flags the others as you navigate.)
  const cur = slides[Math.min(currentIndex, Math.max(0, slides.length - 1))];
  const curStale =
    !!cur &&
    (isTargetStale(cur) ||
      (Array.isArray(cur.items) && cur.items.some((it) => isTargetStale(it))));
  if (pending === 0 && !curStale) return null;
  async function ask(text) { await commitIfDirty?.(); onSendMessage(text); }
  return (
    <div className="flex flex-wrap gap-2">
      {pending > 0 && (
        <button
          type="button"
          onClick={() => ask("The draft looks good — start the images, ONE AT A TIME with me in the loop. Generate the next slide (or cell) that still needs an image, critique it, render the composed slide, then STOP and wait for my feedback before the next one. Don't batch them — apply what I tell you to the following slides.")}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Sparkles className="size-3.5" /> Approve &amp; generate {pending} image{pending > 1 ? "s" : ""} — one by one
        </button>
      )}
      {curStale && (
        <button
          type="button"
          onClick={() => ask(`Regenerate just the image for ${cur.slide_id} — the slide I'm viewing — to match its updated prompt. Leave every other slide exactly as it is.`)}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-amber-400/50 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-600 transition-colors hover:bg-amber-500/20 dark:text-amber-400"
        >
          <RefreshCw className="size-3.5" /> This slide is outdated — regenerate
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drafting state
// ---------------------------------------------------------------------------

function DraftingPulse() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % STREAMING_HINTS.length), 1800);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
      <Spinner className="size-10 border-primary/30 border-t-primary" />
      <p className="text-sm font-medium">Drafting the post…</p>
      <p className="text-xs text-muted-foreground transition-opacity duration-500">{STREAMING_HINTS[idx]}</p>
      <p className="max-w-xs text-[10px] text-muted-foreground/60">
        Slides, caption, and hashtags appear here as soon as the draft is ready. Usually 20–40 seconds.
      </p>
    </div>
  );
}
