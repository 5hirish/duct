"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Hash,
  Image as ImageIcon,
  Images,
  LayoutTemplate,
  RefreshCw,
  Send,
  Sparkles,
  Type,
  Video,
  Wand2,
} from "lucide-react";
import { patchPost } from "../../lib/contentApi";
import { extractStyleHead } from "../../lib/slideDoc";
import { statusMeta } from "../../lib/contentStatus";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import SlidesCarousel from "./SlidesCarousel";

const STREAMING_HINTS = [
  "Picking the hook…",
  "Writing the caption…",
  "Choosing hashtags…",
  "Sketching image prompts…",
];

const TYPE_ICON = { slideshow: Images, video: Video, image: ImageIcon };

/**
 * Post viewport — the slides preview + an inline editor for the post's copy,
 * hook, and creative brief. Works full-page (post detail) and inside the
 * revise split-pane (container queries adapt the columns to the pane width).
 *
 * Props:
 *   - payload   : { type:"post", id, slides, slides_html, caption, hashtags[], ... }
 *   - canPublish, onPublish, onRevise — optional header actions (detail page)
 *   - onSendMessage(text) — when present (active session), enables the
 *     "approve & generate images" + per-slide regenerate actions, which send a
 *     chat turn to the agent. Absent on the read-only detail page.
 */
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

  async function handleCommit() {
    if (!post?.id) return;
    setSaving(true);
    setSaveError("");
    try {
      // Send `slides` (the source of truth) but NOT slides_html — the backend
      // re-renders the HTML from the slides + layout and recomputes staleness.
      const updated = await patchPost(post.id, {
        caption: post.caption, hashtags: post.hashtags,
        hook_type: post.hook_type, hook_text: post.hook_text, hook_emotion: post.hook_emotion,
        save_cta: post.save_cta, tiktok_title: post.tiktok_title, audio_note: post.audio_note,
        bridge_text: post.bridge_text, strategic_note: post.strategic_note,
        visual_brief: post.visual_brief, emotional_arc: post.emotional_arc,
        camera_ref_pool: post.camera_ref_pool,
        layout: post.layout, slides: post.slides,
        platforms: post.platforms, status: post.status,
      });
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

  // Persist any pending edits before asking the agent to act on a slide, so the
  // agent (which reads the saved post) regenerates against the latest prompt.
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
  const currentSlide = slides[slideIdx];
  function patchSlide(i, partial) {
    patch("slides", slides.map((s, j) => (j === i ? { ...s, ...partial } : s)));
  }

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
                <span className="rounded-full bg-primary/10 px-2 py-0.5 font-medium text-primary">{prettify(post.pillar)}</span>
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
            <button
              type="button"
              onClick={handleCommit}
              disabled={!dirty || saving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {saving ? "Saving…" : dirty ? "Commit edits" : <><Check className="size-3.5" /> Saved</>}
            </button>
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

      {/* Body — slide carousel + focused per-slide editor, post details below */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-2xl space-y-4 p-5">
          <SlidesCarousel slides={slides} headHtml={headHtml} index={slideIdx} onIndexChange={setCurrentIndex} />

          <BulkImageBar slides={slides} onSendMessage={onSendMessage} commitIfDirty={commitIfDirty} />

          <SlideEditor
            slide={currentSlide}
            index={slideIdx}
            total={slides.length}
            patchSlide={patchSlide}
            onSendMessage={onSendMessage}
            commitIfDirty={commitIfDirty}
          />

          <PostDetails post={post} patch={patch} />

          <CreativeBrief post={post} patch={patch} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

function prettify(s) {
  return String(s || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function Group({ icon: Icon, title, hint, children }) {
  return (
    <section className="rounded-2xl border border-border bg-card p-4">
      <div className="mb-3 flex items-baseline gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          {Icon && <Icon className="size-3.5 text-muted-foreground" />} {title}
        </h3>
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

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
function TextInput({ value, onChange, mono, italic, ...props }) {
  return <input value={value} onChange={(e) => onChange(e.target.value)} className={`${INPUT_CLS} ${mono ? "font-mono text-xs" : ""} ${italic ? "italic" : ""}`} {...props} />;
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

const HOOK_EMOTIONS = [
  { value: "frustration", hint: "I did everything right and still…" },
  { value: "shock", hint: "A [authority] just told me…" },
  { value: "disbelief", hint: "A free app knew more than my $300/hr…" },
  { value: "anger", hint: "They're selling you the wrong…" },
  { value: "sadness", hint: "I spent [years/money] on…" },
];

function HookEmotionPills({ value, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {HOOK_EMOTIONS.map(({ value: v, hint }) => {
        const active = value === v;
        return (
          <button key={v} type="button" onClick={() => onChange(active ? "" : v)} title={hint}
            className={`rounded-full border px-2.5 py-0.5 text-xs capitalize transition-colors ${
              active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-muted/50"
            }`}>
            {v}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Slides & images — per-slide image status, editable prompts, gated generation
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

function UnitBadge({ target }) {
  if (isTargetStale(target)) {
    return (
      <span className="inline-flex items-center gap-0.5 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
        <AlertTriangle className="size-2.5" /> outdated
      </span>
    );
  }
  if (target.image_url) {
    return (
      <span className="inline-flex items-center gap-0.5 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
        <Check className="size-2.5" /> image
      </span>
    );
  }
  return <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">prompt only</span>;
}

function UnitRow({ target, title, onPrompt, onGenerate, canAct }) {
  return (
    <div className="rounded-lg border border-border/50 bg-background/60 p-2">
      <div className="mb-1.5 flex items-start gap-2">
        {target.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={target.image_url} alt={title} className="size-10 shrink-0 rounded-md object-cover" />
        ) : (
          <div className="flex size-10 shrink-0 items-center justify-center rounded-md border border-dashed border-border bg-background text-muted-foreground/50">
            <ImageIcon className="size-4" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1">
            {title}
            <UnitBadge target={target} />
          </div>
        </div>
        {canAct && (
          <button
            type="button"
            onClick={onGenerate}
            title={target.image_url ? "Regenerate" : "Generate"}
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-muted/50"
          >
            {target.image_url ? <RefreshCw className="size-3" /> : <Sparkles className="size-3" />}
            {target.image_url ? "Regenerate" : "Generate"}
          </button>
        )}
      </div>
      <textarea
        rows={2}
        value={target.image_prompt || ""}
        onChange={(e) => onPrompt(e.target.value)}
        placeholder="Image prompt — the scene to generate."
        className={`${INPUT_CLS} resize-y font-mono text-[11px]`}
      />
    </div>
  );
}

// Batch image actions — generate all pending, or regenerate everything stale.
function BulkImageBar({ slides, onSendMessage, commitIfDirty }) {
  if (!onSendMessage) return null;
  const units = imageUnits(slides);
  const t = (u) => (u.it ? u.it : u.s);
  const pending = units.filter((u) => (t(u).image_prompt || "").trim() && !t(u).image_url).length;
  const staleCount = units.filter((u) => isTargetStale(t(u))).length;
  if (pending === 0 && staleCount === 0) return null;
  async function ask(text) { await commitIfDirty?.(); onSendMessage(text); }
  return (
    <div className="flex flex-wrap gap-2">
      {pending > 0 && (
        <button
          type="button"
          onClick={() => ask("The draft looks good — generate the images now, one at a time, for every slide (and every collage / before-after cell) that has a prompt but no image yet. View and critique each before moving on.")}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Sparkles className="size-3.5" /> Approve &amp; generate {pending} image{pending > 1 ? "s" : ""}
        </button>
      )}
      {staleCount > 0 && (
        <button
          type="button"
          onClick={() => ask("Regenerate the images whose prompt changed (the outdated ones) so they match the new prompts.")}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-amber-400/50 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-600 transition-colors hover:bg-amber-500/20 dark:text-amber-400"
        >
          <RefreshCw className="size-3.5" /> {staleCount} outdated — regenerate
        </button>
      )}
    </div>
  );
}

const SLIDE_KINDS = [
  { v: "photo", label: "Photo" },
  { v: "text", label: "Text" },
  { v: "collage", label: "Collage" },
  { v: "before-after", label: "Before / After" },
  { v: "editorial", label: "Editorial" },
];

const CAPTION_STYLES = [
  { v: "hook", label: "Hook" },
  { v: "cap-stroke", label: "Stroke" },
  { v: "cap-pill", label: "Pill" },
  { v: "cap-raw", label: "Raw" },
  { v: "cap-whisper", label: "Whisper" },
];

function Segmented({ options, value, onChange, small }) {
  return (
    <div className="flex flex-wrap gap-1">
      {options.map((o) => {
        const active = value === o.v;
        return (
          <button
            key={o.v}
            type="button"
            onClick={() => onChange(o.v)}
            className={`rounded-lg border px-2.5 py-1 ${small ? "text-[11px]" : "text-xs"} transition-colors ${
              active ? "border-primary bg-primary/10 font-medium text-primary" : "border-border text-muted-foreground hover:bg-muted/50"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function MarkerToggle({ value, onChange }) {
  return (
    <div className="flex overflow-hidden rounded-md border border-border text-[10px] font-bold">
      <button type="button" onClick={() => onChange("dont")}
        className={`px-2 py-0.5 ${value === "dont" ? "bg-rose-500 text-white" : "text-rose-500 hover:bg-rose-500/10"}`}>
        ✕ DON&apos;T
      </button>
      <button type="button" onClick={() => onChange("do")}
        className={`px-2 py-0.5 ${value === "do" ? "bg-emerald-500 text-white" : "text-emerald-500 hover:bg-emerald-500/10"}`}>
        ✓ DO
      </button>
    </div>
  );
}

function CellEditor({ item, index, kind, canAct, onChange, onGenerate }) {
  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-muted/20 p-2.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] text-muted-foreground">cell {index}</span>
        {kind === "before-after" && (
          <MarkerToggle value={item.marker || (index === 0 ? "dont" : "do")} onChange={(m) => onChange({ marker: m })} />
        )}
        <input
          value={item.label || ""}
          onChange={(e) => onChange({ label: e.target.value })}
          placeholder={kind === "before-after" ? "label (e.g. center part)" : "cell label"}
          className="flex-1 rounded-md border border-input bg-input/40 px-2 py-1 text-xs outline-none focus-visible:border-ring"
        />
      </div>
      <UnitRow target={item} title={null} canAct={canAct} onPrompt={(v) => onChange({ image_prompt: v })} onGenerate={onGenerate} />
    </div>
  );
}

// The focused editor for the currently-previewed slide: format, caption style,
// caption text, and the slide's image prompt(s) + generate / regenerate.
function SlideEditor({ slide, index, total, patchSlide, onSendMessage, commitIfDirty }) {
  if (!slide) return null;
  const kind = slide.kind || "photo";
  const sid = slide.slide_id || `slide-${String(index + 1).padStart(2, "0")}`;
  const canAct = Boolean(onSendMessage);
  const set = (partial) => patchSlide(index, partial);
  const setItem = (ci, partial) =>
    set({ items: (slide.items || []).map((it, j) => (j === ci ? { ...it, ...partial } : it)) });
  async function ask(text) {
    if (!canAct) return;
    await commitIfDirty?.();
    onSendMessage(text);
  }
  const isMulti = kind === "collage" || kind === "before-after";

  function setKind(v) {
    const partial = { kind: v };
    const noItems = !(slide.items || []).length;
    if (v === "collage" && noItems) {
      partial.items = [0, 1, 2, 3].map(() => ({ label: "", image_prompt: "", aspect_ratio: "9:16" }));
    } else if (v === "before-after" && noItems) {
      partial.items = [
        { marker: "dont", label: "", image_prompt: "", aspect_ratio: "9:16" },
        { marker: "do", label: "", image_prompt: "", aspect_ratio: "9:16" },
      ];
    }
    set(partial);
  }

  return (
    <Group icon={LayoutTemplate} title={`Slide ${index + 1} of ${total}`} hint={sid}>
      <Labeled label="Format" hint="how this slide is laid out">
        <Segmented options={SLIDE_KINDS} value={kind} onChange={setKind} />
      </Labeled>

      {kind === "photo" && (
        <Labeled label="Caption style" hint="treatment & weight">
          <Segmented options={CAPTION_STYLES} value={slide.caption_style || "cap-stroke"} onChange={(v) => set({ caption_style: v })} small />
        </Labeled>
      )}

      {!isMulti && (
        <>
          <Labeled label={kind === "text" ? "Statement" : kind === "editorial" ? "Serif headline" : "Headline"} hint="overlay caption">
            <Textarea rows={2} value={slide.headline || ""} onChange={(v) => set({ headline: v })} placeholder="Caption headline…" />
          </Labeled>
          <Labeled label="Subtext" hint="optional sub-line">
            <TextInput value={slide.subtext || ""} onChange={(v) => set({ subtext: v })} placeholder="optional sub-line" />
          </Labeled>
        </>
      )}
      {kind === "collage" && (
        <Labeled label="Serif title" hint="optional, above the grid">
          <TextInput value={slide.headline || ""} onChange={(v) => set({ headline: v })} placeholder="e.g. 4 cuts for a round face" />
        </Labeled>
      )}

      {kind === "text" ? (
        <p className="rounded-lg bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">Text card — no image.</p>
      ) : isMulti ? (
        <Labeled label={`Cells (${(slide.items || []).length})`}>
          {(slide.items || []).length === 0 ? (
            <p className="text-[11px] text-muted-foreground">No cells yet — ask Duct to add them, or switch Format to Photo.</p>
          ) : (
            <div className="space-y-2">
              {(slide.items || []).map((it, ci) => (
                <CellEditor
                  key={ci}
                  item={it}
                  index={ci}
                  kind={kind}
                  canAct={canAct}
                  onChange={(p) => setItem(ci, p)}
                  onGenerate={() => ask(`${it.image_url ? "Regenerate" : "Generate"} the image for ${sid} item_index ${ci}${it.label ? ` (the "${it.label}" cell)` : ""}.`)}
                />
              ))}
            </div>
          )}
        </Labeled>
      ) : (
        <Labeled label="Image">
          <UnitRow
            target={slide}
            title={null}
            canAct={canAct}
            onPrompt={(v) => set({ image_prompt: v })}
            onGenerate={() => ask(slide.image_url ? `Regenerate the image for ${sid} to match its current prompt.` : `Generate the image for ${sid} now.`)}
          />
        </Labeled>
      )}
      <p className="text-[11px] leading-relaxed text-muted-foreground/70">
        Edits preview live. Hit <span className="font-medium">Commit edits</span> to save. Changing an image prompt marks its image “outdated” until regenerated — captions are overlays and never need a regen.
      </p>
    </Group>
  );
}

// Post-level copy + hook, collapsed by default so the slide editor leads.
function PostDetails({ post, patch }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-2xl border border-border bg-card">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-2 p-4">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <Type className="size-3.5 text-muted-foreground" /> Post details
          <span className="text-xs font-normal text-muted-foreground">caption · hashtags · hook</span>
        </h3>
        <ChevronDown className={`size-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="space-y-4 border-t border-border/50 p-4">
          <Labeled label="Caption" hint="first line is the hook — 2–3 sentences">
            <Textarea rows={4} value={post.caption || ""} onChange={(v) => patch("caption", v)} placeholder="First line is the hook. Keep it 2–3 sentences." />
          </Labeled>
          <Labeled label="Hashtags">
            <HashtagInput value={Array.isArray(post.hashtags) ? post.hashtags : []} onChange={(v) => patch("hashtags", v)} />
          </Labeled>
          <Labeled label="Hook emotion" hint="drives slide 1">
            <HookEmotionPills value={post.hook_emotion || ""} onChange={(v) => patch("hook_emotion", v)} />
          </Labeled>
          <div className="grid gap-3 sm:grid-cols-2">
            <Labeled label="Hook type">
              <TextInput value={post.hook_type || ""} onChange={(v) => patch("hook_type", v)} placeholder="e.g. identity_challenge" mono />
            </Labeled>
            <Labeled label="Save CTA">
              <TextInput value={post.save_cta || ""} onChange={(v) => patch("save_cta", v)} placeholder='"save this — self-test on slide 3"' italic />
            </Labeled>
          </div>
          <Labeled label="Hook text">
            <Textarea rows={2} value={post.hook_text || ""} onChange={(v) => patch("hook_text", v)} placeholder="hook text — what slide 1 says" />
          </Labeled>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Creative brief — collapsible advanced fields
// ---------------------------------------------------------------------------

const CAMERA_REF_POOLS = [
  { value: "selfie-talking", hint: "default — indoor, speaking to camera" },
  { value: "lifestyle", hint: "outdoor / educational / gentle arc" },
  { value: "closeup", hint: "intimate / confessional / sadness" },
];

function CreativeBrief({ post, patch }) {
  const hasContent = [post.audio_note, post.bridge_text, post.strategic_note, post.visual_brief, post.emotional_arc]
    .some((v) => v && String(v).trim());
  const [open, setOpen] = useState(hasContent);

  return (
    <section className="rounded-2xl border border-border bg-card">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-2 p-4">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <Wand2 className="size-3.5 text-muted-foreground" /> Creative brief
          <span className="text-xs font-normal text-muted-foreground">production & agent notes</span>
        </h3>
        <ChevronDown className={`size-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-border/50 p-4">
          <Labeled label="Audio note">
            <TextInput value={post.audio_note || ""} onChange={(v) => patch("audio_note", v)} placeholder="trending sound shape that fits" />
          </Labeled>
          <Labeled label="Strategic note" hint="why this works">
            <Textarea rows={2} value={post.strategic_note || ""} onChange={(v) => patch("strategic_note", v)} placeholder="which pillar this reinforces, who it targets, why the hook fits." />
          </Labeled>
          <Labeled label="Slide-6 bridge" hint="first-person, self-deprecating">
            <Textarea rows={2} value={post.bridge_text || ""} onChange={(v) => patch("bridge_text", v)} placeholder='"I found a free app for this. one photo. 30 seconds."' />
          </Labeled>
          <Labeled label="Visual brief" hint="drives copy + image prompts">
            <div className="mb-1.5 flex flex-wrap gap-1">
              {CAMERA_REF_POOLS.map(({ value: v, hint }) => {
                const active = post.camera_ref_pool === v;
                return (
                  <button key={v} type="button" onClick={() => patch("camera_ref_pool", active ? "" : v)} title={hint}
                    className={`rounded border px-1.5 py-0.5 text-[10px] transition-colors ${
                      active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-muted/50"
                    }`}>
                    {v}
                  </button>
                );
              })}
            </div>
            <Textarea rows={4} value={post.visual_brief || ""} onChange={(v) => patch("visual_brief", v)}
              className={`${INPUT_CLS} resize-y font-mono text-xs`}
              placeholder="Lighting / setting / posture / gesture arc / copy voice." />
          </Labeled>
          <Labeled label="Emotional arc" hint="one line per slide">
            <Textarea rows={4} value={post.emotional_arc || ""} onChange={(v) => patch("emotional_arc", v)}
              placeholder={"01: quiet, phone at eye level\n02: leaning in, brow tightening\n03: animated, mid-explanation"} />
          </Labeled>
        </div>
      )}
    </section>
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
      <div className="size-10 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
      <p className="text-sm font-medium">Drafting the post…</p>
      <p className="text-xs text-muted-foreground transition-opacity duration-500">{STREAMING_HINTS[idx]}</p>
      <p className="max-w-xs text-[10px] text-muted-foreground/60">
        Slides, caption, and hashtags appear here as soon as the draft is ready. Usually 20–40 seconds.
      </p>
    </div>
  );
}
