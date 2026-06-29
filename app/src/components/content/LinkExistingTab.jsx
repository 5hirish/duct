"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Loader2, Play, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { linkPostBridgePost, listPostBridgePosts, markPostPosted } from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import DateTimePicker from "./DateTimePicker";

// Local "YYYY-MM-DDTHH:mm" (wall-clock, not UTC) — seeds the posted-on picker.
function toLocalInput(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/**
 * "Already posted" flow — for a post the user published outside Duct's publish
 * button. Two paths, in order of value:
 *
 *   1. LINK it to an existing PostBridge post → its analytics sync into the card.
 *   2. Just MARK it posted (no PostBridge) → gets it off the draft board, no metrics.
 *
 * Only posts published *through* PostBridge appear in the list — content posted
 * natively (e.g. straight in the TikTok app) is invisible to PostBridge, so for
 * those the user takes path 2.
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
  const [refreshing, setRefreshing] = useState(false);
  const [listError, setListError] = useState("");
  const [busyId, setBusyId]   = useState("");        // pb post id being linked
  const [marking, setMarking] = useState(false);
  const [postedAt, setPostedAt] = useState(() => toLocalInput(new Date()));  // when it actually went out
  const [error, setError]     = useState("");
  const [done, setDone]       = useState("");        // success message → celebrate + close

  const load = useCallback(async ({ isRefresh = false } = {}) => {
    if (!post?.project_id) return;
    isRefresh ? setRefreshing(true) : setLoading(true);
    setListError("");
    try {
      const list = await listPostBridgePosts(post.project_id);
      setRows(Array.isArray(list) ? list : []);
    } catch (e) {
      setListError(friendlyError(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [post?.project_id]);

  useEffect(() => { load(); }, [load]);

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
      // Convert the wall-clock pick → ISO (UTC) so the real publish time is stored.
      const iso = postedAt ? new Date(postedAt).toISOString() : undefined;
      const updated = await markPostPosted(post.id, { postedAt: iso });
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
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Link to a PostBridge post
          </h3>
          <button
            type="button"
            onClick={() => load({ isRefresh: true })}
            disabled={loading || refreshing || busy}
            title="Refresh the list"
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw className={`size-3 ${refreshing ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>

        <p className="text-[11px] leading-snug text-muted-foreground/80">
          Only posts published through Duct/PostBridge appear here. Posted directly in
          the app (e.g. TikTok)? It won&apos;t show — use <span className="font-medium text-foreground">Mark as posted</span> below.
        </p>

        {loading && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-3 rounded-xl border border-border px-3 py-2.5">
                <Skeleton className="h-[72px] w-[54px] rounded-lg" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-44" />
                  <Skeleton className="h-3.5 w-28" />
                  <Skeleton className="h-2.5 w-20" />
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
            No PostBridge posts found on the connected account. If you posted it in the
            app, mark this post as posted below.
          </div>
        )}

        {!loading && rows.length > 0 && (
          <div className="max-h-[22rem] space-y-2 overflow-y-auto pr-0.5">
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
        <p className="text-xs text-muted-foreground">
          No PostBridge link — set when it actually went out and move it to{" "}
          <span className="font-medium text-foreground">Posted</span>. No analytics.
        </p>
        <div className="space-y-1">
          <label className="text-[11px] font-medium text-muted-foreground">Posted on</label>
          <DateTimePicker value={postedAt} onChange={setPostedAt} />
        </div>
        <div className="flex justify-end pt-1">
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
  const platform = accounts[0]?.platform || (row.is_video ? "tiktok" : "");
  const preview = (row.caption || "").split("\n")[0].trim() || "(no caption)";
  const when = row.created_at ? new Date(row.created_at).toLocaleDateString() : "";
  const handle = accounts[0]?.username ? `@${accounts[0].username}` : "";
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border px-3 py-2.5">
      <Thumb url={row.thumbnail_url} isVideo={row.is_video} platform={platform} />

      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm font-medium leading-snug">{preview}</p>
        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
          <span className="capitalize">{row.status || "—"}</span>
          {row.is_draft ? " · draft" : ""}
          {when ? ` · ${when}` : ""}
          {handle ? ` · ${handle}` : ""}
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

// Portrait cover thumbnail (9:16-ish). Image posts → <img>; video posts → a
// muted <video> seeked to the first frame; nothing resolvable → a glyph tile.
function Thumb({ url, isVideo, platform }) {
  const [failed, setFailed] = useState(false);
  const show = url && !failed;
  return (
    <div className="relative h-[72px] w-[54px] shrink-0 overflow-hidden rounded-lg border border-border/60 bg-muted">
      {show ? (
        isVideo ? (
          <>
            <video
              src={`${url}#t=0.1`}
              muted
              playsInline
              preload="metadata"
              className="h-full w-full object-cover"
              onError={() => setFailed(true)}
            />
            <span className="absolute inset-0 flex items-center justify-center bg-black/15">
              <Play className="size-4 fill-white text-white drop-shadow" />
            </span>
          </>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt=""
            referrerPolicy="no-referrer"
            className="h-full w-full object-cover"
            onError={() => setFailed(true)}
          />
        )
      ) : (
        <div className="flex h-full w-full items-center justify-center text-muted-foreground">
          {platform ? <PlatformGlyph platform={platform} className="size-4" /> : null}
        </div>
      )}
      {platform && show && (
        <span
          className="absolute bottom-0.5 left-0.5 flex size-4 items-center justify-center rounded text-white"
          title={platformMeta(platform).label}
          style={{ backgroundColor: platformMeta(platform).color }}
        >
          <PlatformGlyph platform={platform} className="size-2.5" />
        </span>
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
