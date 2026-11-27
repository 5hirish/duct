"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  ClipboardCheck,
  History,
  Hash,
  Image as ImageIcon,
  Images,
  RefreshCw,
  Send,
  Sparkles,
  TriangleAlert,
  Type,
  Video,
  Wand2,
} from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { patchPost, restoreSlideVersion } from "../../lib/contentApi";
import { nextAfterApproval, pendingSlides, readyToPublish } from "../../lib/postReadiness";
import { extractStyleHead } from "../../lib/slideDoc";
import { statusMeta } from "../../lib/contentStatus";
import { POST_TYPE_LABELS, PostStatus, PostType, isTextChannel } from "../../lib/contentEnums";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import SlidesCarousel from "./SlidesCarousel";
import PostVideo from "./PostVideo";
import TextPostEditor from "./TextPostEditor";
import CloneSourceNote from "./CloneSourceNote";
import PublishReviewPanel from "./PublishReviewPanel";
import { isScored } from "@/lib/contentReview";
import { REVIEW_IDLE, START_WINDOW_MS, isReviewing, reviewAsked, reviewTick } from "@/lib/reviewRequest";
import { Button } from "@/components/ui/button";
import EmptyState from "@/components/ui/empty-state";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { titleCase } from "@/lib/format";
import { isComposing } from "@/lib/shortcuts";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";

// Message descriptors (module-level): rendered with `i18n._`.
const STREAMING_HINTS = [
  msg`Picking the hook…`,
  msg`Writing the caption…`,
  msg`Choosing hashtags…`,
  msg`Sketching image prompts…`,
];
const TEXT_STREAMING_HINTS = [
  msg`Reading what you've already said…`,
  msg`Picking the angle…`,
  msg`Finding a source…`,
  msg`Writing the hook…`,
];

const TYPE_ICON = { slideshow: Images, video: Video, image: ImageIcon, text: Type };

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
 *   - idle — the live session is waiting on the person (the slide strip
 *     offers "Looks good" only then)
 *   - children — rendered under the copy. The detail page puts a posted post's
 *     metrics form here: it owns the server copy of the post, which the agent's
 *     draft payloads (revise mode) do not carry perf for.
 *   - onSendMessage(text) — when present (active session), enables the
 *     "approve & generate images" action, which sends a chat turn to the agent.
 *     Absent on the read-only detail page.
 *   - channel — the channel a new draft is for, before its first payload
 *     arrives; picks the waiting copy. A text post (X, LinkedIn) swaps the
 *     slides and caption for TextPostEditor: same shell, same save.
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

export default function PostViewport({ payload, canPublish = false, onPublish, onRevise, onSendMessage, channel, idle = false, failed = false, children }) {
  const { t, i18n } = useLingui();
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [tab, setTab] = useState(ViewTab.POST);
  // A review the person asked for, until its score lands or the run stops
  // without one (lib/reviewRequest.js).
  const [review, setReview] = useState(REVIEW_IDLE);
  // How many versions back the slide in view is being shown (0 = as it is).
  const [peek, setPeek] = useState(0);
  const [restoring, setRestoring] = useState(false);
  // The slide the build last touched (an image landed, the agent rendered it).
  const [updatedId, setUpdatedId] = useState("");
  // When the person last moved the carousel themselves: the build does not
  // pull them off a slide they are reading.
  const lastNav = useRef(0);
  const navigate = (i) => { lastNav.current = Date.now(); setPeek(0); setCurrentIndex(i); };

  useEffect(() => {
    if (!payload || payload.type !== "post") return;
    if (!dirty) setDraft(payload);
  }, [payload, dirty]);

  // Follow the build: each frame is shown as it is made, so feedback can be
  // given on it while it is fresh. Never mid-read (8 s after a manual move).
  const focus = payload?._focus;
  useEffect(() => {
    if (!focus?.slide_id) return;
    const at = (payload?.slides || []).findIndex((s) => s?.slide_id === focus.slide_id);
    if (at < 0) return;
    setUpdatedId(focus.slide_id);
    if (Date.now() - lastNav.current > FOLLOW_AFTER_NAV_MS) setCurrentIndex(at);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one jump per focus event
  }, [focus?.at]);

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
  // `replies` and `title` are left out when the payload never had them, so a
  // save against a backend that predates them is not refused for an unknown
  // field (JSON drops an undefined key).
  function editedFields() {
    return {
      caption: post.caption, replies: post.replies, hashtags: post.hashtags,
      hook_type: post.hook_type, hook_text: post.hook_text, hook_emotion: post.hook_emotion,
      save_cta: post.save_cta, title: post.title, audio_note: post.audio_note,
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
      setSaveError(err.message || t`Your edits are still here, but they didn't save. Try again.`);
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

  // Absent on the read-only detail page: there is no session to ask. The
  // review lands on its own tab, which says it is under way until the new
  // score arrives (scored_at moves).
  const requestReview = onSendMessage
    ? async () => {
        await commitIfDirty();
        setReview(reviewAsked(post?.assessment?.scored_at, Date.now()));
        onSendMessage("Review this post before I publish it: score it and tell me what to fix. Don't change anything yet.");
      }
    : undefined;
  const askReview = requestReview
    ? () => { setTab(ViewTab.REVIEW); requestReview(); }
    : undefined;
  const reviewing = isReviewing(review);
  const scoredAt = post?.assessment?.scored_at;
  useEffect(() => {
    if (!review.askedAt) return undefined;
    const tick = () => setReview((r) => reviewTick(r, { idle, failed, scoredAt, now: Date.now() }));
    tick();
    // The one case no prop change reports: a request the agent never took up.
    const timer = review.started ? undefined : setTimeout(tick, START_WINDOW_MS);
    return () => clearTimeout(timer);
  }, [review.askedAt, review.started, idle, failed, scoredAt]);
  // A score that lands later (a queued request, a retry from the chat)
  // answers the notice that the last one stopped.
  useEffect(() => { setReview((r) => (r.stopped ? REVIEW_IDLE : r)); }, [scoredAt]);
  // One instruction from the review (a fix, an opening), then back to the
  // post, where the change will show.
  const fix = onSendMessage
    ? async (instruction) => {
        await commitIfDirty();
        setTab(ViewTab.POST);
        onSendMessage(instruction);
      }
    : undefined;

  // Put the slide in view back the way it was `back` versions ago. Pending
  // edits are saved first, so the restore never drops a caption typed here.
  async function restoreVersion(slideId, back) {
    if (!post?.id || restoring) return;
    setRestoring(true);
    setSaveError("");
    try {
      await commitIfDirty();
      const updated = await restoreSlideVersion(post.id, slideId, back);
      setDraft(updated);
      setDirty(false);
      setPeek(0);
    } catch (err) {
      setSaveError(err.message || t`That version didn't come back. Try again.`);
    } finally {
      setRestoring(false);
    }
  }

  // Publishing a post nobody kept yet keeps it first: the scheduler sends a
  // saved post, and Publish is the clearest way of saying "keep it".
  const publish = canPublish && onPublish
    ? async () => {
        try {
          const saved = post?.status === PostStatus.PENDING ? await handleSave() : (await commitIfDirty(), null);
          onPublish(saved || post);
        } catch { /* surfaced via saveError */ }
      }
    : undefined;

  if (!post || (post.type && post.type !== "post" && !post.id)) {
    return <DraftingPulse text={isTextChannel(channel)} />;
  }

  const slides = Array.isArray(post.slides) ? post.slides : [];
  const isText = post.post_type === PostType.TEXT;
  const slideIdx = Math.min(currentIndex, Math.max(0, slides.length - 1));
  const currentSlide = slides[slideIdx];
  // The slide in view's earlier states, oldest first; peeking shows one in
  // the carousel without changing anything until "Use this version".
  const versions = (currentSlide && post.slide_versions?.[currentSlide.slide_id]) || [];
  const back = Math.min(peek, versions.length);
  const shownSlides = back
    ? slides.map((s, i) => (i === slideIdx ? { ...versions[versions.length - back].slide, slide_id: s.slide_id } : s))
    : slides;

  const status = post.status || "pending";
  const meta = statusMeta(status);
  const TypeIcon = TYPE_ICON[post.post_type] || Images;
  const isVideo = post.post_type === PostType.VIDEO;
  const typeLabel = i18n._(POST_TYPE_LABELS[post.post_type] || POST_TYPE_LABELS[PostType.SLIDESHOW]);
  const platforms = Array.isArray(post.platforms) ? post.platforms : [];
  const slideCount = post.slide_count;
  const postedOn = post.posted_at
    ? new Date(post.posted_at).toLocaleDateString(i18n.locale, { month: "short", day: "numeric", year: "numeric" })
    : "";
  const scheduledOn = post.scheduled_at
    ? new Date(post.scheduled_at).toLocaleDateString(i18n.locale, { month: "short", day: "numeric" })
    : "";
  const dateLabel = post.posted_at
    ? t`Posted ${postedOn}`
    : post.scheduled_at
    ? t`Scheduled ${scheduledOn}`
    : t`Not scheduled`;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Unified header */}
      <header className="shrink-0 border-b border-border/60 px-5 py-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold leading-tight">
              {post.topic || post.post_dir_slug || t`Untitled post`}
            </h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium ${meta.accentClass}`}>
                <span className={`size-1.5 rounded-full ${meta.dotClass}`} /> {i18n._(meta.label)}
              </span>
              {post.pillar && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 font-medium text-brand">{titleCase(post.pillar)}</span>
              )}
              {post.format_name && (
                <span className="rounded-full border border-border/70 px-2 py-0.5">{post.format_name}</span>
              )}
              <span className="inline-flex items-center gap-1"><TypeIcon className="size-3" aria-hidden="true" /> {typeLabel}</span>
              {!isVideo && typeof slideCount === "number" && slideCount > 0 && <span>· <Plural value={slideCount} one="# slide" other="# slides" /></span>}
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
                <Trans>Discard</Trans>
              </button>
            )}
            {post?.status === PostStatus.PENDING ? (
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                title={t`Keep this post — adds it to your board`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {saving ? <Trans>Saving…</Trans> : <><Check className="size-3.5" /> <Trans>Save</Trans></>}
              </button>
            ) : (
              <button
                type="button"
                onClick={handleCommit}
                disabled={!dirty || saving}
                className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {saving ? <Trans>Saving…</Trans> : dirty ? <Trans>Commit edits</Trans> : <><Check className="size-3.5" /> <Trans>Saved</Trans></>}
              </button>
            )}
            {publish && (
              <button type="button" onClick={publish} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted/50">
                <Send className="size-3.5" /> <Trans>Publish</Trans>
              </button>
            )}
            {onRevise && (
              <button type="button" onClick={onRevise} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90">
                <Wand2 className="size-3.5" /> <Trans>Revise with Duct</Trans>
              </button>
            )}
          </div>
        </div>
        {saveError && <p className="mt-2 text-xs text-destructive">{saveError}</p>}
      </header>

      {/* Two views of one post: what ships, and what the review made of it.
          The review sat under the caption, a long scroll away from the post
          it judged, until 2026-11-27. */}
      <Tabs value={tab} onValueChange={setTab} className="shrink-0 gap-0 border-b border-border/60 px-5">
        <TabsList variant="line" className="h-10">
          <TabsTrigger value={ViewTab.POST}><Trans>Post</Trans></TabsTrigger>
          <TabsTrigger value={ViewTab.REVIEW}>
            <Trans>Review</Trans>
            {/* The score sits on the tab in a quiet pill: a red number on a
                tab read as an error, not as "this post needs work". The
                colour lives on the ring inside. */}
            {reviewing ? (
              <Spinner className="size-3 text-muted-foreground" />
            ) : isScored(post.assessment) ? (
              <span className="rounded-full bg-muted px-1.5 text-xs font-medium tabular-nums text-muted-foreground">
                {post.assessment.overall}
              </span>
            ) : null}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Body — what ships. A text post is its words, edited in a feed-shaped
          card; a visual post is the slides preview plus its caption and
          hashtags. Slide layout, image prompts, hook and creative-brief edits
          all happen through the agent chat, so the pane stays on what ships. */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-2xl space-y-4 p-5">
          {tab === ViewTab.REVIEW ? (
            <ReviewView
              assessment={post.assessment}
              reviewing={reviewing}
              stopped={Boolean(review.stopped)}
              onReview={requestReview}
              onFix={fix}
            />
          ) : isText ? (
            <TextPostEditor post={post} patch={patch} />
          ) : (
            <>
              {isVideo ? (
                <PostVideo
                  postId={post.id}
                  video={post.video}
                  takes={Array.isArray(post.video_takes) ? post.video_takes : []}
                  onChange={(updated) =>
                    setDraft((prev) => ({ ...(prev || payload), video: updated.video, video_takes: updated.video_takes }))
                  }
                />
              ) : (
                <>
                  <SlidesCarousel
                    slides={shownSlides}
                    headHtml={headHtml}
                    index={slideIdx}
                    onIndexChange={navigate}
                    note={<BuildNote slides={slides} index={slideIdx} updatedId={updatedId} onShow={navigate} />}
                  />

                  <SlideHistory
                    versions={versions}
                    peek={back}
                    onPeek={setPeek}
                    restoring={restoring}
                    onRestore={post.id ? () => restoreVersion(currentSlide.slide_id, back) : undefined}
                  />

                  {!back && (
                    <SlideFeedback
                      key={currentSlide?.slide_id || slideIdx}
                      slide={currentSlide}
                      n={slideIdx + 1}
                      next={nextAfterApproval(slides, slideIdx, idle)}
                      onSendMessage={onSendMessage}
                      commitIfDirty={commitIfDirty}
                    />
                  )}

                  <PostProgress
                    slides={slides}
                    onPublish={publish}
                    onReview={isScored(post.assessment) ? undefined : askReview}
                  />

                  <BulkImageBar slides={slides} onSendMessage={onSendMessage} commitIfDirty={commitIfDirty} currentIndex={slideIdx} />
                </>
              )}

              <CloneSourceNote source={post.clone_source} />

              <PostCopy post={post} patch={patch} />
            </>
          )}

          {tab === ViewTab.POST && children}
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
        {hint && <span className="text-2xs text-muted-foreground">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

// The ui Textarea with a value-first onChange, which is what this form's
// `patch(key, value)` calls want.
function CaptionField({ value, onChange, ...props }) {
  return <Textarea value={value} onChange={(e) => onChange(e.target.value)} {...props} />;
}

// ---------------------------------------------------------------------------
// Hashtags
// ---------------------------------------------------------------------------

function HashtagInput({ value, onChange }) {
  const { t } = useLingui();
  const [draft, setDraft] = useState("");
  function add() {
    const tag = draft.trim().replace(/^#?/, "#");
    if (tag === "#") { setDraft(""); return; }
    if (!value.includes(tag)) onChange([...value, tag]);
    setDraft("");
  }
  function onKey(e) {
    if (isComposing(e)) return;
    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
    else if (e.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-input bg-input/40 px-2.5 py-2">
      {value.map((tag, i) => (
        <span key={i} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-brand">
          {tag}
          <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))} className="text-brand/60 hover:text-brand">×</button>
        </span>
      ))}
      <span className="inline-flex min-w-[120px] flex-1 items-center gap-1 text-muted-foreground">
        <Hash className="size-3" />
        <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={add}
          aria-label={t`Add a hashtag`}
          placeholder={t`Add a tag, press Enter…`} className="flex-1 rounded-sm bg-transparent text-xs outline-none focus-visible:ring-3 focus-visible:ring-ring/30" />
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
  const { t } = useLingui();
  return (
    <section className="space-y-4 rounded-2xl border border-border bg-card p-4">
      <Labeled label={t`Caption`} hint={t`first line is the hook — 2–3 sentences`}>
        <CaptionField rows={4} value={post.caption || ""} onChange={(v) => patch("caption", v)} placeholder={t`First line is the hook. Keep it 2–3 sentences.`} />
      </Labeled>
      <Labeled label={t`Hashtags`}>
        <HashtagInput value={Array.isArray(post.hashtags) ? post.hashtags : []} onChange={(v) => patch("hashtags", v)} />
      </Labeled>
    </section>
  );
}

// ---------------------------------------------------------------------------
// The Review tab
// ---------------------------------------------------------------------------

const ViewTab = Object.freeze({ POST: "post", REVIEW: "review" });
// The spinner takes the icon's place in the empty state's tile, so the
// copy under it stays centred (inline beside wrapped text it sat off to the
// left of the paragraph).
function ReviewingIcon({ className }) {
  return <Spinner className={className} />;
}

/** The review, or the way to get one: under way, not yet asked, or here. */
function ReviewView({ assessment, reviewing, stopped, onReview, onFix }) {
  const body = <ReviewBody assessment={assessment} reviewing={reviewing} onReview={onReview} onFix={onFix} />;
  if (!stopped || reviewing) return body;
  // The run ended (or never began) without a new score: say so above what
  // the post already had, with the one way forward.
  return (
    <div className="space-y-3">
      <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <TriangleAlert aria-hidden="true" className="size-4 shrink-0 text-warning" />
        <span className="min-w-0 flex-1 text-muted-foreground">
          <Trans>The review stopped before it finished, so nothing new was scored.</Trans>
        </span>
        {/* An unscored post's own empty state already offers the review. */}
        {onReview && isScored(assessment) && (
          <Button size="sm" variant="outline" onClick={onReview}>
            <RefreshCw aria-hidden="true" /> <Trans>Try again</Trans>
          </Button>
        )}
      </div>
      {body}
    </div>
  );
}

function ReviewBody({ assessment, reviewing, onReview, onFix }) {
  if (reviewing) {
    return (
      <EmptyState icon={ReviewingIcon} title={<Trans>Reviewing this post…</Trans>}>
        <Trans>Scoring the opening and the flow, and reading it as each of your personas. Usually a minute.</Trans>
      </EmptyState>
    );
  }
  if (!isScored(assessment)) {
    return (
      <EmptyState
        icon={ClipboardCheck}
        title={<Trans>Not reviewed yet</Trans>}
        actions={onReview && (
          <Button size="sm" onClick={onReview}>
            <ClipboardCheck aria-hidden="true" /> <Trans>Review this post</Trans>
          </Button>
        )}
      >
        {onReview
          ? <Trans>Duct scores the opening, the flow and what people would do with it, and your personas say whether they would stop.</Trans>
          : <Trans>Revise with Duct and ask for a review to get one.</Trans>}
      </EmptyState>
    );
  }
  return <PublishReviewPanel assessment={assessment} onReview={onReview} onFix={onFix} />;
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
          <Sparkles className="size-3.5" /> <Plural value={pending} one="Approve & generate # image — one by one" other="Approve & generate # images — one by one" />
        </button>
      )}
      {curStale && (
        <button
          type="button"
          onClick={() => ask(`Regenerate just the image for ${cur.slide_id} — the slide I'm viewing — to match its updated prompt. Leave every other slide exactly as it is.`)}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-warning/50 bg-warning/10 px-3 py-2 text-xs font-semibold text-warning transition-colors hover:bg-warning/20"
        >
          <RefreshCw className="size-3.5" /> <Trans>This slide is outdated — regenerate</Trans>
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Following the build
// ---------------------------------------------------------------------------

const FOLLOW_AFTER_NAV_MS = 8000;

/** In the carousel header: this slide just changed, or another one did. */
function BuildNote({ slides, index, updatedId, onShow }) {
  if (!updatedId) return null;
  const at = slides.findIndex((s) => s?.slide_id === updatedId);
  if (at < 0) return null;
  if (at === index) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-semibold text-brand">
        <Sparkles className="size-3" aria-hidden="true" /> <Trans>Just updated</Trans>
      </span>
    );
  }
  const n = at + 1;
  return (
    <button
      type="button"
      onClick={() => onShow(at)}
      className="inline-flex min-h-6 items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-semibold text-brand hover:bg-primary/15"
    >
      <Trans>Slide {n} updated · View</Trans>
    </button>
  );
}

/**
 * Feedback on the slide in view, under it: the words go to the agent with
 * the slide named, so nobody types "slide 3" or scrolls the chat to say it.
 * "Looks good" appears only while the agent is waiting on this slide before
 * making the next one (`next`, its index, or -1): offered at any other moment
 * it sent the agent looking for a slide that was not there.
 */
function SlideFeedback({ slide, n, next = -1, onSendMessage, commitIfDirty }) {
  const { t } = useLingui();
  const [text, setText] = useState("");
  if (!onSendMessage || !slide) return null;
  const id = slide.slide_id || `slide-${String(n).padStart(2, "0")}`;
  const nextN = next + 1;
  async function send(message) {
    await commitIfDirty?.();
    onSendMessage(message);
  }
  function submit(e) {
    e.preventDefault();
    const words = text.trim();
    if (!words) return;
    setText("");
    send(`Feedback on slide ${n} (${id}): ${words}`);
  }
  return (
    <form onSubmit={submit} className="flex items-center gap-2">
      <label className="sr-only" htmlFor={`slide-feedback-${id}`}><Trans>Ask for a change to slide {n}</Trans></label>
      <input
        id={`slide-feedback-${id}`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t`Ask for a change to slide ${n}`}
        className="h-9 min-w-0 flex-1 rounded-lg border border-control bg-input/50 px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
      />
      {text.trim() ? (
        <button type="submit" className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-semibold text-primary-foreground hover:opacity-90">
          <Send className="size-3.5" aria-hidden="true" /> <Trans>Send</Trans>
        </button>
      ) : next >= 0 ? (
        <button
          type="button"
          onClick={() => send(`Slide ${n} (${id}) looks good. Go on with slide ${nextN}.`)}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium hover:bg-muted/50"
        >
          <Check className="size-3.5" aria-hidden="true" /> <Trans>Looks good, make slide {nextN}</Trans>
        </button>
      ) : null}
    </form>
  );
}

/**
 * The slide in view's earlier versions: step back through them in the
 * carousel, then keep one. Nothing changes until "Use this version", and the
 * version it replaces is kept, so that is undone the same way.
 */
function SlideHistory({ versions, peek, onPeek, restoring, onRestore }) {
  const { t } = useLingui();
  if (!versions.length) return null;
  const total = versions.length + 1;
  const showing = total - peek;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <History className="size-3.5 text-muted-foreground" aria-hidden="true" />
      <span className="tabular-nums text-muted-foreground">
        {peek ? <Trans>Version {showing} of {total}</Trans> : <Trans>Latest of {total} versions</Trans>}
      </span>
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => onPeek(peek + 1)}
          disabled={peek >= versions.length || restoring}
          aria-label={t`Earlier version`}
          className="inline-flex size-8 items-center justify-center rounded-md hover:bg-muted/50 disabled:opacity-40"
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => onPeek(peek - 1)}
          disabled={peek === 0 || restoring}
          aria-label={t`Later version`}
          className="inline-flex size-8 items-center justify-center rounded-md hover:bg-muted/50 disabled:opacity-40"
        >
          <ChevronRight className="size-4" aria-hidden="true" />
        </button>
      </div>
      {peek > 0 && (
        <div className="ml-auto flex items-center gap-2">
          <button type="button" onClick={() => onPeek(0)} disabled={restoring} className="h-8 rounded-md px-2 text-muted-foreground hover:text-foreground">
            <Trans>Back to latest</Trans>
          </button>
          {onRestore && (
            <button
              type="button"
              onClick={onRestore}
              disabled={restoring}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary px-3 font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-60"
            >
              {restoring ? <Spinner className="size-3.5" /> : <Check className="size-3.5" aria-hidden="true" />}
              <Trans>Use this version</Trans>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Where the post stands: how many slides still need a picture, or that every
 * one is ready, with the review and Publish beside it. A post with all its
 * pictures used to show nothing at all, so nobody could tell it was done.
 * The review is offered until the post has one; its panel then sits below.
 */
function PostProgress({ slides, onPublish, onReview }) {
  if (!slides.length) return null;
  const pending = pendingSlides(slides);
  if (!readyToPublish(slides)) {
    const ready = slides.length - pending.length;
    const total = slides.length;
    const nextN = pending[0] + 1;
    return (
      <p className="text-xs tabular-nums text-muted-foreground">
        <Trans>{ready} of {total} slides ready · slide {nextN} needs a picture</Trans>
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2">
      <CircleCheck className="size-4 shrink-0 text-success" aria-hidden="true" />
      <p className="min-w-0 flex-1 basis-48 text-sm">
        <Plural value={slides.length} one="The slide is ready to publish." other="All # slides are ready to publish." />
      </p>
      {onReview && (
        <button
          type="button"
          onClick={onReview}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium hover:bg-muted/50"
        >
          <ClipboardCheck className="size-3.5" aria-hidden="true" /> <Trans>Review first</Trans>
        </button>
      )}
      {onPublish && (
        <button
          type="button"
          onClick={onPublish}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-semibold text-primary-foreground hover:opacity-90"
        >
          <Send className="size-3.5" aria-hidden="true" /> <Trans>Publish</Trans>
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drafting state
// ---------------------------------------------------------------------------

function DraftingPulse({ text = false }) {
  const { i18n } = useLingui();
  const [idx, setIdx] = useState(0);
  const hints = text ? TEXT_STREAMING_HINTS : STREAMING_HINTS;
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % hints.length), 1800);
    return () => clearInterval(t);
  }, [hints.length]);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
      <Spinner className="size-10 border-primary/30 border-t-primary" />
      <p className="text-sm font-medium"><Trans>Drafting the post…</Trans></p>
      <p className="text-xs text-muted-foreground transition-opacity duration-500">{i18n._(hints[idx % hints.length])}</p>
      <p className="max-w-xs text-2xs text-muted-foreground">
        {text
          ? <Trans>The post appears here as soon as the draft is ready, with its character count.</Trans>
          : <Trans>Slides, caption, and hashtags appear here as soon as the draft is ready. Usually 20–40 seconds.</Trans>}
      </p>
    </div>
  );
}
