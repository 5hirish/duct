"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  listSocialAccounts,
  publishPost,
} from "@/lib/contentApi";
import { PLATFORM_LABELS } from "@/lib/contentEnums";

/**
 * Publish flow:
 *   1. Pick one or more connected accounts
 *   2. (Optional) pick a schedule time
 *   3. Submit → backend uploads images to PostBridge + creates the post
 *
 * Props:
 *   - open        : boolean
 *   - onClose     : () => void
 *   - post        : { id, project_id, topic, caption, platforms[] }
 *   - onPublished : (updatedPost) => void  — fired after successful publish
 */
export default function PublishModal({ open, onClose, post, onPublished }) {
  const [accounts, setAccounts]     = useState([]);
  const [selected, setSelected]     = useState(new Set());
  const [scheduledAt, setScheduledAt] = useState("");
  const [tiktokDraft, setTiktokDraft] = useState(false);
  const [loading, setLoading]       = useState(false);
  const [error,   setError]         = useState("");
  const [stage,   setStage]         = useState("");  // "" | "loading" | "publishing" | "done"

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
        const list = await listSocialAccounts(post.project_id);
        if (cancelled) return;
        setAccounts(list || []);
        // Pre-select TikTok accounts if the post targets TikTok by default.
        if (Array.isArray(post.platforms) && post.platforms.includes("tiktok")) {
          const ttIds = (list || []).filter(a => a.platform === "tiktok").map(a => a.id);
          setSelected(new Set(ttIds));
        }
      } catch (e) {
        if (!cancelled) setError(friendlyError(e));
      } finally {
        if (!cancelled) setStage("");
      }
    })();
    return () => { cancelled = true; };
  }, [open, post?.project_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  function toggle(id) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function handlePublish() {
    if (selected.size === 0) { setError("Pick at least one account."); return; }
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget && !loading) onClose(); }}
    >
      <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-xl bg-background border border-border shadow-xl">
        <header className="px-5 py-3 border-b border-border/60 flex items-center justify-between">
          <div className="min-w-0">
            <h2 className="text-base font-semibold">Publish post</h2>
            <p className="text-xs text-muted-foreground truncate">{post?.topic || post?.id}</p>
          </div>
          {!loading && (
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-xl">
              ×
            </button>
          )}
        </header>

        <div className="px-5 py-4 space-y-4">
          {stage === "loading" && (
            <p className="text-sm text-muted-foreground">Loading your connected accounts…</p>
          )}

          {stage === "done" && (
            <div className="text-sm text-green-600 dark:text-green-400 font-medium py-2">
              ✓ {scheduledAt ? "Post scheduled" : tiktokDraft ? "Saved as TikTok draft" : "Post published"}
            </div>
          )}

          {stage !== "loading" && stage !== "done" && (
            <>
              {!hasAccounts && (
                <div className="rounded-md border border-amber-300/40 bg-amber-50/40 dark:bg-amber-950/20 p-3 text-xs">
                  You don't have any social accounts connected yet. Ask your admin to
                  connect a TikTok / Instagram / YouTube account.
                </div>
              )}

              {hasAccounts && (
                <section className="space-y-2">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Where to post
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
                              <span className="text-[10px] text-muted-foreground ml-auto">
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
                  When to post
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
                    <span>Post now</span>
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="radio"
                      name="when"
                      checked={!!scheduledAt}
                      onChange={() => { setScheduledAt(minDateTime); setTiktokDraft(false); }}
                      className="accent-primary"
                    />
                    <span>Schedule for:</span>
                    <input
                      type="datetime-local"
                      value={scheduledAt}
                      min={minDateTime}
                      onChange={(e) => { setScheduledAt(e.target.value); setTiktokDraft(false); }}
                      onFocus={() => { if (!scheduledAt) setScheduledAt(minDateTime); }}
                      className="rounded border border-input bg-background px-2 py-0.5 text-xs"
                    />
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="radio"
                      name="when"
                      checked={tiktokDraft}
                      onChange={() => { setTiktokDraft(true); setScheduledAt(""); }}
                      className="accent-primary"
                    />
                    <span>Save as TikTok draft (post manually from the app)</span>
                  </label>
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
            <Button variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
            <Button
              onClick={handlePublish}
              disabled={loading || selected.size === 0 || stage === "loading"}
            >
              {loading
                ? "Working…"
                : scheduledAt
                ? "Schedule post"
                : tiktokDraft
                ? "Save as draft"
                : "Post now"}
            </Button>
          </footer>
        )}
      </div>
    </div>
  );
}

function friendlyError(err) {
  const msg = err?.message || String(err || "");
  if (!msg) return "Something went wrong. Please try again.";
  if (/connect/i.test(msg))    return "Publishing isn't connected. Ask your admin to set it up.";
  if (/rate limit|429/i.test(msg)) return "Hit the rate limit — wait a minute and try again.";
  if (/network|connection/i.test(msg)) return "Couldn't reach the service. Check your internet and try again.";
  // Don't leak status codes or stack traces to the user.
  if (/^\d{3}\b/.test(msg))    return "Publishing failed. Please try again in a moment.";
  return msg;
}
