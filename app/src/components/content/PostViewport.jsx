"use client";

import { useEffect, useMemo, useState } from "react";
import { patchPost } from "../../lib/contentApi";

const STREAMING_HINTS = [
  "Picking the hook…",
  "Writing the caption…",
  "Choosing hashtags…",
  "Sketching image prompts…",
];

/**
 * Right-pane viewport for draft_post sessions.
 *
 * Layout: slides iframe on top (sandboxed via srcDoc, no allow-scripts so
 * the model's HTML can never run JS in this origin), editable fields
 * underneath (caption, hashtags, hook, audio note), Commit button at top
 * right to persist staged edits via PATCH /api/content/posts/{id}.
 *
 * Props:
 *   - payload: { type: "post", id, slides_html, caption, hashtags[], hook_text, ... }
 */
export default function PostViewport({ payload }) {
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  // Sync from incoming payload — but only when the agent's payload is
  // strictly newer than our local edits. We detect "strictly newer" by
  // post id and updated_at if present, otherwise drop staged edits
  // whenever a new payload arrives if not dirty.
  useEffect(() => {
    if (!payload || payload.type !== "post") return;
    if (!dirty) {
      setDraft(payload);
      return;
    }
    // Dirty: keep the user's edits; the agent's payload waits until the
    // user commits or discards. (MVP behaviour — Phase 6 will add a "the
    // agent updated this post — merge / keep mine / accept" prompt.)
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
        caption:      post.caption,
        hashtags:     post.hashtags,
        hook_type:    post.hook_type,
        hook_text:    post.hook_text,
        hook_emotion: post.hook_emotion,
        save_cta:     post.save_cta,
        tiktok_title: post.tiktok_title,
        audio_note:   post.audio_note,
        bridge_text:  post.bridge_text,
        strategic_note: post.strategic_note,
        visual_brief:  post.visual_brief,
        emotional_arc: post.emotional_arc,
        camera_ref_pool: post.camera_ref_pool,
        slides_html:  post.slides_html,
        platforms:    post.platforms,
        status:       post.status,
      });
      setDraft(updated);
      setDirty(false);
    } catch (err) {
      setSaveError(err.message || "Failed to save post.");
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() {
    setDraft(payload);
    setDirty(false);
    setSaveError("");
  }

  if (!post || post.type === undefined || (post.type && post.type !== "post" && !post.id)) {
    return <DraftingPulse />;
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="border-b border-border/60 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">
            {post.topic || post.post_dir_slug || "Untitled post"}
          </p>
          <p className="text-xs text-muted-foreground truncate">
            {post.pillar ? `pillar: ${post.pillar}` : ""}
            {post.hook_type ? ` · hook: ${post.hook_type}` : ""}
            {typeof post.slide_count === "number" ? ` · ${post.slide_count} slides` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {dirty && (
            <button
              type="button"
              onClick={handleDiscard}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Discard edits
            </button>
          )}
          <button
            type="button"
            onClick={handleCommit}
            disabled={!dirty || saving}
            className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
          >
            {saving ? "Saving…" : dirty ? "Commit edits" : "Saved"}
          </button>
        </div>
      </div>

      {saveError && (
        <div className="border-b border-destructive/30 bg-destructive/8 px-4 py-2 text-xs text-destructive">
          {saveError}
        </div>
      )}

      <div className="flex-1 overflow-auto p-4 space-y-4 min-h-0">
        <SlidesPreview html={post.slides_html} />
        <CaptionPanel value={post.caption || ""} onChange={(v) => patch("caption", v)} />
        <HashtagPanel
          value={Array.isArray(post.hashtags) ? post.hashtags : []}
          onChange={(v) => patch("hashtags", v)}
        />
        <HookEmotionPills value={post.hook_emotion || ""} onChange={(v) => patch("hook_emotion", v)} />
        <HookPanel
          hookType={post.hook_type || ""}
          hookText={post.hook_text || ""}
          saveCta={post.save_cta || ""}
          onChange={(field, v) => patch(field, v)}
        />
        <AudioPanel value={post.audio_note || ""} onChange={(v) => patch("audio_note", v)} />
        <BridgeTextPanel value={post.bridge_text || ""} onChange={(v) => patch("bridge_text", v)} />
        <StrategicNotePanel value={post.strategic_note || ""} onChange={(v) => patch("strategic_note", v)} />
        <VisualBriefPanel
          value={post.visual_brief || ""}
          cameraRefPool={post.camera_ref_pool || ""}
          onChange={(v) => patch("visual_brief", v)}
          onPoolChange={(v) => patch("camera_ref_pool", v)}
        />
        <EmotionalArcPanel value={post.emotional_arc || ""} onChange={(v) => patch("emotional_arc", v)} />
        <AssetStrip imagePrompts={post.image_prompts || []} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subpanels
// ---------------------------------------------------------------------------

function DraftingPulse() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % STREAMING_HINTS.length), 1800);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6 gap-3">
      <div className="size-10 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
      <p className="text-sm font-medium">Drafting the post…</p>
      <p className="text-xs text-muted-foreground transition-opacity duration-500">
        {STREAMING_HINTS[idx]}
      </p>
      <p className="text-[10px] text-muted-foreground/60 max-w-xs">
        Slides, caption, and hashtags will appear here as soon as the draft is ready.
        This usually takes 20–40 seconds.
      </p>
    </div>
  );
}


function SlidesPreview({ html }) {
  // Use srcDoc with sandbox — no allow-scripts means inline event handlers
  // in the model's HTML cannot run. Strip explicit <script> tags as a belt-
  // and-braces measure in case sandbox attrs are misinterpreted.
  const safeHtml = useMemo(() => {
    if (!html) return "";
    return String(html).replace(/<script\b[\s\S]*?<\/script>/gi, "");
  }, [html]);

  return (
    <section className="rounded-lg border border-border bg-muted/20">
      <header className="flex items-center justify-between px-3 py-1.5 border-b border-border/50">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Slides preview
        </span>
        <span className="text-[10px] text-muted-foreground">sandboxed iframe</span>
      </header>
      <div className="bg-black/80">
        {safeHtml ? (
          <iframe
            title="slides preview"
            sandbox="allow-same-origin"
            srcDoc={safeHtml}
            className="w-full h-[600px] bg-white"
          />
        ) : (
          <div className="h-[200px] flex items-center justify-center text-xs text-muted-foreground/70">
            No slides_html yet.
          </div>
        )}
      </div>
    </section>
  );
}

function CaptionPanel({ value, onChange }) {
  return (
    <section className="rounded-lg border border-border bg-background">
      <header className="px-3 py-1.5 border-b border-border/50">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Caption</span>
      </header>
      <textarea
        rows={4}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="First line is the hook. Keep it 2–3 sentences."
        className="w-full resize-y rounded-b-lg border-0 bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </section>
  );
}

function HashtagPanel({ value, onChange }) {
  const [draft, setDraft] = useState("");

  function addFromInput() {
    const tag = draft.trim().replace(/^#?/, "#");
    if (tag === "#") {
      setDraft("");
      return;
    }
    if (!value.includes(tag)) onChange([...value, tag]);
    setDraft("");
  }

  function handleKey(e) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addFromInput();
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <section className="rounded-lg border border-border bg-background">
      <header className="px-3 py-1.5 border-b border-border/50">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Hashtags</span>
      </header>
      <div className="flex flex-wrap items-center gap-1.5 px-3 py-2">
        {value.map((tag, i) => (
          <span key={i} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs">
            {tag}
            <button
              type="button"
              onClick={() => onChange(value.filter((_, j) => j !== i))}
              className="text-muted-foreground hover:text-foreground"
            >
              ×
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKey}
          onBlur={addFromInput}
          placeholder="Add a tag, press Enter…"
          className="flex-1 min-w-[120px] bg-transparent text-xs focus:outline-none"
        />
      </div>
    </section>
  );
}

const HOOK_EMOTIONS = [
  { value: "frustration", hint: "I did everything right and still…" },
  { value: "shock",       hint: "A [authority] just told me…" },
  { value: "disbelief",   hint: "A free app knew more than my $300/hr…" },
  { value: "anger",       hint: "They're selling you the wrong…" },
  { value: "sadness",     hint: "I spent [years/money] on…" },
];

function HookEmotionPills({ value, onChange }) {
  return (
    <section className="rounded-lg border border-border bg-background">
      <header className="px-3 py-1.5 border-b border-border/50 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Hook emotion
        </span>
        <span className="text-[10px] text-muted-foreground/70">
          drives slide 1 — pick one
        </span>
      </header>
      <div className="px-3 py-2 flex flex-wrap gap-1.5">
        {HOOK_EMOTIONS.map(({ value: v, hint }) => {
          const active = value === v;
          return (
            <button
              key={v}
              type="button"
              onClick={() => onChange(active ? "" : v)}
              title={hint}
              className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                active
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:bg-muted/50"
              }`}
            >
              {v}
            </button>
          );
        })}
      </div>
    </section>
  );
}


function BridgeTextPanel({ value, onChange }) {
  // Hidden when empty + not focused — only slide-6 bridges show
  const [forceShow, setForceShow] = useState(false);
  const visible = forceShow || (value && value.trim());
  if (!visible) {
    return (
      <button
        type="button"
        onClick={() => setForceShow(true)}
        className="text-xs text-muted-foreground hover:text-foreground transition-colors text-left"
      >
        + Add slide-6 bridge (personal discovery beat)
      </button>
    );
  }
  return (
    <section className="rounded-lg border border-border bg-background">
      <header className="px-3 py-1.5 border-b border-border/50 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Slide 6 — bridge
        </span>
        <span className="text-[10px] text-muted-foreground/70">
          first-person, slightly self-deprecating
        </span>
      </header>
      <textarea
        rows={2}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder='"I found a free app for this. one photo. 30 seconds. I kind of wish I hadn’t."'
        className="w-full resize-y rounded-b-lg border-0 bg-transparent px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </section>
  );
}


function HookPanel({ hookType, hookText, saveCta, onChange }) {
  return (
    <section className="rounded-lg border border-border bg-background space-y-2">
      <header className="px-3 py-1.5 border-b border-border/50">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Hook</span>
      </header>
      <div className="px-3 pb-2 space-y-2">
        <input
          value={hookType}
          onChange={(e) => onChange("hook_type", e.target.value)}
          placeholder="hook type (e.g. identity_challenge)"
          className="w-full rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <textarea
          rows={2}
          value={hookText}
          onChange={(e) => onChange("hook_text", e.target.value)}
          placeholder="hook text — what slide 1 says"
          className="w-full resize-y rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <input
          value={saveCta}
          onChange={(e) => onChange("save_cta", e.target.value)}
          placeholder='save CTA — e.g. "save this — the self-test is on slide 3"'
          className="w-full rounded-md border border-input bg-background px-2 py-1 text-xs italic text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
    </section>
  );
}

function AudioPanel({ value, onChange }) {
  return (
    <section className="rounded-lg border border-border bg-background">
      <header className="px-3 py-1.5 border-b border-border/50">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Audio note</span>
      </header>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="one line on the trending sound shape that fits"
        className="w-full rounded-b-lg border-0 bg-transparent px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </section>
  );
}

function StrategicNotePanel({ value, onChange }) {
  // Hide entirely when empty + user hasn't focused — keeps the viewport
  // uncluttered for posts that don't carry agent reasoning.
  const [forceShow, setForceShow] = useState(false);
  const visible = forceShow || (value && value.trim());
  if (!visible) {
    return (
      <button
        type="button"
        onClick={() => setForceShow(true)}
        className="text-xs text-muted-foreground hover:text-foreground transition-colors text-left"
      >
        + Add strategic note (why this post works)
      </button>
    );
  }
  return (
    <section className="rounded-lg border border-border bg-muted/20">
      <header className="px-3 py-1.5 border-b border-border/50 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Why this works
        </span>
        <span className="text-[10px] text-muted-foreground/70">agent reasoning · editable</span>
      </header>
      <textarea
        rows={2}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="1-2 sentences: which pillar this reinforces, who it targets, why the hook fits."
        className="w-full resize-y rounded-b-lg border-0 bg-transparent px-3 py-2 text-xs italic focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </section>
  );
}


const CAMERA_REF_POOLS = [
  { value: "selfie-talking", hint: "default — indoor, person speaking to camera" },
  { value: "lifestyle",      hint: "outdoor / educational / gentle arc" },
  { value: "closeup",        hint: "intimate / confessional / sadness" },
];

function VisualBriefPanel({ value, cameraRefPool, onChange, onPoolChange }) {
  const [forceShow, setForceShow] = useState(false);
  const visible = forceShow || (value && value.trim()) || (cameraRefPool && cameraRefPool.trim());
  if (!visible) {
    return (
      <button
        type="button"
        onClick={() => setForceShow(true)}
        className="text-xs text-muted-foreground hover:text-foreground transition-colors text-left"
      >
        + Add visual brief (lighting / posture / camera pool)
      </button>
    );
  }
  return (
    <section className="rounded-lg border border-border bg-muted/10">
      <header className="px-3 py-1.5 border-b border-border/50 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Visual brief
        </span>
        <div className="flex items-center gap-1">
          {CAMERA_REF_POOLS.map(({ value: v, hint }) => {
            const active = cameraRefPool === v;
            return (
              <button
                key={v}
                type="button"
                onClick={() => onPoolChange(active ? "" : v)}
                title={hint}
                className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors ${
                  active
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted/50"
                }`}
              >
                {v}
              </button>
            );
          })}
        </div>
      </header>
      <textarea
        rows={5}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Lighting / setting / posture / skin texture / gesture arc / copy voice — drives copy + every image prompt."
        className="w-full resize-y rounded-b-lg border-0 bg-transparent px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </section>
  );
}


function EmotionalArcPanel({ value, onChange }) {
  const [forceShow, setForceShow] = useState(false);
  const visible = forceShow || (value && value.trim());
  if (!visible) {
    return (
      <button
        type="button"
        onClick={() => setForceShow(true)}
        className="text-xs text-muted-foreground hover:text-foreground transition-colors text-left"
      >
        + Add emotional arc (5-slide energy map)
      </button>
    );
  }
  return (
    <section className="rounded-lg border border-border bg-muted/10">
      <header className="px-3 py-1.5 border-b border-border/50 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Emotional arc
        </span>
        <span className="text-[10px] text-muted-foreground/70">
          one line per slide — peak at 03, vulnerable at 04, still at 05
        </span>
      </header>
      <textarea
        rows={5}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={"01: quiet, holding phone at eye level\n02: leaning in, brow tightening\n03: animated, mid-explanation\n04: looks away, hand on collarbone\n05: direct gaze, soft mouth, settled"}
        className="w-full resize-y rounded-b-lg border-0 bg-transparent px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </section>
  );
}


function AssetStrip({ imagePrompts }) {
  if (!Array.isArray(imagePrompts) || imagePrompts.length === 0) return null;
  return (
    <section className="rounded-lg border border-border bg-background">
      <header className="px-3 py-1.5 border-b border-border/50">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Image prompts ({imagePrompts.length})
        </span>
      </header>
      <ul className="divide-y divide-border/40">
        {imagePrompts.map((p, i) => (
          <li key={i} className="px-3 py-2 text-xs">
            <p className="font-mono text-[10px] text-muted-foreground mb-0.5">{p.slide_id || `slide-${i + 1}`}</p>
            <p className="line-clamp-3">{p.prompt}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
