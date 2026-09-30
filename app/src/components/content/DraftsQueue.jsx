"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CalendarClock, MessageSquareText, X } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";
import { dayLabel } from "@/components/content/ReflectionViewport";
import PublishModal from "@/components/content/PublishModal";
import { getBestSlot, getReflectionQueue, skipPost } from "@/lib/contentApi";

// The five reasons a proposed post gets a no. Each is a memory the next
// reflection reads (routes/content.py skip_post), so the chips are few and
// each one says something different about what to write next time.
export const SKIP_REASONS = [
  { id: "not_true", label: msg`Not true` },
  { id: "too_revealing", label: msg`Gives too much away` },
  { id: "not_interesting", label: msg`Not interesting` },
  { id: "already_said", label: msg`Already said` },
  { id: "wrong_voice", label: msg`Not my voice` },
];

/**
 * The drafts queue (issue #266): what the day's reflections proposed and
 * nobody has answered yet, newest day first. Approve opens the publish
 * dialog on the channel's next good slot; skip takes one reason and teaches
 * the next reflection. Renders nothing when there is nothing waiting, so the
 * journal below is the whole tab on a quiet day.
 *
 * `load`, `loadSlot` and `skip` are injectable so /preview can render it
 * without a backend.
 */
export default function DraftsQueue({
  projectId,
  load = getReflectionQueue,
  loadSlot = getBestSlot,
  skip = skipPost,
  onChange,
}) {
  const [days, setDays] = useState(null);

  useEffect(() => {
    let cancelled = false;
    load(projectId)
      .then((rows) => !cancelled && setDays(Array.isArray(rows) ? rows : []))
      .catch(() => !cancelled && setDays([]));
    return () => { cancelled = true; };
  }, [projectId, load]);

  function answered(postId) {
    setDays((prev) => (prev || [])
      .map((d) => ({ ...d, drafts: d.drafts.filter((p) => p.id !== postId) }))
      .filter((d) => d.drafts.length > 0));
    onChange?.();
  }

  if (!days || days.length === 0) return null;
  const waiting = days.reduce((n, d) => n + d.drafts.length, 0);

  return (
    <section className="space-y-4" aria-labelledby="drafts-queue-title">
      <h2 id="drafts-queue-title" className="text-sm font-semibold">
        <Plural value={waiting} one="# draft waiting for you" other="# drafts waiting for you" />
      </h2>
      {days.map((day) => (
        <QueueDay
          key={day.group_id}
          day={day}
          projectId={projectId}
          loadSlot={loadSlot}
          skip={skip}
          onAnswered={answered}
        />
      ))}
    </section>
  );
}

function QueueDay({ day, projectId, loadSlot, skip, onAnswered }) {
  const { i18n } = useLingui();
  return (
    <div className="space-y-2">
      <Link
        href={`/content/reflect?day=${encodeURIComponent(day.day)}`}
        className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted-foreground hover:text-foreground"
      >
        <span className="font-medium uppercase tracking-wide">{dayLabel(day.day, i18n.locale)}</span>
        <span className="truncate">{day.title}</span>
      </Link>
      <div className="grid grid-cols-1 gap-3 @2xl:grid-cols-2">
        {day.drafts.map((post) => (
          <QueueCard
            key={post.id}
            post={post}
            day={day.day}
            projectId={projectId}
            loadSlot={loadSlot}
            skip={skip}
            onAnswered={onAnswered}
          />
        ))}
      </div>
    </div>
  );
}

/** One proposed post: its words, when it would go out and why, and the three answers. */
export function QueueCard({ post, day, projectId, loadSlot = getBestSlot, skip = skipPost, onAnswered }) {
  const { t, i18n } = useLingui();
  const channel = post.platforms?.[0] || "";
  const [slot, setSlot] = useState(null);
  const [approving, setApproving] = useState(false);
  const [skipping, setSkipping] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    loadSlot(projectId, channel).then((s) => !cancelled && setSlot(s)).catch(() => {});
    return () => { cancelled = true; };
  }, [projectId, channel, loadSlot]);

  const when = slot?.at
    ? new Date(slot.at).toLocaleString(i18n.locale, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : "";
  const channelLabel = platformMeta(channel).label;
  const posts = slot?.posts || 0;
  const why = slot?.reason === "history"
    ? t`Your best hour on ${channelLabel}, from ${posts} posts with numbers.`
    : t`A good default for ${channelLabel} until five posts have numbers.`;

  async function answerSkip(reason) {
    setSkipping(true);
    setError("");
    try {
      await skip(post.id, reason);
      onAnswered?.(post.id);
    } catch (e) {
      setError(String(e?.message || e));
      setSkipping(false);
    }
  }

  return (
    <article className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <header className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <PlatformGlyph platform={channel} className="size-3.5" />
        {channelLabel}
      </header>

      <p className="line-clamp-6 whitespace-pre-line text-sm leading-relaxed">{post.caption}</p>

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

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="mt-auto flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => setApproving(true)}>
          <Trans>Approve</Trans>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href={`/content/reflect?day=${encodeURIComponent(day)}`}>
            <MessageSquareText className="size-3.5" /> <Trans>Edit in chat</Trans>
          </Link>
        </Button>
        <Popover>
          <PopoverTrigger asChild>
            <Button size="sm" variant="ghost" disabled={skipping} className="ml-auto text-muted-foreground">
              <X className="size-3.5" /> <Trans>Skip</Trans>
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-60 space-y-2 p-3">
            <p className="text-xs text-muted-foreground">
              <Trans>Why not? The next reflection learns from it.</Trans>
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SKIP_REASONS.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  disabled={skipping}
                  onClick={() => answerSkip(r.id)}
                  className="rounded-full border px-2.5 py-1 text-xs transition-colors hover:border-primary/50 hover:bg-muted disabled:opacity-50"
                >
                  {i18n._(r.label)}
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
        onPublished={() => onAnswered?.(post.id)}
      />
    </article>
  );
}
