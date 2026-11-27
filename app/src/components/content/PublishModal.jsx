"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { CircleCheck, ExternalLink, Send, TriangleAlert, Type } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  getPost,
  listLinkedAccounts,
  listSocialAccounts,
  localPickerValue,
  mediaUrl,
  publishPost,
} from "@/lib/contentApi";
import { PLATFORM_LABELS, Platform, PostType } from "@/lib/contentEnums";
import { errorText, friendlyErrorMessage } from "@/lib/agentSession";
import { formatDate, formatTime } from "@/lib/format";
import { PlatformGlyph } from "./platformGlyphs";
import PublishReviewPanel from "./PublishReviewPanel";

/**
 * Publish flow, in four states, each one drawn (2026-11-27: the accounts
 * loaded behind one grey line, nothing showed what was about to go out, and
 * a publish was a button reading "Working…" then a tick that closed itself
 * in a second):
 *   loading    — the shape of what is coming, as skeletons
 *   form       — what goes out (cover, caption, hashtags), the review's cut,
 *                where (accounts) and when
 *   publishing — what is being sent, and to whom, while the scheduler takes it
 *   done       — where it went and when, a link to it once live; the person
 *                closes it
 *
 * Props:
 *   - open, onClose
 *   - post        : { id, project_id, topic, caption, hashtags, slides, platforms[], post_type, replies[], channel }
 *   - onPublished : (updatedPost) => void
 *   - suggestedAt : ISO instant to open on as the schedule (the drafts queue's best slot)
 *   - suggestion  : a line saying why that time, shown while it is still the pick
 *   - api         : the four calls, for /preview; the real ones by default
 */
// Accounts are unique per scheduler, not overall: two schedulers can number
// theirs the same.
const accountKey = (a) => `${a.publisher || ""}:${a.id ?? a.account_id}`;

const Stage = Object.freeze({ LOADING: "loading", FORM: "form", PUBLISHING: "publishing", DONE: "done" });

const DEFAULT_API = { listSocialAccounts, listLinkedAccounts, getPost, publishPost };

export default function PublishModal({ open, onClose, post, onPublished, suggestedAt, suggestion, api = DEFAULT_API }) {
  const { t, i18n } = useLingui();
  const [accounts, setAccounts]     = useState([]);
  const [selected, setSelected]     = useState(new Set());
  const [scheduledAt, setScheduledAt] = useState("");
  const [tiktokDraft, setTiktokDraft] = useState(false);
  const [error,   setError]         = useState("");
  const [stage,   setStage]         = useState(Stage.LOADING);
  const [fresh, setFresh]           = useState(null);
  const [result, setResult]         = useState(null);
  const primary = Array.isArray(post?.platforms) ? post.platforms[0] : undefined;
  // A TikTok draft is TikTok's own feature; nowhere else has it.
  const offersTiktokDraft = primary === Platform.TIKTOK;
  const shown = fresh || post;
  const sending = stage === Stage.PUBLISHING;

  // Group accounts by platform for the select grid
  const grouped = useMemo(() => {
    const out = {};
    for (const a of accounts) (out[a.platform] = out[a.platform] || []).push(a);
    return out;
  }, [accounts]);

  // The picker's own format, in the reader's zone like minDateTime below: the
  // UTC slice this used to take showed a 9:00 Madrid slot as 07:00, and
  // absoluteTime then sent 07:00 Madrid.
  const suggestedValue = suggestedAt ? localPickerValue(suggestedAt) : "";

  useEffect(() => {
    if (!open || !post?.project_id) return;
    setStage(Stage.LOADING); setError(""); setResult(null);
    if (suggestedValue) { setScheduledAt(suggestedValue); setTiktokDraft(false); }
    let cancelled = false;
    (async () => {
      try {
        const [list, linked, again] = await Promise.all([
          api.listSocialAccounts(post.project_id),
          api.listLinkedAccounts(post.project_id).catch(() => []),
          // Re-read, not the page's copy: edits committed since the page
          // loaded change the checks and the cover. A failed read only loses
          // the review and falls back to the page's copy.
          api.getPost(post.id).catch(() => null),
        ]);
        if (cancelled) return;
        setAccounts(list || []);
        setFresh(again);
        const available = new Set((list || []).map(accountKey));
        // Prefer the project's linked account for the post's platform, else
        // the accounts on that platform at one scheduler: a post goes out
        // through one.
        const onPlatform = (list || []).filter(a => a.platform === primary);
        const linkedHere = (linked || [])
          .filter(a => a.platform === primary)
          .map(accountKey)
          .filter(k => available.has(k));
        const firstAt = onPlatform[0]?.publisher;
        setSelected(new Set(
          linkedHere.length > 0
            ? linkedHere
            : onPlatform.filter(a => a.publisher === firstAt).map(accountKey),
        ));
      } catch (e) {
        if (!cancelled) setError(friendlyError(e));
      } finally {
        if (!cancelled) setStage(Stage.FORM);
      }
    })();
    return () => { cancelled = true; };
  }, [open, post?.project_id, post?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  function toggle(id) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const chosen = accounts.filter(a => selected.has(accountKey(a)));

  async function handlePublish() {
    if (chosen.length === 0) { setError(t`Pick at least one account.`); return; }
    const publishers = [...new Set(chosen.map(a => a.publisher))];
    if (publishers.length > 1) { setError(t`Pick accounts at one scheduler at a time.`); return; }
    setError(""); setStage(Stage.PUBLISHING);
    try {
      const updated = await api.publishPost(post.id, {
        socialAccountIds: chosen.map(a => a.id),
        publisher: publishers[0],
        scheduledAt: scheduledAt || null,
        tiktokDraft,
      });
      setResult(updated || {});
      setStage(Stage.DONE);
      onPublished?.(updated);
    } catch (e) {
      setError(friendlyError(e));
      setStage(Stage.FORM);
    }
  }

  const hasAccounts = accounts.length > 0;
  const minDateTime = localPickerValue(new Date(Date.now() + 5 * 60_000));
  const when = scheduledAt ? new Date(scheduledAt) : null;
  const whenText = when
    ? t`${formatDate(when, { locale: i18n.locale, withYear: false })} at ${formatTime(when, { locale: i18n.locale })}`
    : "";

  // A publish in flight must not be dismissable — hence the guards on
  // onOpenChange, outside-click and Escape rather than a bare onClose.
  const dismiss = (next) => {
    if (!next && !sending) onClose();
  };
  const blockWhileSending = (event) => {
    if (sending) event.preventDefault();
  };

  return (
    <Dialog open={open} onOpenChange={dismiss}>
      <DialogContent
        className="max-h-[90dvh] max-w-lg gap-0 overflow-hidden p-0"
        showCloseButton={!sending}
        onInteractOutside={blockWhileSending}
        onEscapeKeyDown={blockWhileSending}
      >
        <DialogHeader className="border-b border-border/60 px-5 py-3">
          <DialogTitle className="text-base font-semibold"><Trans>Publish post</Trans></DialogTitle>
          <DialogDescription className="truncate text-xs">
            {post?.topic || post?.id}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 space-y-5 overflow-y-auto px-5 py-4">
          {stage === Stage.LOADING && <LoadingState />}

          {stage === Stage.PUBLISHING && (
            <SendingState post={shown} accounts={chosen} whenText={whenText} draft={tiktokDraft} />
          )}

          {stage === Stage.DONE && (
            <DoneState post={shown} accounts={chosen} whenText={whenText} draft={tiktokDraft} url={result?.published_url} />
          )}

          {stage === Stage.FORM && (
            <>
              <WhatGoesOut post={shown} />

              <PublishReviewPanel assessment={fresh?.assessment || null} compact />

              <WhatPublishes post={shown} />

              {!hasAccounts && (
                <Card variant="quiet" size="sm" className="flex-row items-start gap-2 text-sm">
                  <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
                  <Trans>
                    There's no account to post from yet. In the Accounts tab, connect a
                    scheduler and link the account you want to post from.
                  </Trans>
                </Card>
              )}

              {hasAccounts && (
                <section className="space-y-2">
                  <SectionTitle><Trans>Where to post</Trans></SectionTitle>
                  <div className="space-y-1.5">
                    {Object.entries(grouped).map(([platform, list]) => list.map(a => (
                      <AccountRow
                        key={accountKey(a)}
                        account={a}
                        platform={platform}
                        checked={selected.has(accountKey(a))}
                        onToggle={() => toggle(accountKey(a))}
                      />
                    )))}
                  </div>
                </section>
              )}

              <section className="space-y-2">
                <SectionTitle><Trans>When to post</Trans></SectionTitle>
                <div className="space-y-2 text-sm">
                  <label className="flex min-h-6 items-center gap-2">
                    <input
                      type="radio"
                      name="when"
                      checked={!scheduledAt && !tiktokDraft}
                      onChange={() => { setScheduledAt(""); setTiktokDraft(false); }}
                      className="accent-primary"
                    />
                    <span><Trans>Post now</Trans></span>
                  </label>
                  <label className="flex min-h-6 flex-wrap items-center gap-2">
                    <input
                      type="radio"
                      name="when"
                      checked={!!scheduledAt}
                      onChange={() => { setScheduledAt(minDateTime); setTiktokDraft(false); }}
                      className="accent-primary"
                    />
                    <span><Trans>Schedule for</Trans></span>
                    <input
                      type="datetime-local"
                      value={scheduledAt}
                      min={minDateTime}
                      aria-label={t`Date and time to post`}
                      onChange={(e) => { setScheduledAt(e.target.value); setTiktokDraft(false); }}
                      onFocus={() => { if (!scheduledAt) setScheduledAt(minDateTime); }}
                      className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    />
                  </label>
                  {suggestion && scheduledAt && scheduledAt === suggestedValue && (
                    <p className="pl-6 text-xs text-muted-foreground">{suggestion}</p>
                  )}
                  {offersTiktokDraft && (
                    <label className="flex min-h-6 items-center gap-2">
                      <input
                        type="radio"
                        name="when"
                        checked={tiktokDraft}
                        onChange={() => { setTiktokDraft(true); setScheduledAt(""); }}
                        className="accent-primary"
                      />
                      <span><Trans>Save as a TikTok draft, to post from the app yourself</Trans></span>
                    </label>
                  )}
                </div>
              </section>

              {error && (
                <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
                  <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                  <span>{errorText(i18n, error)}</span>
                </p>
              )}
            </>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border/60 px-5 py-3">
          {stage === Stage.DONE ? (
            <>
              {result?.published_url && (
                <Button variant="outline" asChild>
                  <a href={result.published_url} target="_blank" rel="noreferrer">
                    <ExternalLink aria-hidden="true" /> <Trans>View post</Trans>
                  </a>
                </Button>
              )}
              <Button onClick={onClose}><Trans>Done</Trans></Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={sending}><Trans>Cancel</Trans></Button>
              <Button
                onClick={handlePublish}
                disabled={sending || stage === Stage.LOADING || chosen.length === 0}
              >
                {sending ? <Spinner aria-hidden="true" /> : <Send aria-hidden="true" />}
                {sending
                  ? <Trans>Sending…</Trans>
                  : scheduledAt
                  ? <Trans>Schedule post</Trans>
                  : tiktokDraft
                  ? <Trans>Save as draft</Trans>
                  : <Trans>Post now</Trans>}
              </Button>
            </>
          )}
        </footer>
      </DialogContent>
    </Dialog>
  );
}

function SectionTitle({ children }) {
  return <h3 className="text-xs font-medium text-muted-foreground">{children}</h3>;
}

/** The shape of the form, while the accounts and the fresh post load. */
function LoadingState() {
  const { t } = useLingui();
  return (
    <div className="space-y-5" role="status" aria-label={t`Loading your accounts`}>
      <div className="flex gap-3">
        <Skeleton className="aspect-[9/16] w-16 shrink-0 rounded-lg" />
        <div className="min-w-0 flex-1 space-y-2 pt-1"><SkeletonText lines={3} /></div>
      </div>
      <div className="space-y-2">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-11 w-full rounded-lg" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-4 w-56" />
      </div>
    </div>
  );
}

function slideCount(post) {
  return Array.isArray(post?.slides) ? post.slides.length : 0;
}

/** The cover, or a glyph for a post with none (a text post, a cover not made). */
function Cover({ post, className = "w-16" }) {
  const src = mediaUrl(post?.thumbnail_url);
  const [broken, setBroken] = useState(false);
  return (
    <div className={`aspect-[9/16] shrink-0 overflow-hidden rounded-lg bg-muted ${className}`}>
      {src && !broken ? (
        <img src={src} alt="" className="size-full object-cover" onError={() => setBroken(true)} />
      ) : (
        <div className="flex size-full items-center justify-center text-muted-foreground">
          <Type aria-hidden="true" className="size-5" />
        </div>
      )}
    </div>
  );
}

/**
 * What the post sends: the cover, the caption as it will read, the hashtags
 * and the slide count. The caption is the thing people most want to see
 * before posting and the one thing this dialog never showed.
 */
function WhatGoesOut({ post }) {
  const [all, setAll] = useState(false);
  const [clipped, setClipped] = useState(false);
  const words_ = useRef(null);
  const isText = post?.post_type === PostType.TEXT;
  const words = post?.caption || "";
  const tags = (post?.hashtags || []).filter(Boolean);
  const slides = slideCount(post);
  // Offer the rest only when the fold actually cut something.
  useLayoutEffect(() => {
    const el = words_.current;
    if (el && !all) setClipped(el.scrollHeight > el.clientHeight + 1);
  }, [words, all]);
  return (
    <section className="space-y-2">
      <SectionTitle><Trans>What goes out</Trans></SectionTitle>
      <Card variant="quiet" size="sm" className="flex-row gap-3">
        {!isText && <Cover post={post} />}
        <div className="min-w-0 flex-1 space-y-1.5 text-sm">
          {words ? (
            // Folded, the paragraphs run together: a clamp that lands on a
            // blank line leaves an ellipsis alone on its own line.
            <p ref={words_} className={`break-words ${all ? "whitespace-pre-line" : "line-clamp-4"}`}>
              {all ? words : words.replace(/\s*\n\s*/g, " ")}
            </p>
          ) : (
            <p className="text-muted-foreground"><Trans>No caption.</Trans></p>
          )}
          {(clipped || all) && (
            <button type="button" onClick={() => setAll((v) => !v)} className="text-xs font-medium text-brand hover:underline">
              {all ? <Trans>Show less</Trans> : <Trans>Show the whole caption</Trans>}
            </button>
          )}
          {tags.length > 0 && (
            <p className="break-words text-xs text-muted-foreground">
              {tags.map((h) => (h.startsWith("#") ? h : `#${h}`)).join(" ")}
            </p>
          )}
          {slides > 0 && (
            <p className="text-xs text-muted-foreground">
              <Plural value={slides} one="# slide" other="# slides" />
            </p>
          )}
        </div>
      </Card>
    </section>
  );
}

function AccountRow({ account: a, platform, checked, onToggle }) {
  const id = `publish-account-${accountKey(a)}`;
  return (
    <label
      htmlFor={id}
      className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2 text-sm transition-colors hover:bg-muted/40 has-[[data-state=checked]]:border-primary/40 has-[[data-state=checked]]:bg-primary/5"
    >
      <Checkbox id={id} checked={checked} onCheckedChange={onToggle} />
      <PlatformGlyph platform={platform} className="size-4 shrink-0" title={PLATFORM_LABELS[platform] || platform} />
      <span className="min-w-0 flex-1 truncate">
        <span className="font-medium">@{a.username}</span>
        {a.display_name && <span className="text-muted-foreground"> · {a.display_name}</span>}
      </span>
      {a.needs_reconnect && (
        <span className="shrink-0 text-xs text-warning"><Trans>Reconnect it</Trans></span>
      )}
      {a.publisher_label && (
        <span className="shrink-0 text-xs text-muted-foreground"><Via scheduler={a.publisher_label} /></span>
      )}
    </label>
  );
}

function handles(accounts) {
  return accounts.map((a) => `@${a.username}`).join(", ");
}

/** While the scheduler takes the post: what is going where. */
function SendingState({ post, accounts, whenText, draft }) {
  const to = handles(accounts);
  const scheduler = accounts[0]?.publisher_label || "";
  const slides = slideCount(post);
  return (
    <div className="flex flex-col items-center gap-4 py-4 text-center" role="status">
      <div className="relative">
        <Cover post={post} className="w-20 opacity-60" />
        <span className="absolute inset-0 flex items-center justify-center">
          <Spinner className="size-6 text-foreground" />
        </span>
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium">
          {draft
            ? <Trans>Saving to {to}'s TikTok drafts…</Trans>
            : whenText
            ? <Trans>Scheduling for {to}…</Trans>
            : <Trans>Posting to {to}…</Trans>}
        </p>
        <p className="mx-auto max-w-[40ch] text-xs text-muted-foreground">
          {slides > 0
            ? <Plural value={slides} one="Sending # slide and the caption." other="Sending # slides and the caption." />
            : <Trans>Sending the post.</Trans>}{" "}
          {scheduler ? <Trans>{scheduler} can take a minute.</Trans> : <Trans>This can take a minute.</Trans>}
        </p>
      </div>
    </div>
  );
}

/** Where it went and when. The person closes it; it does not vanish. */
function DoneState({ post, accounts, whenText, draft, url }) {
  const to = handles(accounts);
  return (
    <div className="flex flex-col items-center gap-4 py-4 text-center" role="status">
      <div className="flex size-12 items-center justify-center rounded-full bg-success/15 text-success">
        <CircleCheck aria-hidden="true" className="size-6" />
      </div>
      <div className="space-y-1">
        <p className="text-base font-semibold">
          {draft
            ? <Trans>Saved to TikTok drafts</Trans>
            : whenText
            ? <Trans>Scheduled for {whenText}</Trans>
            : <Trans>Posted</Trans>}
        </p>
        <p className="mx-auto max-w-[40ch] text-sm text-muted-foreground">
          {draft
            ? <Trans>Open TikTok on {to} to post it yourself.</Trans>
            : whenText
            ? <Trans>It goes out on {to}. You can change or cancel it from the post until then.</Trans>
            : url
            ? <Trans>It's live on {to}.</Trans>
            : <Trans>It's on its way to {to}. The link appears on the post once the platform confirms it.</Trans>}
        </p>
      </div>
      <Card variant="quiet" size="sm" className="w-full flex-row items-center gap-3 text-left">
        <Cover post={post} className="w-10" />
        <p className="line-clamp-2 min-w-0 flex-1 text-sm">{post?.caption || post?.topic}</p>
      </Card>
    </div>
  );
}

// What a text post takes with it. The scheduler decides how many replies go
// out (PostBridge one on X, none on LinkedIn; Zernio a whole thread on X and
// a first comment on LinkedIn); the rest are the author's to paste. Said
// before Publish, rather than learned from a refusal after it.
function WhatPublishes({ post }) {
  const channel = post?.channel;
  if (post?.post_type !== PostType.TEXT || !channel) return null;
  const replies = (post.replies || []).filter((r) => r && r.trim());
  if (replies.length === 0) return null;
  const label = channel.label;
  const publishable = channel.publishable_replies || 0;
  const extra = replies.length - publishable;
  if (extra <= 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {replies.length > 1
          ? <Trans>The post and all its replies go out together.</Trans>
          : <Trans>The post and its first reply go out together.</Trans>}
      </p>
    );
  }
  return (
    <p className="flex items-start gap-2 text-sm">
      <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
      <span>
        {publishable > 0
          ? <><Trans>{label} publishes the post and its first reply.</Trans>{" "}<Plural value={extra} one="Post the other reply yourself once it's live: each part has a copy button." other="Post the other # replies yourself once it's live: each part has a copy button." /></>
          : <Trans>{label} doesn't publish comments. The post goes out alone; paste your first comment under it once it's live.</Trans>}
      </span>
    </p>
  );
}

function Via({ scheduler }) {
  return <Trans>via {scheduler}</Trans>;
}

// A near-copy of `friendlyErrorMessage` used to live here — same four classes,
// slightly different wording, so the same failure read differently depending on
// which surface caught it. One translator now; publishing's own case
// (POSTBRIDGE) is already in its table.
function friendlyError(err) {
  return friendlyErrorMessage(err?.message || String(err || ""));
}
