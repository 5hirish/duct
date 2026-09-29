"use client";

import { useEffect, useState } from "react";
import { Check, Film } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { mediaUrl, selectPostVideo } from "../../lib/contentApi";
import { formatCost } from "../../lib/usageApi";
import EmptyState from "@/components/ui/empty-state";
import { Spinner } from "@/components/ui/spinner";

/**
 * A video post's clip: the player, and every take the agent made.
 *
 * The *cut* is the take that publishes. The agent makes a clip the cut as it
 * makes it, and every earlier take stays, so a clip the owner liked better is
 * one click back rather than another paid render. Watching a take and
 * choosing it are separate on purpose: comparing two takes should not change
 * what goes out.
 *
 * Props:
 *   - postId  — the post the takes belong to.
 *   - video   — the cut, `{asset_id, url, first_frame_url, duration_seconds,
 *               aspect_ratio, cost_usd}`; null before the first clip.
 *   - takes   — newest first, each shaped like `video` plus `is_cut`.
 *   - onChange(post) — optional; the server's post after a take is chosen.
 */
export default function PostVideo({ postId, video, takes = [], onChange }) {
  const { t } = useLingui();
  const [cutId, setCutId] = useState(video?.asset_id || "");
  const [shownId, setShownId] = useState(video?.asset_id || "");
  const [choosing, setChoosing] = useState(false);
  const [error, setError] = useState("");

  // A new clip from the agent is the new cut and the one to watch.
  useEffect(() => {
    setCutId(video?.asset_id || "");
    setShownId(video?.asset_id || "");
  }, [video?.asset_id]);

  const list = takes.length ? takes : video ? [{ ...video, is_cut: true }] : [];
  if (!list.length) {
    return (
      <EmptyState icon={Film} title={t`No clip yet`}>
        <Trans>Once the writing is right, ask Duct to make the clip. It shows up here to watch before it publishes.</Trans>
      </EmptyState>
    );
  }

  const shown = list.find((take) => take.asset_id === shownId) || list[0];
  const isCut = shown.asset_id === cutId;
  const ratio = String(shown.aspect_ratio || "9:16").replace(":", " / ");
  const seconds = Number.isInteger(shown.duration_seconds) ? shown.duration_seconds : null;
  const cost = formatCost(typeof shown.cost_usd === "number" ? shown.cost_usd : null);

  async function choose() {
    if (!postId || choosing) return;
    setChoosing(true);
    setError("");
    try {
      const updated = await selectPostVideo(postId, shown.asset_id);
      setCutId(shown.asset_id);
      onChange?.(updated);
    } catch {
      setError(t`That take couldn't be chosen. Try again.`);
    } finally {
      setChoosing(false);
    }
  }

  return (
    <section className="space-y-3">
      <div
        className="mx-auto w-full max-w-xs overflow-hidden rounded-xl border bg-black"
        style={{ aspectRatio: ratio }}
      >
        <video
          key={shown.asset_id}
          // With no poster, WebKit shows black until played; a first-frame
          // fragment makes it decode one (see ClipStill).
          src={shown.first_frame_url ? mediaUrl(shown.url) : `${mediaUrl(shown.url)}#t=0.1`}
          poster={shown.first_frame_url ? mediaUrl(shown.first_frame_url) : undefined}
          controls
          playsInline
          loop
          preload="metadata"
          aria-label={t`Video clip`}
          className="size-full object-contain"
        />
      </div>

      <div className="mx-auto flex max-w-xs items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>
          {seconds !== null && <Trans>{seconds} s</Trans>}
          {seconds !== null && cost && " · "}
          {cost && <Trans>{cost} to make</Trans>}
        </span>
        {isCut ? (
          <span className="inline-flex items-center gap-1 font-medium text-success">
            <Check className="size-3.5" aria-hidden="true" /> <Trans>Publishing this take</Trans>
          </span>
        ) : (
          <button
            type="button"
            onClick={choose}
            disabled={choosing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/50 disabled:opacity-40"
          >
            {choosing && <Spinner className="size-3" />} <Trans>Use this take</Trans>
          </button>
        )}
      </div>

      {list.length > 1 && (
        <ol aria-label={t`Takes`} className="mx-auto flex max-w-xs gap-2 overflow-x-auto p-1">
          {list.map((take, i) => {
            const number = list.length - i;
            const selected = take.asset_id === shown.asset_id;
            const label = take.asset_id === cutId ? t`Take ${number}, publishing` : t`Take ${number}`;
            return (
              <li key={take.asset_id} className="shrink-0">
                <button
                  type="button"
                  onClick={() => setShownId(take.asset_id)}
                  aria-pressed={selected}
                  aria-label={label}
                  className={`relative block overflow-hidden rounded-md border-2 ${selected ? "border-primary" : "border-transparent hover:border-border"}`}
                >
                  <ClipStill url={take.url} poster={take.first_frame_url} className="aspect-[9/16] h-20 w-auto object-cover" />
                  <span className="absolute inset-x-0 bottom-0 bg-background/80 px-1 text-2xs font-medium">
                    {number}
                  </span>
                  {take.asset_id === cutId && (
                    <Check className="absolute right-0.5 top-0.5 size-3.5 rounded-full bg-success p-0.5 text-background" aria-hidden="true" />
                  )}
                </button>
              </li>
            );
          })}
        </ol>
      )}

      {error && <p role="alert" className="text-center text-xs text-destructive">{error}</p>}
    </section>
  );
}

/**
 * A clip's opening frame, as a picture: for cards and the takes strip, where
 * a playing video would be noise. `#t=0.1` makes WebKit decode a frame instead
 * of showing black, which is also why the desktop shell needs it.
 */
export function ClipStill({ url, poster, className = "" }) {
  if (!url) return null;
  return (
    <video
      src={`${mediaUrl(url)}#t=0.1`}
      poster={poster ? mediaUrl(poster) : undefined}
      muted
      playsInline
      preload="metadata"
      aria-hidden="true"
      tabIndex={-1}
      className={`bg-black ${className}`}
    />
  );
}
