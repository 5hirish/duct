"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Images, Link2, Loader2, PenLine, Sparkles, Video, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Platform, PLATFORM_LABELS, PostType } from "@/lib/contentEnums";
import { fmtCount } from "@/lib/contentMetrics";
import {
  appendPlanDay,
  createPost,
  listReferences,
  mediaUrl,
  tiktokOEmbed,
} from "@/lib/contentApi";

const MODES = [
  { key: "manual", label: "Manual", Icon: PenLine },
  { key: "url", label: "Paste URL", Icon: Link2 },
  { key: "reference", label: "References", Icon: Sparkles },
];

// A small, sensible default "Plan for": tomorrow at 18:00 local.
function defaultPlanFor() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(18, 0, 0, 0);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function slugify(s) {
  const base = String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  const rand = Math.random().toString(36).slice(2, 8);
  return `${base || "post"}-${rand}`;
}

const PLATFORM_CHOICES = [Platform.TIKTOK, Platform.INSTAGRAM, Platform.YOUTUBE];

/**
 * Add-post modal — the board's pinned CTA opens this. Three modes:
 *   - Manual: type the post; Save → pending post, Draft now → draft_post session.
 *   - Paste URL: free oEmbed peek (no scrape); Save stores a clone_source pointer,
 *     Draft now runs clone_post (scrape happens then, cached).
 *   - References: pick a saved discovery; same Save/Draft-now as URL.
 * Saving appends a plan day at the chosen "Plan for" time (source="manual").
 */
export default function AddPostModal({ projectId, plan, onClose, onSaved }) {
  const router = useRouter();
  const [mode, setMode] = useState("manual");
  const [planFor, setPlanFor] = useState(defaultPlanFor);
  const [busy, setBusy] = useState(""); // "" | "save" | "draft"
  const [error, setError] = useState("");

  // Manual fields
  const [topic, setTopic] = useState("");
  const [postType, setPostType] = useState(PostType.SLIDESHOW); // manual mode: slideshow | video
  const [hookText, setHookText] = useState("");
  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState([]);
  const [tagDraft, setTagDraft] = useState("");
  const [pillar, setPillar] = useState("");
  const [platforms, setPlatforms] = useState([Platform.TIKTOK]);

  // URL mode
  const [url, setUrl] = useState("");
  const [peek, setPeek] = useState(null);
  const [peeking, setPeeking] = useState(false);

  // Reference mode
  const [refs, setRefs] = useState(null); // null = not loaded
  const [refsErr, setRefsErr] = useState("");
  const [selectedRef, setSelectedRef] = useState(null);

  const planId = plan?.id || null;
  const pillars = useMemo(() => {
    const set = new Set();
    for (const d of plan?.days || []) if (d?.pillar) set.add(d.pillar);
    return [...set];
  }, [plan]);

  // Lazy-load saved references the first time the user opens that tab.
  useEffect(() => {
    if (mode !== "reference" || refs !== null || !projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const items = await listReferences(projectId);
        if (!cancelled) setRefs(Array.isArray(items) ? items : []);
      } catch (e) {
        if (!cancelled) { setRefs([]); setRefsErr(e.message || "Couldn't load references."); }
      }
    })();
    return () => { cancelled = true; };
  }, [mode, refs, projectId]);

  // Debounced free oEmbed peek when a TikTok URL is pasted (no Apify cost).
  useEffect(() => {
    setPeek(null);
    const u = url.trim();
    if (mode !== "url" || !/tiktok\.com/.test(u)) return;
    let cancelled = false;
    setPeeking(true);
    const t = setTimeout(async () => {
      const data = await tiktokOEmbed(u);
      if (!cancelled) { setPeek(data); setPeeking(false); }
    }, 500);
    return () => { cancelled = true; clearTimeout(t); setPeeking(false); };
  }, [url, mode]);

  function togglePlatform(p) {
    setPlatforms((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  }
  function addTag(raw) {
    const t = String(raw || "").trim().replace(/^#/, "");
    if (t && !hashtags.includes(t)) setHashtags((prev) => [...prev, t]);
    setTagDraft("");
  }
  function onTagKey(e) {
    if (e.key === "Enter" || e.key === "," || e.key === " ") { e.preventDefault(); addTag(tagDraft); }
    else if (e.key === "Backspace" && !tagDraft && hashtags.length) setHashtags((p) => p.slice(0, -1));
  }

  const scheduledIso = useMemo(() => {
    if (!planFor) return null;
    const d = new Date(planFor);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }, [planFor]);

  // What we know about the post at Save time, per mode.
  function derivePost() {
    if (mode === "manual") {
      return {
        topic: topic.trim() || "Untitled post",
        post_type: postType,
        clone_source: null,
      };
    }
    if (mode === "url") {
      return {
        topic: (peek?.title || "Cloned from TikTok").slice(0, 120),
        post_type: PostType.SLIDESHOW,
        clone_source: { kind: "url", url: url.trim(), ingested: false },
      };
    }
    // reference
    const r = selectedRef;
    return {
      topic: (r?.text || `Clone of @${r?.author || "reference"}`).slice(0, 120),
      post_type: r?.is_slideshow ? PostType.SLIDESHOW : PostType.VIDEO,
      clone_source: { kind: "reference", reference_asset_id: r?.asset_id, ingested: false },
    };
  }

  function validate() {
    if (mode === "manual" && !topic.trim()) return "Give the post a topic.";
    if (mode === "url" && !/tiktok\.com/.test(url.trim())) return "Paste a TikTok URL.";
    if (mode === "reference" && !selectedRef) return "Pick a reference.";
    return "";
  }

  // Create the pending post + append a plan day at the chosen slot.
  async function persist() {
    const d = derivePost();
    const slug = slugify(d.topic);
    const post = await createPost({
      project_id: projectId,
      plan_id: planId || undefined,
      post_dir_slug: slug,
      status: "pending",
      topic: d.topic,
      pillar: pillar || "",
      post_type: d.post_type,
      hook_text: mode === "manual" ? hookText : "",
      caption: mode === "manual" ? caption : "",
      hashtags: mode === "manual" ? hashtags.map((t) => `#${t}`) : [],
      platforms,
      ...(d.clone_source ? { clone_source: d.clone_source } : {}),
    });
    if (planId) {
      await appendPlanDay(planId, {
        post_id: post.id,
        scheduled_at: scheduledIso,
        source: "manual",
        status: "pending",
        topic: d.topic,
        pillar: pillar || "",
        post_type: d.post_type,
        platforms,
      });
    }
    return post;
  }

  async function onSave() {
    const v = validate();
    if (v) { setError(v); return; }
    setBusy("save"); setError("");
    try {
      await persist();
      onSaved?.();
    } catch (e) {
      setError(e.message || "Couldn't save the post.");
      setBusy("");
    }
  }

  async function onDraftNow() {
    const v = validate();
    if (v) { setError(v); return; }
    setBusy("draft"); setError("");
    try {
      const ch = platforms[0] || "tiktok";
      if (mode === "manual") {
        // No pre-created post — append a day stub and let the draft agent build it.
        let dayIndex = (plan?.days?.length ?? 0);
        if (planId) {
          const updated = await appendPlanDay(planId, {
            scheduled_at: scheduledIso,
            source: "manual",
            status: "pending",
            topic: topic.trim(),
            pillar: pillar || "",
            hook: hookText,
            post_type: postType,
            platforms,
          });
          dayIndex = Math.max(0, (updated?.days?.length ?? dayIndex + 1) - 1);
        }
        const params = new URLSearchParams();
        if (planId) { params.set("plan_id", planId); params.set("day", String(dayIndex)); }
        else { if (topic.trim()) params.set("topic", topic.trim()); if (pillar) params.set("pillar", pillar); }
        if (postType && postType !== PostType.SLIDESHOW) params.set("post_type", postType);
        params.set("channel", ch);
        router.push(`/content/posts/new?${params.toString()}`);
        return;
      }
      // URL / reference → create the pending clone post, then open clone_post.
      const post = await persist();
      const params = new URLSearchParams({ clone_post_id: post.id, channel: ch });
      if (planId) params.set("plan_id", planId);
      router.push(`/content/posts/new?${params.toString()}`);
    } catch (e) {
      setError(e.message || "Couldn't start drafting.");
      setBusy("");
    }
  }

  const working = Boolean(busy);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-in fade-in-0"
      onClick={(e) => { if (e.target === e.currentTarget && !working) onClose(); }}
    >
      <div className="flex max-h-[88vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl animate-in zoom-in-95 fade-in-0 duration-200">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-3.5">
          <h2 className="text-sm font-semibold">Add post</h2>
          <button
            type="button"
            onClick={() => !working && onClose()}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Mode tabs */}
        <div className="flex shrink-0 gap-1 border-b border-border/60 px-5 py-2.5">
          {MODES.map(({ key, label, Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => { setMode(key); setError(""); }}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                mode === key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <Icon className="size-3.5" />
              {label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {mode === "manual" && (
            <div className="space-y-4">
              <Field label="Topic">
                <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="What's the post about?" autoFocus />
              </Field>
              <Field label="Format">
                <div className="flex flex-wrap gap-1.5">
                  {[
                    { key: PostType.SLIDESHOW, label: "Slideshow", Icon: Images },
                    { key: PostType.VIDEO, label: "Video", Icon: Video },
                  ].map(({ key, label, Icon }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setPostType(key)}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${
                        postType === key ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground hover:border-primary/40"
                      }`}
                    >
                      <Icon className="size-3.5" /> {label}
                    </button>
                  ))}
                </div>
              </Field>
              {postType === PostType.VIDEO && (
                <p className="rounded-xl bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                  Video posts are generated with Higgsfield (image-to-video). Make sure Higgsfield is
                  connected for your workspace before drafting.
                </p>
              )}
              <Field label="Hook" hint={`${hookText.length}/120`}>
                <Input value={hookText} maxLength={120} onChange={(e) => setHookText(e.target.value)} placeholder="The scroll-stopping first line" />
              </Field>
              <Field label="Caption">
                <textarea
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  rows={3}
                  placeholder="Caption copy…"
                  className="w-full resize-none rounded-2xl border border-input bg-transparent px-3.5 py-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
                />
              </Field>
              <Field label="Hashtags">
                <div className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-input px-3 py-2">
                  {hashtags.map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                      #{t}
                      <button type="button" onClick={() => setHashtags((p) => p.filter((x) => x !== t))} className="text-primary/60 hover:text-primary">
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                  <input
                    value={tagDraft}
                    onChange={(e) => setTagDraft(e.target.value)}
                    onKeyDown={onTagKey}
                    onBlur={() => addTag(tagDraft)}
                    placeholder={hashtags.length ? "" : "Type a tag, press Enter"}
                    className="min-w-[8ch] flex-1 bg-transparent text-sm outline-none"
                  />
                </div>
              </Field>
              {pillars.length > 0 && (
                <Field label="Pillar">
                  <div className="flex flex-wrap gap-1.5">
                    {pillars.map((p) => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => setPillar((cur) => (cur === p ? "" : p))}
                        className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                          pillar === p ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground hover:border-primary/40"
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </Field>
              )}
            </div>
          )}

          {mode === "url" && (
            <div className="space-y-4">
              <Field label="TikTok URL" hint="We fetch the full post when you draft — no cost to paste.">
                <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.tiktok.com/@…/video/…" autoFocus />
              </Field>
              {peeking && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Loading preview…</p>
              )}
              {peek && (peek.thumbnail_url || peek.title) && (
                <div className="flex gap-3 rounded-xl border border-border/60 bg-muted/30 p-3">
                  {peek.thumbnail_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={peek.thumbnail_url} alt="" className="h-20 w-14 shrink-0 rounded-md object-cover" />
                  )}
                  <div className="min-w-0 text-xs">
                    {peek.author_name && <p className="font-medium text-foreground">@{peek.author_name}</p>}
                    <p className="mt-0.5 line-clamp-3 text-muted-foreground">{peek.title}</p>
                  </div>
                </div>
              )}
              <p className="text-xs text-muted-foreground">
                <strong className="font-medium text-foreground">Draft now</strong> visually analyses the post + its metrics and clones it for your brand.
              </p>
            </div>
          )}

          {mode === "reference" && (
            <div className="space-y-3">
              {refs === null && <p className="text-xs text-muted-foreground">Loading saved references…</p>}
              {refsErr && <p className="text-xs text-destructive">{refsErr}</p>}
              {refs && refs.length === 0 && !refsErr && (
                <p className="text-xs text-muted-foreground">No saved references yet — discover and save TikToks first, or paste a URL.</p>
              )}
              {refs && refs.length > 0 && (
                <div className="grid grid-cols-3 gap-2">
                  {refs.map((r) => (
                    <button
                      key={r.asset_id}
                      type="button"
                      onClick={() => setSelectedRef(r)}
                      className={`group relative overflow-hidden rounded-lg border text-left transition-all ${
                        selectedRef?.asset_id === r.asset_id ? "border-primary ring-2 ring-primary/30" : "border-border/60 hover:border-primary/40"
                      }`}
                    >
                      <div className="aspect-[3/4] w-full bg-muted/40">
                        {r.cover_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={mediaUrl(r.cover_url)} alt="" className="size-full object-cover" />
                        ) : (
                          <div className="flex size-full items-center justify-center text-[10px] text-muted-foreground/50">no cover</div>
                        )}
                      </div>
                      <div className="space-y-0.5 p-1.5">
                        <p className="truncate text-[10px] font-medium">@{r.author || "tiktok"}</p>
                        <p className="text-[10px] text-muted-foreground">{fmtCount(r.metrics?.views)} views</p>
                        {r.diagnostic?.lever && (
                          <p className="truncate text-[9px] font-medium uppercase tracking-wide text-primary">{r.diagnostic.lever}</p>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              {selectedRef?.diagnostic?.summary && (
                <p className="rounded-lg bg-primary/5 px-3 py-2 text-xs text-foreground">{selectedRef.diagnostic.summary}</p>
              )}
            </div>
          )}

          {/* Plan-for (all modes) */}
          <Field label="Plan for" hint="Where it lands on the board. Duplicate slots are fine.">
            <Input type="datetime-local" value={planFor} onChange={(e) => setPlanFor(e.target.value)} />
          </Field>

          {/* Platforms (all modes) */}
          <Field label="Platforms">
            <div className="flex flex-wrap gap-1.5">
              {PLATFORM_CHOICES.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => togglePlatform(p)}
                  className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                    platforms.includes(p) ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground hover:border-primary/40"
                  }`}
                >
                  {PLATFORM_LABELS[p]}
                </button>
              ))}
            </div>
          </Field>

          {error && <p className="text-xs text-destructive">{error}</p>}
          {!planId && (
            <p className="text-xs text-amber-600 dark:text-amber-400">No active plan — saving needs a plan. Create one in the planner first.</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border px-5 py-3">
          <Button variant="outline" onClick={onSave} disabled={working || !planId}>
            {busy === "save" ? <Loader2 className="size-4 animate-spin" /> : null}
            Save
          </Button>
          <Button onClick={onDraftNow} disabled={working}>
            {busy === "draft" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            Draft now
          </Button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-medium text-muted-foreground">{label}</Label>
        {hint && <span className="text-[10px] text-muted-foreground/70">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
