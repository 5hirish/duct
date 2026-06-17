"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Check,
  Copy,
  ExternalLink,
  Eye,
  Hash,
  Heart,
  Image as ImageIcon,
  Images,
  MessageCircle,
  RefreshCw,
  Send,
  Share2,
  Sparkles,
  Video,
  Wand2,
} from "lucide-react";
import { downloadPostSlides, patchPost, syncPostMetrics } from "../../lib/contentApi";
import { extractStyleHead } from "../../lib/slideDoc";
import { statusMeta } from "../../lib/contentStatus";
import { PostStatus } from "../../lib/contentEnums";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import { useRouter } from "next/navigation";
import SlidesCarousel from "./SlidesCarousel";
import PublishReviewPanel from "./PublishReviewPanel";
import PublishModal from "./PublishModal";
import { Phase } from "./contentPhase";

const STREAMING_HINTS = [
  "Picking the hook…",
  "Writing the caption…",
  "Choosing hashtags…",
  "Sketching image prompts…",
];

const TYPE_ICON = { slideshow: Images, video: Video, image: ImageIcon };

// The chat turn that kicks off the in-session pre-publish review (review_post
// sub-agent → submit_assessment → PUBLISH_ASSESSMENT). Emphatic that this is a
// READ-ONLY review — the agent has a habit of "helpfully" applying fixes, which
// must never happen on a review (the user decides what to change).
const REVIEW_TURN =
  "Run a pre-publish review of this draft — SCORE ONLY, do NOT change anything. " +
  "Dispatch the review (hook, narrative momentum, save-worthiness, shareability, " +
  "visual quality, CTA), then report the overall score and the top fixes. Do NOT " +
  "edit any slide, caption, hashtag, or image, and do NOT regenerate images — " +
  "I'll decide what to change after I see the score.";

// Build the "Improve with Duct" chat turn from the latest assessment: lead with
// the weakest markers' fixes, then any failed completeness checks.
function improveTurn(a) {
  const weak = [...(a.markers || [])]
    .sort((x, y) => (x.score ?? 0) - (y.score ?? 0))
    .slice(0, 3)
    .map((m, i) => `${i + 1}. ${m.label} (${m.score}/100): ${m.fix || m.verdict}`);
  const gaps = (a.sanity || [])
    .filter((c) => !c.passed)
    .map((c) => `- ${c.label}${c.detail ? `: ${c.detail}` : ""}`);
  let t = `Improve this draft before publishing. Prioritise the weakest markers:\n${weak.join("\n")}`;
  if (gaps.length) t += `\n\nAlso close these completeness gaps:\n${gaps.join("\n")}`;
  t += "\n\nApply these changes and then stop — don't re-run the review yet; I'll rerun it myself once you're done.";
  return t;
}

// A content fingerprint of everything the review judges (copy + images). Used to
// detect that the draft changed since the last review, so the panel can flag it.
function postSig(post) {
  const slides = Array.isArray(post?.slides) ? post.slides : [];
  return JSON.stringify({
    c: post?.caption || "",
    h: Array.isArray(post?.hashtags) ? post.hashtags : [],
    s: slides.map((s) => [
      s.headline || "", s.subtext || "", s.image_url || "",
      (Array.isArray(s.items) ? s.items : []).map((it) => [it.label || "", it.image_url || ""]),
    ]),
  });
}

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

// Quiet period after the last manual edit before auto-saving.
const AUTOSAVE_MS = 1000;

export default function PostViewport({ payload, assessment = null, phase, canPublish = false, onPublish, onRevise, onClone, onSendMessage }) {
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [reviewing, setReviewing] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [cloning, setCloning] = useState(false);
  const reviewedSigRef = useRef(null);
  const router = useRouter();

  // Stop the "Reviewing…" placeholder once a fresh assessment lands.
  useEffect(() => { if (assessment) setReviewing(false); }, [assessment?.generated_at]);
  // …and don't leave it stuck if the agent turn ends without one (error /
  // interruption / the agent never finalised the review).
  useEffect(() => {
    if (phase === Phase.READY || phase === Phase.FAILED) setReviewing(false);
  }, [phase]);

  // The last *incoming* payload object we've adopted into `draft`. A manual/auto
  // save (patchPost) doesn't flow back to the parent's `payload` prop, so this
  // guard stops the sync effect from re-running when `dirty` flips false after a
  // save and clobbering the freshly-saved draft with the now-stale prop. We only
  // re-sync when a genuinely new payload object arrives (an agent update).
  const lastSyncedPayload = useRef(null);

  useEffect(() => {
    if (!payload || payload.type !== "post") return;
    if (payload === lastSyncedPayload.current) return; // not a new agent update
    lastSyncedPayload.current = payload;
    if (!dirty) setDraft(payload);
  }, [payload, dirty]);

  const post = draft || payload;
  // CSS for the live preview comes from the backend-rendered slides_html (it
  // inlines the full style registry + layout CSS, all content-independent).
  const headHtml = useMemo(() => extractStyleHead(post?.slides_html || ""), [post?.slides_html]);

  // The review to show: the live in-session one wins; otherwise the persisted
  // last_assessment on the post (so it survives reload + shows on the detail
  // page). Guard that it belongs to THIS post.
  const effectiveAssessment = assessment || post?.last_assessment || null;
  const matchesPost = Boolean(effectiveAssessment && String(effectiveAssessment.post_id) === String(post?.id));
  // Staleness: snapshot the post's content fingerprint when a review lands, then
  // flag the panel if the slides/copy have changed since (agent OR manual edit).
  const currentSig = useMemo(() => postSig(post), [post]);
  useEffect(() => {
    if (matchesPost) reviewedSigRef.current = currentSig;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveAssessment?.generated_at]);
  const assessmentStale =
    matchesPost && reviewedSigRef.current != null && reviewedSigRef.current !== currentSig;

  function patch(field, value) {
    setDraft((prev) => ({ ...(prev || payload || {}), [field]: value }));
    setDirty(true);
    if (saveError) setSaveError(""); // editing again re-arms auto-save after a failure
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

  // Kick off the in-session pre-publish review. Persist pending edits first so
  // the review_post sub-agent scores the latest copy.
  async function handleReview() {
    if (!onSendMessage) return;
    await commitIfDirty();
    setReviewing(true);
    onSendMessage(REVIEW_TURN);
  }

  // Panel "Improve with Duct" → hand the prioritized fixes to the agent. It only
  // EDITS the draft (it doesn't re-review); once the edits land the draft reads
  // as stale and the panel's primary action flips to "Rerun review".
  async function handleImprove() {
    if (!onSendMessage || !effectiveAssessment) return;
    await commitIfDirty();
    onSendMessage(improveTurn(effectiveAssessment));
  }

  // Panel "Publish now" → the parent's publish flow when present (detail page),
  // otherwise our own PublishModal (the live drafting / revise session).
  function handlePanelPublish() {
    if (onPublish) onPublish();
    else setPublishOpen(true);
  }

  // Download the composed slides + caption as a .zip (available even once posted).
  async function handleDownloadSlides() {
    if (!post?.id) return;
    try {
      const slug = post.post_dir_slug || post.id;
      await downloadPostSlides(post.id, `${slug}-slides.zip`);
    } catch (err) {
      setSaveError(err.message || "Couldn't download the slides.");
    }
  }

  // Clone → a new draft variant (the parent does the create + routes to it).
  async function handleClone() {
    if (!onClone) return;
    setCloning(true);
    try { await onClone(); } catch (err) { setSaveError(err.message || "Couldn't clone the post."); }
    finally { setCloning(false); }
  }

  // Auto-save: debounce manual edits and persist them at the current status
  // (the agent's own edits already persist server-side). Pending posts are
  // excluded — keeping one is a deliberate promotion via the Save button. We
  // skip while a save is in flight (no double-save) and while one is erroring
  // (no hammering a failing endpoint); editing again clears the error and re-arms.
  useEffect(() => {
    if (!dirty || saving || saveError) return;
    if (!post?.id || post.status === PostStatus.PENDING) return;
    const t = setTimeout(() => { persist(post.status).catch(() => {}); }, AUTOSAVE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, saving, saveError, post?.id, post?.status, draft]);

  if (!post || (post.type && post.type !== "post" && !post.id)) {
    return <DraftingPulse />;
  }

  const slides = Array.isArray(post.slides) ? post.slides : [];
  const slideIdx = Math.min(currentIndex, Math.max(0, slides.length - 1));

  const status = post.status || "pending";
  const isPosted = status === PostStatus.POSTED;
  // Two-column on the full-width static view (no live chat): slides on the right,
  // details on the left. The live editor + mobile stay single-column.
  const twoCol = !onSendMessage && slides.length > 0;
  const meta = statusMeta(status);
  const TypeIcon = TYPE_ICON[post.post_type] || Images;
  const platforms = Array.isArray(post.platforms) ? post.platforms : [];
  const dateLabel = post.posted_at
    ? `Posted ${new Date(post.posted_at).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" })}`
    : post.scheduled_at
    ? `Scheduled ${new Date(post.scheduled_at).toLocaleDateString("en", { month: "short", day: "numeric" })}`
    : "Not scheduled";

  // Body blocks — composed into one or two columns below.
  const metricsEl = isPosted && post.post_bridge_post_id ? <PostMetrics post={post} /> : null;
  const reviewEl = (reviewing || matchesPost) ? (
    <PublishReviewPanel
      assessment={matchesPost ? effectiveAssessment : null}
      reviewing={reviewing}
      stale={assessmentStale}
      published={isPosted}
      onImprove={!isPosted && onSendMessage ? handleImprove : undefined}
      onRerun={!isPosted && onSendMessage ? handleReview : undefined}
      onPublish={!isPosted ? handlePanelPublish : undefined}
      onDownload={handleDownloadSlides}
    />
  ) : null;
  const carouselEl = (
    <SlidesCarousel slides={slides} headHtml={headHtml} index={slideIdx} onIndexChange={setCurrentIndex} />
  );

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
              <SaveIndicator saving={saving} dirty={dirty} hasError={Boolean(saveError)} onRetry={handleCommit} />
            )}
            {canPublish && onPublish && (
              <button type="button" onClick={onPublish} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted/50">
                <Send className="size-3.5" /> Publish
              </button>
            )}
            {onSendMessage && slides.length > 0 && (
              <button
                type="button"
                onClick={handleReview}
                disabled={reviewing}
                title="Run a pre-publish review, then publish"
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                <Send className="size-3.5" /> {reviewing ? "Reviewing…" : "Review & publish"}
              </button>
            )}
            {isPosted && onClone ? (
              <button
                type="button"
                onClick={handleClone}
                disabled={cloning}
                title="Create a new draft variant from this post"
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                <Copy className="size-3.5" /> {cloning ? "Cloning…" : "Clone"}
              </button>
            ) : onRevise ? (
              <button type="button" onClick={onRevise} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90">
                <Wand2 className="size-3.5" /> Revise with Duct
              </button>
            ) : null}
          </div>
        </div>
        {saveError && <p className="mt-2 text-xs text-destructive">{saveError}</p>}
      </header>

      {/* Body — the slides preview + the publishable copy (caption + hashtags).
          Slide layout, image prompts, hook and creative-brief edits all happen
          through the agent chat, so the pane stays focused on what ships. */}
      <div className="min-h-0 flex-1 overflow-auto">
        {twoCol ? (
          // Desktop full-width view: slides on the right, everything else on the
          // left. Collapses to a single column (slides first) on mobile.
          <div className="mx-auto grid max-w-5xl gap-5 p-5 md:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
            <div className="order-2 space-y-4 md:order-1">
              {metricsEl}
              {reviewEl}
              <PostCopy post={post} patch={patch} />
            </div>
            <div className="order-1 md:order-2 md:sticky md:top-5 md:self-start">
              {carouselEl}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-2xl space-y-4 p-5">
            {metricsEl}
            {carouselEl}
            <BulkImageBar slides={slides} onSendMessage={onSendMessage} commitIfDirty={commitIfDirty} currentIndex={slideIdx} />
            {reviewEl}
            <PostCopy post={post} patch={patch} />
          </div>
        )}
      </div>

      {/* Fallback publish flow for the live session (the detail page passes its
          own onPublish + PublishModal, so we only mount ours when it doesn't). */}
      {!onPublish && (
        <PublishModal
          open={publishOpen}
          onClose={() => setPublishOpen(false)}
          post={post}
          onPublished={(updated) => setDraft(updated)}    // update state; modal keeps the success screen up
          onViewPost={() => router.push(`/content/posts/${post.id}`)}  // → clean published view
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

function prettify(s) {
  return String(s || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Performance — PostBridge metrics for a published post
// ---------------------------------------------------------------------------

const METRIC_TILES = [
  { key: "view_count",    label: "Views",    icon: Eye },
  { key: "like_count",    label: "Likes",    icon: Heart },
  { key: "comment_count", label: "Comments", icon: MessageCircle },
  { key: "share_count",   label: "Shares",   icon: Share2 },
];

function fmtCount(n) {
  if (n == null) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(n % 1e6 === 0 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(n % 1e3 === 0 ? 0 : 1).replace(/\.0$/, "") + "K";
  return n.toLocaleString();
}

// share_url comes from PostBridge (external) — only allow http(s) so a
// javascript:/data: URL can't ride into an <a href> (XSS).
function safeHref(u) {
  if (typeof u !== "string" || !u) return null;
  try {
    const url = new URL(u, typeof window !== "undefined" ? window.location.origin : "https://getduct.ai");
    return /^https?:$/.test(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

function timeAgo(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

// Live PostBridge metrics for a published post. Shows stored perf immediately,
// auto-pulls once if we have nothing yet, and offers a manual refresh. The post
// is published (post_bridge_post_id present) before this renders.
function PostMetrics({ post }) {
  const [perf, setPerf] = useState(post.perf || {});
  const [syncing, setSyncing] = useState(false);
  const [note, setNote] = useState("");
  const fetchedRef = useRef(false);

  const hasAny = METRIC_TILES.some((t) => perf?.[t.key] != null);

  async function refresh() {
    setSyncing(true); setNote("");
    try {
      const updated = await syncPostMetrics(post.id);
      setPerf(updated?.perf || {});
    } catch (e) {
      const msg = e?.message || "";
      setNote(/publish|processing|finished/i.test(msg)
        ? "Metrics appear once the platform finishes processing the post."
        : "Couldn't refresh metrics — try again shortly.");
    } finally {
      setSyncing(false);
    }
  }

  // Best-effort first load when there's nothing stored yet.
  useEffect(() => {
    if (!fetchedRef.current && !hasAny) { fetchedRef.current = true; refresh(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const shareUrl = safeHref(perf?.share_url);

  return (
    <section className="space-y-3 rounded-2xl border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <BarChart3 className="size-4 text-primary" /> Performance
        </h3>
        <div className="flex items-center gap-2">
          {perf?.last_synced_at && (
            <span className="text-[11px] text-muted-foreground">Updated {timeAgo(perf.last_synced_at)}</span>
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={syncing}
            className="inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs font-medium hover:bg-muted/50 disabled:opacity-50"
          >
            <RefreshCw className={`size-3.5 ${syncing ? "animate-spin" : ""}`} /> {syncing ? "Syncing…" : "Refresh"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2">
        {METRIC_TILES.map(({ key, label, icon: Icon }) => (
          <div key={key} className="rounded-xl border border-border/60 bg-muted/30 px-3 py-2.5">
            <Icon className="size-4 text-muted-foreground" />
            <p className="mt-1.5 text-lg font-semibold leading-none tabular-nums">
              {syncing && !hasAny ? "…" : fmtCount(perf?.[key])}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>

      {note && <p className="text-[11px] text-muted-foreground">{note}</p>}
      {shareUrl && (
        <a
          href={shareUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          <ExternalLink className="size-3.5" /> View on platform
        </a>
      )}
    </section>
  );
}

// Passive save status for auto-saved (non-pending) posts. Renders as quiet text,
// not a button — edits persist on their own. The only actionable state is a
// failed save, which offers a Retry.
function SaveIndicator({ saving, dirty, hasError, onRetry }) {
  if (hasError) {
    return (
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/40 px-2.5 py-1.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10"
      >
        <RefreshCw className="size-3.5" /> Save failed · Retry
      </button>
    );
  }
  const inFlight = saving || dirty;
  return (
    <span
      aria-live="polite"
      className="inline-flex items-center gap-1.5 px-1.5 text-xs font-medium text-muted-foreground"
    >
      {inFlight ? (
        <><RefreshCw className="size-3.5 animate-spin" /> Saving…</>
      ) : (
        <><Check className="size-3.5 text-emerald-500" /> Saved</>
      )}
    </span>
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
      <div className="size-10 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
      <p className="text-sm font-medium">Drafting the post…</p>
      <p className="text-xs text-muted-foreground transition-opacity duration-500">{STREAMING_HINTS[idx]}</p>
      <p className="max-w-xs text-[10px] text-muted-foreground/60">
        Slides, caption, and hashtags appear here as soon as the draft is ready. Usually 20–40 seconds.
      </p>
    </div>
  );
}
