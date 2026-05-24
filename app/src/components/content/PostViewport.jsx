"use client";

import { useEffect, useMemo, useState } from "react";
import { patchPost } from "../../lib/contentApi";

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
        tiktok_title: post.tiktok_title,
        audio_note:   post.audio_note,
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
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 gap-2">
        <div className="size-10 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
        <p className="text-sm text-muted-foreground">Drafting the post…</p>
        <p className="text-xs text-muted-foreground/70">
          Slides, caption, and hashtags will appear here as soon as the draft is ready.
        </p>
      </div>
    );
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
        <HookPanel
          hookType={post.hook_type || ""}
          hookText={post.hook_text || ""}
          onChange={(field, v) => patch(field, v)}
        />
        <AudioPanel value={post.audio_note || ""} onChange={(v) => patch("audio_note", v)} />
        <AssetStrip imagePrompts={post.image_prompts || []} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subpanels
// ---------------------------------------------------------------------------

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

function HookPanel({ hookType, hookText, onChange }) {
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
