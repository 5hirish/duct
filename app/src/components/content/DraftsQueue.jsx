"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarClock, MessageSquareText, X } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";
import PublishModal from "@/components/content/PublishModal";
import { cdnImage, getBestSlot, mediaUrl, skipPost } from "@/lib/contentApi";
import { PostStatus, PostType, SKIP_REASON_LABELS, SkipReason, SlotReason } from "@/lib/contentEnums";

// Past this a caption is folded behind "Show all": a LinkedIn post runs to
// 3,000 characters, and a queue of them would be a wall nobody answers.
const FOLD_CHARS = 320;
const FOLD_LINES = 6;

/**
 * The drafts queue (issue #266): the project's drafts nobody has answered,
 * newest first, from any channel and from a plan day or a chat alike. Each
 * card says when it would go out and why; Approve opens the publish dialog on
 * that time, Skip takes one reason and teaches the content agent's next
 * draft. The caller owns the list and hears about each answer through
 * `onAnswered(postId, updatedPost)`, so the Posts tab's counts move with it.
 *
 * `loadSlot` and `skip` are injectable so /preview can render it without a
 * backend; `aside` sits at the end of the heading row (the reminder setting).
 */
export default function DraftsQueue({
  posts,
  projectId,
  loadSlot = getBestSlot,
  skip = skipPost,
  onAnswered,
  aside = null,
}) {
  const drafts = useMemo(
    () => [...(posts || [])].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))),
    [posts],
  );
  // One slot per channel, not per card: two drafts for X would otherwise ask
  // twice for the same answer. Re-asked when an approve takes that slot.
  const [slots, setSlots] = useState({});
  const channels = useMemo(
    () => [...new Set(drafts.map((p) => p.platforms?.[0]).filter(Boolean))].sort(),
    [drafts],
  );
  const channelKey = channels.join(",");

  const refreshSlot = useCallback((channel) => {
    loadSlot(projectId, channel)
      .then((slot) => setSlots((prev) => ({ ...prev, [channel]: slot })))
      // No suggestion is still a card: Approve opens on "Post now".
      .catch(() => {});
  }, [projectId, loadSlot]);

  useEffect(() => {
    channels.forEach(refreshSlot);
    // channelKey stands for `channels`, which is a new array every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelKey, refreshSlot]);

  function answered(post, updated) {
    onAnswered?.(post.id, updated);
    if (updated?.status === PostStatus.SCHEDULED) refreshSlot(post.platforms?.[0]);
  }

  return (
    <section className="space-y-4" aria-labelledby="drafts-queue-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="drafts-queue-title" className="text-sm font-semibold">
          {drafts.length > 0
            ? <Plural value={drafts.length} one="# draft waiting for you" other="# drafts waiting for you" />
            : <Trans>Nothing is waiting on you.</Trans>}
        </h2>
        {aside}
      </div>
      {drafts.length > 0 && (
        <div className="grid grid-cols-1 gap-3 @2xl:grid-cols-2 @6xl:grid-cols-3">
          {drafts.map((post) => (
            <QueueCard
              key={post.id}
              post={post}
              slot={slots[post.platforms?.[0]] || null}
              skip={skip}
              onAnswered={(updated) => answered(post, updated)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

/** One draft: its words (or its cover), when it would go out and why, and the three answers. */
export function QueueCard({ post, slot, skip = skipPost, onAnswered }) {
  const { t, i18n } = useLingui();
  const channel = post.platforms?.[0] || "";
  const [approving, setApproving] = useState(false);
  const [skipping, setSkipping] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");

  const channelLabel = platformMeta(channel).label;
  const caption = post.caption || "";
  const long = caption.length > FOLD_CHARS || caption.split("\n").length > FOLD_LINES;
  const thumb = post.post_type !== PostType.TEXT ? cdnImage(mediaUrl(post.thumbnail_url), { width: 160 }) : "";
  const when = slot?.at
    ? new Date(slot.at).toLocaleString(i18n.locale, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : "";
  const posts = slot?.posts || 0;
  const why = slot?.reason === SlotReason.HISTORY
    ? t`Your best hour on ${channelLabel}, from ${posts} posts with numbers.`
    : t`A good default for ${channelLabel} until five posts have numbers.`;

  async function answerSkip(reason) {
    setSkipping(true);
    setError("");
    try {
      onAnswered?.(await skip(post.id, reason));
    } catch (e) {
      setError(String(e?.message || e));
      setSkipping(false);
    }
  }

  return (
    <article className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <header className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
        <PlatformGlyph platform={channel} className="size-3.5 shrink-0" />
        <span className="shrink-0">{channelLabel}</span>
        {post.topic && (
          <>
            <span aria-hidden="true">·</span>
            <span className="truncate" title={post.topic}>{post.topic}</span>
          </>
        )}
      </header>

      <div className="flex min-w-0 gap-3">
        {thumb && (
          <img src={thumb} alt="" className="size-16 shrink-0 rounded-md border object-cover" loading="lazy" />
        )}
        <div className="min-w-0 flex-1">
          <p className={`whitespace-pre-line text-sm leading-relaxed ${long && !expanded ? "line-clamp-6" : ""}`}>
            {caption || <span className="text-muted-foreground"><Trans>No caption yet.</Trans></span>}
          </p>
          {long && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              className="mt-1 text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              {expanded ? <Trans>Show less</Trans> : <Trans>Show all</Trans>}
            </button>
          )}
        </div>
      </div>

      {when && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <CalendarClock className="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-medium text-foreground">{when}</span>
            {" · "}
            {why}
          </span>
        </p>
      )}

      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}

      <div className="mt-auto flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => setApproving(true)}>
          <Trans>Approve</Trans>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href={`/content/posts/${post.id}`}>
            <MessageSquareText className="size-3.5" aria-hidden="true" /> <Trans>Edit in chat</Trans>
          </Link>
        </Button>
        <Popover>
          <PopoverTrigger asChild>
            <Button size="sm" variant="ghost" disabled={skipping} className="ml-auto text-muted-foreground">
              <X className="size-3.5" aria-hidden="true" /> <Trans>Skip</Trans>
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64 space-y-2 p-3">
            <p className="text-xs text-muted-foreground">
              <Trans>Why not? The next draft learns from it.</Trans>
            </p>
            <div className="flex flex-wrap gap-1.5">
              {Object.values(SkipReason).map((reason) => (
                <button
                  key={reason}
                  type="button"
                  disabled={skipping}
                  onClick={() => answerSkip(reason)}
                  className="rounded-full border px-2.5 py-1 text-xs transition-colors hover:border-primary/50 hover:bg-muted disabled:opacity-50"
                >
                  {i18n._(SKIP_REASON_LABELS[reason])}
                </button>
              ))}
            </div>
          </PopoverContent>
        </Popover>
      </div>

      <PublishModal
        open={approving}
        onClose={() => setApproving(false)}
        post={post}
        suggestedAt={slot?.at}
        suggestion={slot ? why : ""}
        onPublished={(updated) => onAnswered?.(updated)}
      />
    </article>
  );
}
