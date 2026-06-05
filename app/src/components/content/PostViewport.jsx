"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  Hash,
  Image as ImageIcon,
  Images,
  Send,
  Smartphone,
  Sparkles,
  Type,
  Video,
  Wand2,
} from "lucide-react";
import { patchPost } from "../../lib/contentApi";
import { statusMeta } from "../../lib/contentStatus";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";

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
 *   - payload   : { type:"post", id, slides_html, caption, hashtags[], ... }
 *   - canPublish, onPublish, onRevise — optional header actions (detail page)
 */
export default function PostViewport({ payload, canPublish = false, onPublish, onRevise }) {
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    if (!payload || payload.type !== "post") return;
    if (!dirty) setDraft(payload);
  }, [payload, dirty]);

  const post = draft || payload;

  function patch(field, value) {
    setDraft((prev) => ({ ...(prev || payload || {}), [field]: value }));
    setDirty(true);
  }

  async function handleCommit() {
    if (!post?.id) return;
    setSaving(true);
    setSaveError("");
    try {
      const updated = await patchPost(post.id, {
        caption: post.caption, hashtags: post.hashtags,
        hook_type: post.hook_type, hook_text: post.hook_text, hook_emotion: post.hook_emotion,
        save_cta: post.save_cta, tiktok_title: post.tiktok_title, audio_note: post.audio_note,
        bridge_text: post.bridge_text, strategic_note: post.strategic_note,
        visual_brief: post.visual_brief, emotional_arc: post.emotional_arc,
        camera_ref_pool: post.camera_ref_pool, slides_html: post.slides_html,
        platforms: post.platforms, status: post.status,
      });
      setDraft(updated);
      setDirty(false);
    } catch (err) {
      setSaveError(err.message || "Failed to save post.");
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() { setDraft(payload); setDirty(false); setSaveError(""); }

  if (!post || (post.type && post.type !== "post" && !post.id)) {
    return <DraftingPulse />;
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

      {/* Body — slides hero + editor, two columns when the pane is wide */}
      <div className="@container min-h-0 flex-1 overflow-auto">
        <div className="grid gap-5 p-5 @4xl:grid-cols-[minmax(0,1fr)_minmax(360px,420px)]">
          {/* Slides hero */}
          <div className="@4xl:sticky @4xl:top-0 @4xl:self-start">
            <SlidesPreview html={post.slides_html} />
          </div>

          {/* Editor column */}
          <div className="space-y-4">
            <Group icon={Type} title="Copy">
              <Labeled label="Caption" hint="First line is the hook — keep it 2–3 sentences.">
                <Textarea rows={4} value={post.caption || ""} onChange={(v) => patch("caption", v)}
                  placeholder="First line is the hook. Keep it 2–3 sentences." />
              </Labeled>
              <Labeled label="Hashtags">
                <HashtagInput value={Array.isArray(post.hashtags) ? post.hashtags : []} onChange={(v) => patch("hashtags", v)} />
              </Labeled>
            </Group>

            <Group icon={Sparkles} title="Hook" hint="What slide 1 says.">
              <Labeled label="Emotion" hint="Drives slide 1 — pick one.">
                <HookEmotionPills value={post.hook_emotion || ""} onChange={(v) => patch("hook_emotion", v)} />
              </Labeled>
              <div className="grid gap-3 @md:grid-cols-2">
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
            </Group>

            <CreativeBrief post={post} patch={patch} />
          </div>
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
// Slides preview — phone-framed
// ---------------------------------------------------------------------------

function SlidesPreview({ html }) {
  const safeHtml = useMemo(() => (html ? String(html).replace(/<script\b[\s\S]*?<\/script>/gi, "") : ""), [html]);
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-muted/20">
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-1.5">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <Smartphone className="size-3.5" /> Slides preview
        </span>
        <span className="text-[10px] text-muted-foreground/70">sandboxed</span>
      </div>
      {safeHtml ? (
        <div className="bg-black/80 p-3">
          <iframe
            title="slides preview"
            sandbox="allow-same-origin"
            srcDoc={safeHtml}
            className="mx-auto aspect-[9/16] w-full max-w-[360px] rounded-xl bg-white shadow-lg"
          />
        </div>
      ) : (
        <div className="flex aspect-[9/16] max-h-[520px] w-full flex-col items-center justify-center gap-2 text-center text-muted-foreground/60">
          <Images className="size-8" />
          <p className="text-sm font-medium">No slides yet</p>
          <p className="max-w-[16rem] text-xs">Slides appear here once the draft is generated. Use “Revise with Duct” to build them.</p>
        </div>
      )}
    </div>
  );
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
// Creative brief — collapsible advanced fields
// ---------------------------------------------------------------------------

const CAMERA_REF_POOLS = [
  { value: "selfie-talking", hint: "default — indoor, speaking to camera" },
  { value: "lifestyle", hint: "outdoor / educational / gentle arc" },
  { value: "closeup", hint: "intimate / confessional / sadness" },
];

function CreativeBrief({ post, patch }) {
  const hasContent = [post.audio_note, post.bridge_text, post.strategic_note, post.visual_brief, post.emotional_arc]
    .some((v) => v && String(v).trim()) || (post.image_prompts || []).length > 0;
  const [open, setOpen] = useState(hasContent);
  const imagePrompts = Array.isArray(post.image_prompts) ? post.image_prompts : [];

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
          {imagePrompts.length > 0 && (
            <Labeled label={`Image prompts (${imagePrompts.length})`}>
              <ul className="space-y-1.5 rounded-xl border border-border/60 bg-muted/20 p-2">
                {imagePrompts.map((p, i) => (
                  <li key={i} className="text-xs">
                    <span className="font-mono text-[10px] text-muted-foreground">{p.slide_id || `slide-${i + 1}`}</span>
                    <p className="line-clamp-2 text-muted-foreground">{p.prompt}</p>
                  </li>
                ))}
              </ul>
            </Labeled>
          )}
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
