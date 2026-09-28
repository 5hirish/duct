"use client";

import { useState } from "react";
import { Check, Copy, Plus, X } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";

/**
 * A text post — X or LinkedIn — edited where it will be read: a feed-shaped
 * card, the post on top and the author's own replies threaded under it.
 *
 * Every number comes from `post.channel` (the backend's channel rules, sent
 * with each post), so the counter here and the check that refuses an
 * over-length post count against the same limit:
 *   - max_chars            the platform's ceiling, per part
 *   - fold_chars           where the feed cuts to "see more" (0: it does not)
 *   - publishable_replies  how many replies go out with the post
 *
 * Props:
 *   - post  : { caption, replies[], platforms[], channel }
 *   - patch : (field, value) => void — the viewport's draft setter
 */
export default function TextPostEditor({ post, patch }) {
  const { t } = useLingui();
  const channel = post.channel || {};
  const platform = channel.id || (Array.isArray(post.platforms) && post.platforms[0]) || "";
  const label = channel.label || platformMeta(platform).label;
  const max = channel.max_chars || 0;
  const publishable = channel.publishable_replies ?? 0;
  const replies = Array.isArray(post.replies) ? post.replies : [];

  function setReply(i, value) {
    patch("replies", replies.map((r, j) => (j === i ? value : r)));
  }
  function removeReply(i) {
    patch("replies", replies.filter((_, j) => j !== i));
  }

  const addLabel = publishable > 0 ? t`Add a reply` : t`Add a first comment`;

  return (
    <section aria-label={t`${label} post`} className="space-y-3">
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <FeedPart
          platform={platform}
          title={t`Post`}
          value={post.caption || ""}
          max={max}
          threaded={replies.length > 0}
          onChange={(v) => patch("caption", v)}
          placeholder={t`The first line is the hook.`}
        >
          {channel.fold_chars > 0 && <FoldPreview text={post.caption || ""} fold={channel.fold_chars} label={label} />}
        </FeedPart>
        {replies.map((reply, i) => {
          const n = i + 1;
          const publishes = i < publishable;
          return (
            <FeedPart
              key={i}
              platform={platform}
              title={publishable > 0 ? t`Reply ${n}` : t`First comment`}
              value={reply}
              max={max}
              threaded={i < replies.length - 1}
              onChange={(v) => setReply(i, v)}
              onRemove={() => removeReply(i)}
              removeLabel={t`Remove reply ${n}`}
              placeholder={t`The source, the link, or the why.`}
              note={
                publishes
                  ? t`Publishes as the post's first reply.`
                  : publishable > 0
                  ? t`${label} only publishes the first reply. Post this one yourself.`
                  : t`${label} doesn't publish comments. Paste this under the post once it's live.`
              }
              quiet={publishes}
            />
          );
        })}
      </div>
      <Button type="button" variant="outline" size="sm" onClick={() => patch("replies", [...replies, ""])}>
        <Plus aria-hidden="true" /> {addLabel}
      </Button>
    </section>
  );
}

// ---------------------------------------------------------------------------
// One part of the post, as the feed draws it
// ---------------------------------------------------------------------------

function FeedPart({ platform, title, value, max, threaded, onChange, onRemove, removeLabel, placeholder, note, quiet, children }) {
  return (
    <div className="flex gap-3 px-4 pb-3 pt-4">
      <div className="flex flex-col items-center">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-foreground">
          <PlatformGlyph platform={platform} className="size-4" />
        </span>
        {/* The thread line: this part continues below. */}
        {threaded && <span aria-hidden="true" className="mt-1.5 w-0.5 flex-1 rounded-full bg-border" />}
      </div>
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold">{title}</span>
          <span className="ml-auto flex items-center gap-1">
            <Counter n={value.length} max={max} />
            <CopyButton text={value} />
            {onRemove && (
              <button
                type="button"
                onClick={onRemove}
                aria-label={removeLabel}
                className="flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            )}
          </span>
        </div>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={title}
          placeholder={placeholder}
          rows={rowsFor(value)}
          className="field-sizing-content min-h-[2lh] w-full resize-none rounded-md bg-transparent text-sm leading-relaxed outline-none placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/25"
        />
        {children}
        {note && <p className={`text-2xs ${quiet ? "text-muted-foreground" : "text-warning"}`}>{note}</p>}
      </div>
    </div>
  );
}

// Where `field-sizing: content` is supported the box grows with its text and
// this is ignored; elsewhere (older WebKit) it is the height: a line per
// newline, plus the lines a long paragraph wraps onto at the pane's width.
function rowsFor(text) {
  const wrapped = text.split("\n").reduce((n, line) => n + Math.max(1, Math.ceil(line.length / 64)), 0);
  return Math.max(2, wrapped);
}

// ---------------------------------------------------------------------------
// Counter — the platform's own limit, not a style target
// ---------------------------------------------------------------------------

function Counter({ n, max }) {
  const { t } = useLingui();
  if (!max) return null;
  const over = n > max;
  const near = !over && n > max * 0.9;
  const tone = over ? "font-semibold text-destructive" : near ? "text-warning" : "text-muted-foreground";
  const left = max - n;
  const extra = n - max;
  return (
    <span
      className={`text-2xs tabular-nums ${tone}`}
      title={over ? t`${extra} over the limit` : t`${left} left`}
    >
      {n.toLocaleString()} / {max.toLocaleString()}
    </span>
  );
}

// ---------------------------------------------------------------------------
// The fold — what a reader sees before "see more"
// ---------------------------------------------------------------------------

function FoldPreview({ text, fold, label }) {
  if (text.length <= fold) return null;
  const shown = text.slice(0, fold).trimEnd();
  const hidden = text.length - fold;
  return (
    <div className="rounded-lg border border-dashed border-border/80 bg-muted/40 px-3 py-2">
      <p className="mb-1 text-2xs font-medium text-muted-foreground">
        <Trans>What the {label} feed shows before “see more”</Trans>
      </p>
      <p className="whitespace-pre-line text-xs leading-relaxed">
        {shown}
        <span className="text-muted-foreground">… <Trans>see more</Trans></span>
      </p>
      <p className="mt-1 text-2xs text-muted-foreground">
        <Plural value={hidden} one="# character sits behind the fold." other="# characters sit behind the fold." />
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Copy — for the parts a platform won't publish, and for pasting by hand
// ---------------------------------------------------------------------------

function CopyButton({ text }) {
  const { t } = useLingui();
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard refused (permissions, insecure context): the text is still selectable */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      disabled={!text}
      aria-label={copied ? t`Copied` : t`Copy this part`}
      title={copied ? t`Copied` : t`Copy`}
      className="flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30 disabled:opacity-40"
    >
      {copied ? <Check className="size-3.5 text-success" aria-hidden="true" /> : <Copy className="size-3.5" aria-hidden="true" />}
    </button>
  );
}
