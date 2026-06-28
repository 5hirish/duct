"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Link2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { linkPostBridgePost, listPostBridgePosts, markPostPosted } from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";

/**
 * "Already posted" flow — for a post the user published outside Duct's publish
 * button. Two paths, in order of value:
 *
 *   1. LINK it to an existing PostBridge post → its analytics sync into the card.
 *   2. Just MARK it posted (no PostBridge) → gets it off the draft board, no metrics.
 *
 * Self-contained: loads the linkable PostBridge posts itself, owns its success
 * state, and on success calls onPublished(updatedPost) then onClose() after a beat.
 *
 * Props:
 *   - post        : { id, project_id, platforms[] }
 *   - onPublished : (updatedPost) => void  — update parent state with the linked card
 *   - onClose     : () => void
 */
export default function LinkExistingTab({ post, onPublished, onClose }) {
  const [rows, setRows]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [busyId, setBusyId]   = useState("");        // pb post id being linked
  const [marking, setMarking] = useState(false);
  const [error, setError]     = useState("");
  const [done, setDone]       = useState("");        // success message → celebrate + close

  useEffect(() => {
    if (!post?.project_id) return;
    let cancelled = false;
    setLoading(true); setListError("");
    (async () => {
      try {
        const list = await listPostBridgePosts(post.project_id);
        if (!cancelled) setRows(Array.isArray(list) ? list : []);
      } catch (e) {
        if (!cancelled) setListError(friendlyError(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [post?.project_id]);

  function succeed(updated, message) {
    onPublished?.(updated);
    setDone(message);
    setTimeout(() => onClose?.(), 1900);
  }

  async function handleLink(row) {
    setBusyId(row.id); setError("");
    try {
      const updated = await linkPostBridgePost(post.id, { postBridgePostId: row.id });
      succeed(updated, "Linked! Analytics will sync into this post.");
    } catch (e) {
      setError(friendlyError(e));
      setBusyId("");
    }
  }

  async function handleMark() {
    setMarking(true); setError("");
    try {
      const updated = await markPostPosted(post.id);
      succeed(updated, "Marked as posted.");
    } catch (e) {
      setError(friendlyError(e));
      setMarking(false);
    }
  }

  if (done) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
        <div className="flex size-14 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500 animate-in zoom-in-50 duration-300">
          <CheckCircle2 className="size-8" />
        </div>
        <p className="text-base font-semibold">{done}</p>
      </div>
    );
  }

  const busy = !!busyId || marking;

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Posted this somewhere else? Link it to an existing PostBridge post to pull in
        its analytics — or just mark it posted to clear it off the board.
      </p>

      {/* PostBridge posts to link */}
      <section className="space-y-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Link to a PostBridge post
        </h3>

        {loading && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-3 rounded-xl border border-border px-3 py-2.5">
                <Skeleton className="size-9 rounded-lg" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-40" />
                  <Skeleton className="h-2.5 w-24" />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && listError && (
          <div className="rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-400">
            {listError}
          </div>
        )}

        {!loading && !listError && rows.length === 0 && (
          <div className="rounded-xl border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
            No PostBridge posts found on the connected account. You can still mark this
            post as posted below.
          </div>
        )}

        {!loading && rows.length > 0 && (
          <div className="max-h-64 space-y-2 overflow-y-auto pr-0.5">
            {rows.map((row) => (
              <LinkRow
                key={row.id}
                row={row}
                busy={busy}
                linking={busyId === row.id}
                onLink={() => handleLink(row)}
              />
            ))}
          </div>
        )}
      </section>

      {error && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Mark posted without linking */}
      <section className="space-y-2 border-t border-border/60 pt-4">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Or mark it posted
        </h3>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            No PostBridge link — just move it to <span className="font-medium text-foreground">Posted</span>. No analytics.
          </p>
          <Button variant="outline" size="sm" onClick={handleMark} disabled={busy}>
            {marking ? <><Loader2 className="size-4 animate-spin" /> Marking…</> : "Mark as posted"}
          </Button>
        </div>
      </section>
    </div>
  );
}

function LinkRow({ row, busy, linking, onLink }) {
  const accounts = Array.isArray(row.accounts) ? row.accounts : [];
  const preview = (row.caption || "").split("\n")[0].trim() || "(no caption)";
  const when = row.created_at ? new Date(row.created_at).toLocaleDateString() : "";
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border px-3 py-2.5">
      <div className="flex -space-x-1.5">
        {accounts.length > 0 ? (
          accounts.slice(0, 3).map((a) => (
            <span
              key={a.id}
              title={`${platformMeta(a.platform).label} · @${a.username}`}
              className="flex size-7 items-center justify-center rounded-full border-2 border-card text-white"
              style={{ backgroundColor: platformMeta(a.platform).color }}
            >
              <PlatformGlyph platform={a.platform} className="size-3" />
            </span>
          ))
        ) : (
          <span className="flex size-7 items-center justify-center rounded-full border-2 border-card bg-muted text-muted-foreground">
            <Link2 className="size-3" />
          </span>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{preview}</p>
        <p className="truncate text-[11px] text-muted-foreground">
          <span className="capitalize">{row.status || "—"}</span>
          {row.is_draft ? " · draft" : ""}
          {when ? ` · ${when}` : ""}
        </p>
      </div>

      {row.already_linked ? (
        <span
          className="flex shrink-0 items-center gap-1 rounded-md bg-muted px-2 py-1 text-[11px] text-muted-foreground"
          title={row.linked_label ? `Linked to ${row.linked_label}` : "Already linked"}
        >
          <CheckCircle2 className="size-3.5" /> Linked
        </span>
      ) : (
        <Button size="sm" variant="outline" onClick={onLink} disabled={busy} className="shrink-0">
          {linking
            ? <><Loader2 className="size-4 animate-spin" /> Linking…</>
            : <><ExternalLink className="size-3.5" /> Link</>}
        </Button>
      )}
    </div>
  );
}

function friendlyError(err) {
  const msg = err?.message || String(err || "");
  if (!msg) return "Something went wrong. Please try again.";
  if (/connect/i.test(msg)) return "PostBridge isn't connected. Ask your admin to set it up.";
  if (/rate limit|429/i.test(msg)) return "Hit the rate limit — wait a minute and try again.";
  if (/network|connection/i.test(msg)) return "Couldn't reach the service. Check your internet and try again.";
  if (/already linked/i.test(msg)) return msg;
  if (/^\d{3}\b/.test(msg)) return "That didn't work. Please try again in a moment.";
  return msg;
}
