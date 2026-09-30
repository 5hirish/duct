"use client";

import { useEffect, useMemo, useState } from "react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
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
  publishPost,
} from "@/lib/contentApi";
import { PLATFORM_LABELS, Platform, PostType } from "@/lib/contentEnums";
import { friendlyErrorMessage } from "@/lib/agentSession";
import PublishReviewPanel from "./PublishReviewPanel";

/**
 * Publish flow:
 *   0. The pre-publish review, read fresh: the checks as the post stands and
 *      the agent's last score. Advice — nothing below waits on it.
 *   1. Pick one or more connected accounts
 *   2. (Optional) pick a schedule time
 *   3. Submit → backend uploads images to PostBridge + creates the post; a
 *      text post goes as words alone, and the dialog says which of its
 *      replies go with it (the channel's rule, from `post.channel`)
 *
 * Props:
 *   - open        : boolean
 *   - onClose     : () => void
 *   - post        : { id, project_id, topic, caption, platforms[], post_type, replies[], channel }
 *   - onPublished : (updatedPost) => void  — fired after successful publish
 */
export default function PublishModal({ open, onClose, post, onPublished }) {
  const { t } = useLingui();
  const [accounts, setAccounts]     = useState([]);
  const [selected, setSelected]     = useState(new Set());
  const [scheduledAt, setScheduledAt] = useState("");
  const [tiktokDraft, setTiktokDraft] = useState(false);
  const [loading, setLoading]       = useState(false);
  const [error,   setError]         = useState("");
  const [stage,   setStage]         = useState("");  // "" | "loading" | "publishing" | "done"
  const [assessment, setAssessment] = useState(null);
  const primary = Array.isArray(post?.platforms) ? post.platforms[0] : undefined;
  // A TikTok draft is TikTok's own feature; nowhere else has it.
  const offersTiktokDraft = primary === Platform.TIKTOK;

  // Group accounts by platform for the select grid
  const grouped = useMemo(() => {
    const out = {};
    for (const a of accounts) (out[a.platform] = out[a.platform] || []).push(a);
    return out;
  }, [accounts]);

  useEffect(() => {
    if (!open || !post?.project_id) return;
    setStage("loading"); setError("");
    let cancelled = false;
    (async () => {
      try {
        const [list, linked, fresh] = await Promise.all([
          listSocialAccounts(post.project_id),
          listLinkedAccounts(post.project_id).catch(() => []),
          // Re-read, not the page's copy: edits committed since the page
          // loaded change the checks. A failed read only loses the review.
          getPost(post.id).catch(() => null),
        ]);
        if (cancelled) return;
        setAccounts(list || []);
        setAssessment(fresh?.assessment || null);
        const availableIds = new Set((list || []).map(a => a.id));
        const linkedIds = (linked || [])
          .map(a => Number(a.account_id))
          .filter(id => availableIds.has(id));
        if (linkedIds.length > 0) {
          // Prefer the project's linked accounts.
          setSelected(new Set(linkedIds));
        } else if (primary) {
          // Fall back to the accounts on the post's own platform.
          const ids = (list || []).filter(a => a.platform === primary).map(a => a.id);
          setSelected(new Set(ids));
        }
      } catch (e) {
        if (!cancelled) setError(friendlyError(e));
      } finally {
        if (!cancelled) setStage("");
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

  async function handlePublish() {
    if (selected.size === 0) { setError(t`Pick at least one account.`); return; }
    setLoading(true); setError(""); setStage("publishing");
    try {
      const ids = [...selected].map(Number);
      const updated = await publishPost(post.id, {
        socialAccountIds: ids,
        scheduledAt: scheduledAt || null,
        tiktokDraft,
      });
      setStage("done");
      onPublished?.(updated);
      // Auto-close after a short success beat
      setTimeout(() => { onClose(); setStage(""); }, 1200);
    } catch (e) {
      setError(friendlyError(e));
      setStage("");
    } finally {
      setLoading(false);
    }
  }

  const hasAccounts = accounts.length > 0;
  const minDateTime = new Date(Date.now() + 5 * 60_000).toISOString().slice(0, 16);

  // A publish in flight must not be dismissable — hence the guards on
  // onOpenChange, outside-click and Escape rather than a bare onClose.
  const dismiss = (next) => {
    if (!next && !loading) onClose();
  };
  const blockWhileLoading = (event) => {
    if (loading) event.preventDefault();
  };

  return (
    <Dialog open={open} onOpenChange={dismiss}>
      <DialogContent
        className="max-w-lg gap-0 p-0"
        showCloseButton={!loading}
        onInteractOutside={blockWhileLoading}
        onEscapeKeyDown={blockWhileLoading}
      >
        <DialogHeader className="border-b border-border/60 px-5 py-3">
          <DialogTitle className="text-base font-semibold"><Trans>Publish post</Trans></DialogTitle>
          <DialogDescription className="truncate text-xs">
            {post?.topic || post?.id}
          </DialogDescription>
        </DialogHeader>

        <div className="px-5 py-4 space-y-4">
          {stage === "loading" && (
            <p className="text-sm text-muted-foreground"><Trans>Loading your connected accounts…</Trans></p>
          )}

          {stage === "done" && (
            <div className="text-sm text-success font-medium py-2">
              ✓ {scheduledAt ? <Trans>Post scheduled</Trans> : tiktokDraft ? <Trans>Saved as TikTok draft</Trans> : <Trans>Post published</Trans>}
            </div>
          )}

          {stage !== "loading" && stage !== "done" && (
            <>
              <PublishReviewPanel assessment={assessment} compact />

              <WhatPublishes post={post} />

              {!hasAccounts && (
                <div className="rounded-md border border-warning/40 bg-warning/5 p-3 text-xs">
                  <Trans>
                    You don't have any social accounts connected yet. Connect the
                    account you want to post from in the Accounts tab.
                  </Trans>
                </div>
              )}

              {hasAccounts && (
                <section className="space-y-2">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    <Trans>Where to post</Trans>
                  </h3>
                  <div className="space-y-2">
                    {Object.entries(grouped).map(([platform, list]) => (
                      <div key={platform}>
                        <p className="text-xs text-muted-foreground mb-1">
                          {PLATFORM_LABELS[platform] || platform}
                        </p>
                        <div className="grid grid-cols-1 gap-1.5">
                          {list.map(a => (
                            <label
                              key={a.id}
                              className="flex items-center gap-2 rounded border border-border bg-background hover:bg-muted/40 px-2 py-1.5 text-xs cursor-pointer"
                            >
                              <input
                                type="checkbox"
                                checked={selected.has(a.id)}
                                onChange={() => toggle(a.id)}
                                className="accent-primary"
                              />
                              <span className="font-medium">@{a.username}</span>
                              <span className="text-2xs text-muted-foreground ml-auto">
                                #{a.id}
                              </span>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="space-y-2">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  <Trans>When to post</Trans>
                </h3>
                <div className="space-y-1.5">
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="radio"
                      name="when"
                      checked={!scheduledAt && !tiktokDraft}
                      onChange={() => { setScheduledAt(""); setTiktokDraft(false); }}
                      className="accent-primary"
                    />
                    <span><Trans>Post now</Trans></span>
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="radio"
                      name="when"
                      checked={!!scheduledAt}
                      onChange={() => { setScheduledAt(minDateTime); setTiktokDraft(false); }}
                      className="accent-primary"
                    />
                    <span><Trans>Schedule for:</Trans></span>
                    <input
                      type="datetime-local"
                      value={scheduledAt}
                      min={minDateTime}
                      onChange={(e) => { setScheduledAt(e.target.value); setTiktokDraft(false); }}
                      onFocus={() => { if (!scheduledAt) setScheduledAt(minDateTime); }}
                      className="rounded border border-input bg-background px-2 py-0.5 text-xs"
                    />
                  </label>
                  {offersTiktokDraft && (
                    <label className="flex items-center gap-2 text-xs">
                      <input
                        type="radio"
                        name="when"
                        checked={tiktokDraft}
                        onChange={() => { setTiktokDraft(true); setScheduledAt(""); }}
                        className="accent-primary"
                      />
                      <span><Trans>Save as TikTok draft (post manually from the app)</Trans></span>
                    </label>
                  )}
                </div>
              </section>

              {error && (
                <div className="rounded-md border border-destructive/40 bg-destructive/8 p-3 text-xs text-destructive">
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        {stage !== "done" && (
          <footer className="px-5 py-3 border-t border-border/60 flex items-center justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={loading}><Trans>Cancel</Trans></Button>
            <Button
              onClick={handlePublish}
              disabled={loading || selected.size === 0 || stage === "loading"}
            >
              {loading
                ? <Trans>Working…</Trans>
                : scheduledAt
                ? <Trans>Schedule post</Trans>
                : tiktokDraft
                ? <Trans>Save as draft</Trans>
                : <Trans>Post now</Trans>}
            </Button>
          </footer>
        )}
      </DialogContent>
    </Dialog>
  );
}

// What a text post takes with it. PostBridge posts one reply on X (as the
// post's first reply) and none on LinkedIn; the rest are the author's to
// paste. Said before Publish, rather than learned from a refusal after it.
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
      <p className="rounded-md border border-border bg-muted/40 p-3 text-xs">
        <Trans>The post and its first reply go out together.</Trans>
      </p>
    );
  }
  return (
    <p className="rounded-md border border-warning/40 bg-warning/5 p-3 text-xs">
      {publishable > 0
        ? <><Trans>{label} publishes the post and its first reply.</Trans>{" "}<Plural value={extra} one="Post the other reply yourself once it's live: each part has a copy button." other="Post the other # replies yourself once it's live: each part has a copy button." /></>
        : <Trans>{label} doesn't publish comments. The post goes out alone; paste your first comment under it once it's live.</Trans>}
    </p>
  );
}

// A near-copy of `friendlyErrorMessage` used to live here — same four classes,
// slightly different wording, so the same failure read differently depending on
// which surface caught it. One translator now; publishing's own case
// (POSTBRIDGE) is already in its table.
function friendlyError(err) {
  return friendlyErrorMessage(err?.message || String(err || ""));
}
