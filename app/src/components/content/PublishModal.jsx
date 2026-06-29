"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  Check,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Send,
  X,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  downloadPostSlides,
  listLinkedAccounts,
  listSocialAccounts,
  mediaUrl,
  publishPostStream,
} from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import DateTimePicker from "./DateTimePicker";
import LinkExistingTab from "./LinkExistingTab";

// Local "YYYY-MM-DDTHH:mm" (NOT UTC — the value is a wall-clock schedule time).
function toLocalInput(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/**
 * Publish flow:
 *   1. Pick one or more connected accounts
 *   2. Choose when (now / schedule / TikTok draft)
 *   3. Submit → backend uploads images to PostBridge + creates the post
 *
 * Props:
 *   - open        : boolean
 *   - onClose     : () => void
 *   - post        : { id, project_id, topic, caption, platforms[] }
 *   - onPublished : (updatedPost) => void  — fired the moment publish succeeds
 *                   (update state only; do NOT close — the success screen needs to show)
 *   - onViewPost  : () => void  — optional; where "View post" / auto-advance goes
 *                   after the celebration (e.g. route to the published view). Falls
 *                   back to onClose.
 */
export default function PublishModal({ open, onClose, post, onPublished, onViewPost, initialTab = "publish" }) {
  const [tab, setTab]               = useState(initialTab);  // "publish" | "link"
  const [accounts, setAccounts]     = useState([]);
  const [selected, setSelected]     = useState(new Set());
  const [scheduledAt, setScheduledAt] = useState("");
  const [tiktokDraft, setTiktokDraft] = useState(false);
  const [loading, setLoading]       = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error,   setError]         = useState("");
  const [stage,   setStage]         = useState("");  // "" | "loading" | "publishing" | "done"
  const [progress, setProgress]     = useState({ phase: "", index: 0, total: 0 });

  // Group accounts by platform for the select list.
  const grouped = useMemo(() => {
    const out = {};
    for (const a of accounts) (out[a.platform] = out[a.platform] || []).push(a);
    return out;
  }, [accounts]);

  useEffect(() => {
    if (!open || !post?.project_id) return;
    setStage("loading"); setError(""); setTab(initialTab || "publish");
    let cancelled = false;
    (async () => {
      try {
        const [list, linked] = await Promise.all([
          listSocialAccounts(post.project_id),
          listLinkedAccounts(post.project_id).catch(() => []),
        ]);
        if (cancelled) return;
        setAccounts(list || []);
        const availableIds = new Set((list || []).map(a => a.id));
        const linkedIds = (linked || [])
          .map(a => Number(a.account_id))
          .filter(id => availableIds.has(id));
        if (linkedIds.length > 0) {
          setSelected(new Set(linkedIds));            // prefer the project's linked accounts
        } else if (Array.isArray(post.platforms) && post.platforms.includes("tiktok")) {
          const ttIds = (list || []).filter(a => a.platform === "tiktok").map(a => a.id);
          setSelected(new Set(ttIds));                // else fall back to TikTok accounts
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
    setProgress({ phase: "prepare", index: 0, total: (post?.slides || []).length });
    let publishedPost = null;
    let streamError = null;
    try {
      await publishPostStream(
        post.id,
        { socialAccountIds: [...selected].map(Number), scheduledAt: scheduledAt || null, tiktokDraft },
        (ev) => {
          switch (ev.event) {
            case "prepare": setProgress((p) => ({ ...p, phase: "prepare", total: ev.total })); break;
            case "upload":  setProgress({ phase: "upload", index: ev.index, total: ev.total }); break;
            case "create":  setProgress((p) => ({ ...p, phase: "create" })); break;
            case "done":    publishedPost = ev.post; break;
            case "error":   streamError = ev.message; break;
            default: break;
          }
        },
      );
      if (streamError) throw new Error(streamError);
      if (!publishedPost) throw new Error("Publishing didn't complete. Please try again.");
      setStage("done");
      onPublished?.(publishedPost);   // update state only — the success screen stays up
      // Let the confetti land, then advance to the published view (or just close).
      setTimeout(() => { setStage(""); (onViewPost || onClose)(); }, 2400);
    } catch (e) {
      setError(friendlyError(e));
      setStage("");
    } finally {
      setLoading(false);
    }
  }

  async function handleDownload() {
    setDownloading(true); setError("");
    try {
      const slug = post?.post_dir_slug || post?.id || "post";
      await downloadPostSlides(post.id, `${slug}-slides.zip`);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setDownloading(false);
    }
  }

  const hasAccounts = accounts.length > 0;
  const minDate = new Date(Date.now() + 5 * 60_000);
  const when = tiktokDraft ? "draft" : scheduledAt ? "schedule" : "now";

  function pickWhen(key) {
    if (key === "now")       { setScheduledAt(""); setTiktokDraft(false); }
    else if (key === "schedule") { setScheduledAt((s) => s || toLocalInput(minDate)); setTiktokDraft(false); }
    else if (key === "draft")    { setTiktokDraft(true); setScheduledAt(""); }
  }

  const subtitle = post?.topic || (post?.caption || "").split("\n")[0] || post?.id;
  const slides = Array.isArray(post?.slides) ? post.slides : [];
  const hasSlides = slides.some((s) => s?.image_url || s?._preview_uri);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-in fade-in-0"
      onClick={(e) => { if (e.target === e.currentTarget && !loading) onClose(); }}
    >
      <div className="flex max-h-[88vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl animate-in zoom-in-95 fade-in-0 duration-200">
        {/* Header */}
        <header className="flex shrink-0 items-start justify-between gap-3 px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold tracking-tight">Publish post</h2>
            {subtitle && <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          {!loading && (
            <button
              onClick={onClose}
              className="-mr-1 -mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              aria-label="Close"
            >
              <X className="size-4" />
            </button>
          )}
        </header>

        {/* Tabs — publish via Duct, or link/mark an already-posted one. Hidden once
            publishing is underway (the progress + success screens own the view). */}
        {(stage === "" || stage === "loading") && (
          <div className="shrink-0 px-5 pb-1">
            <div className="flex gap-1 rounded-lg bg-muted/60 p-1">
              {[["publish", "Publish"], ["link", "Already posted"]].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => { setTab(key); setError(""); }}
                  aria-pressed={tab === key}
                  className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    tab === key ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-2">
          {tab === "link" ? (
            <div className="pt-2">
              <LinkExistingTab post={post} onPublished={onPublished} onClose={onClose} />
            </div>
          ) : (
          <>
          {stage === "loading" && <LoadingSkeleton />}

          {stage === "publishing" && (
            <PublishingProgress slides={slides} progress={progress} scheduled={!!scheduledAt} tiktokDraft={tiktokDraft} />
          )}

          {stage === "done" && (
            <div className="relative flex flex-col items-center justify-center gap-3 overflow-hidden py-10 text-center">
              <Confetti />
              <div className="flex size-16 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500 animate-in zoom-in-50 duration-300">
                <CheckCircle2 className="size-9" />
              </div>
              <p className="text-base font-semibold">
                {scheduledAt ? "Scheduled! 🎉" : tiktokDraft ? "Saved as TikTok draft! 🎉" : "Published! 🎉"}
              </p>
              <p className="text-xs text-muted-foreground">
                {scheduledAt
                  ? "It'll go out at your scheduled time."
                  : tiktokDraft
                  ? "Open TikTok to finish posting."
                  : `Live on ${selected.size} account${selected.size === 1 ? "" : "s"}.`}
              </p>
              <Button className="mt-2" onClick={() => { setStage(""); (onViewPost || onClose)(); }}>
                View post
              </Button>
            </div>
          )}

          {stage === "" && (
            <div className="space-y-5">
              {hasSlides && <ThumbStrip slides={slides} />}

              {!hasAccounts && (
                <div className="rounded-xl border border-amber-400/40 bg-amber-500/10 p-4 text-xs text-amber-700 dark:text-amber-400">
                  No social accounts are connected yet. Connect a TikTok / Instagram / YouTube
                  account on the Accounts tab to publish.
                </div>
              )}

              {hasAccounts && (
                <section className="space-y-2">
                  <SectionLabel>Where to post</SectionLabel>
                  <div className="space-y-2">
                    {Object.entries(grouped).map(([platform, list]) => (
                      <div key={platform} className="space-y-1.5">
                        <p className="flex items-center gap-1.5 px-0.5 text-[11px] font-medium text-muted-foreground">
                          <PlatformGlyph platform={platform} className="size-3" />
                          {platformMeta(platform).label}
                        </p>
                        {list.map((a) => (
                          <AccountRow
                            key={a.id}
                            account={a}
                            selected={selected.has(a.id)}
                            onToggle={() => toggle(a.id)}
                          />
                        ))}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="space-y-2">
                <SectionLabel>When to post</SectionLabel>
                <div className="grid grid-cols-3 gap-2">
                  <WhenCard icon={Zap}           label="Post now"     desc="Publish now"      active={when === "now"}      onClick={() => pickWhen("now")} />
                  <WhenCard icon={CalendarClock} label="Schedule"     desc="Pick a time"      active={when === "schedule"} onClick={() => pickWhen("schedule")} />
                  <WhenCard icon={FileText}      label="TikTok draft" desc="Post in-app"      active={when === "draft"}    onClick={() => pickWhen("draft")} />
                </div>

                {when === "schedule" && (
                  <div className="pt-1">
                    <DateTimePicker
                      value={scheduledAt}
                      min={minDate}
                      onChange={(v) => { setScheduledAt(v); setTiktokDraft(false); }}
                    />
                  </div>
                )}
              </section>

              {error && (
                <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
                  {error}
                </div>
              )}
            </div>
          )}
          </>
          )}
        </div>

        {/* Footer — only the publish picker stage; progress + success + the link
            tab own their own views/actions. */}
        {tab === "publish" && stage === "" && (
          <footer className="flex shrink-0 items-center justify-between gap-2 px-5 py-4">
            {hasSlides ? (
              <Button
                variant="outline" size="sm" onClick={handleDownload} disabled={downloading}
                title="Download the slides + caption as a .zip to post manually"
              >
                {downloading
                  ? <><Loader2 className="size-4 animate-spin" /> Zipping…</>
                  : <><Download className="size-4" /> Download</>}
              </Button>
            ) : <span />}
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button onClick={handlePublish} disabled={selected.size === 0}>
                {when === "schedule"
                  ? <><CalendarClock className="size-4" /> Schedule</>
                  : when === "draft"
                  ? <><FileText className="size-4" /> Save draft</>
                  : <><Send className="size-4" /> Post now</>}
              </Button>
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

function SectionLabel({ children }) {
  return (
    <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{children}</h3>
  );
}

// Lightweight CSS confetti — no dependency. A burst of colored chips rains down
// over the success screen. Keyframes are injected inline (scoped name) so we
// don't have to touch globals.css.
const CONFETTI_COLORS = ["#6366f1", "#22c55e", "#f59e0b", "#ec4899", "#06b6d4", "#a855f7"];

function Confetti() {
  const pieces = useMemo(
    () =>
      Array.from({ length: 80 }, (_, i) => ({
        left: Math.random() * 100,
        delay: Math.random() * 0.5,
        duration: 1.8 + Math.random() * 1.6,
        drift: (Math.random() - 0.5) * 160,
        spin: 360 + Math.random() * 720,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
        w: 5 + Math.random() * 5,
        h: 8 + Math.random() * 8,
      })),
    [],
  );
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <style>{
        "@keyframes pm-confetti{0%{transform:translateY(-16%) translateX(0) rotate(0);opacity:1}" +
        "100%{transform:translateY(360px) translateX(var(--dx)) rotate(var(--r));opacity:0}}"
      }</style>
      {pieces.map((p, i) => (
        <span
          key={i}
          style={{
            position: "absolute",
            top: 0,
            left: `${p.left}%`,
            width: p.w,
            height: p.h,
            background: p.color,
            borderRadius: 1,
            "--dx": `${p.drift}px`,
            "--r": `${p.spin}deg`,
            animation: `pm-confetti ${p.duration}s cubic-bezier(.2,.65,.4,1) ${p.delay}s forwards`,
          }}
        />
      ))}
    </div>
  );
}

// A read-only strip of the post's slide thumbnails (shown in the picker).
function ThumbStrip({ slides }) {
  const withImg = slides.filter((s) => s?.image_url || s?._preview_uri);
  if (!withImg.length) return null;
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1">
      {withImg.map((s, i) => (
        <div key={i} className="relative size-14 shrink-0 overflow-hidden rounded-lg border border-border/60 bg-muted">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={mediaUrl(s.image_url || s._preview_uri)} alt="" referrerPolicy="no-referrer" className="size-full object-cover" />
          <span className="absolute bottom-0.5 right-0.5 rounded bg-black/60 px-1 text-[9px] font-medium tabular-nums text-white">{i + 1}</span>
        </div>
      ))}
    </div>
  );
}

// One slide tile during publishing: dims when pending, spins when uploading,
// flips to a green check once its frame is up.
function SlideThumb({ slide, n, state }) {
  const src = mediaUrl(slide.image_url || slide._preview_uri || "");
  return (
    <div className={`relative size-12 overflow-hidden rounded-lg border transition-colors ${state === "active" ? "border-primary ring-2 ring-primary/40" : "border-border/60"}`}>
      {src
        ? // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt="" referrerPolicy="no-referrer" className={`size-full object-cover transition-opacity ${state === "pending" ? "opacity-40" : ""}`} />
        : <div className="flex size-full items-center justify-center bg-muted text-[10px] text-muted-foreground">{n}</div>}
      {state === "done" && (
        <div className="absolute inset-0 flex items-center justify-center bg-emerald-500/45">
          <Check className="size-4 text-white drop-shadow" />
        </div>
      )}
      {state === "active" && (
        <div className="absolute inset-0 flex items-center justify-center bg-primary/45">
          <Loader2 className="size-4 animate-spin text-white" />
        </div>
      )}
    </div>
  );
}

// Live publish progress — the slide tiles light up as each uploads, with a
// labelled step + bar. Replaces the opaque "Working…" button.
function PublishingProgress({ slides, progress, scheduled, tiktokDraft }) {
  const withImg = slides.filter((s) => s?.image_url || s?._preview_uri);
  const total = progress.total || withImg.length || 1;
  const { phase, index } = progress;
  const pct =
    phase === "prepare" ? 6 :
    phase === "upload"  ? Math.min(92, 6 + Math.round((index / Math.max(1, total)) * 84)) :
    phase === "create"  ? 96 : 100;
  const label =
    phase === "prepare" ? "Preparing your slides…" :
    phase === "upload"  ? `Uploading slide ${index} of ${total}…` :
    phase === "create"  ? (scheduled ? "Scheduling your post…" : tiktokDraft ? "Saving your draft…" : "Creating your post…") :
    "Finishing up…";
  return (
    <div className="flex flex-col gap-4 py-5">
      {withImg.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {withImg.map((s, i) => {
            const n = i + 1;
            const state =
              phase === "create" || phase === "done" ? "done" :
              phase === "upload" ? (n < index ? "done" : n === index ? "active" : "pending") :
              "pending";
            return <SlideThumb key={i} slide={s} n={n} state={state} />;
          })}
        </div>
      )}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Loader2 className="size-4 animate-spin text-primary" />
          <span>{label}</span>
        </div>
        <Progress value={pct} className="h-1.5" />
      </div>
    </div>
  );
}

function AccountRow({ account, selected, onToggle }) {
  const meta = platformMeta(account.platform);
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={selected}
      className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors ${
        selected
          ? "border-primary bg-primary/[0.06] ring-1 ring-primary/30"
          : "border-border hover:bg-muted/50"
      }`}
    >
      <AccountAvatar platform={account.platform} username={account.username} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">@{account.username}</p>
        <p className="truncate text-xs text-muted-foreground">{meta.label} · #{account.id}</p>
      </div>
      <span
        className={`flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
          selected ? "border-primary bg-primary text-primary-foreground" : "border-border bg-background"
        }`}
      >
        {selected && <Check className="size-3.5" />}
      </span>
    </button>
  );
}

function AccountAvatar({ platform, username }) {
  const meta = platformMeta(platform);
  const [failed, setFailed] = useState(false);
  // PostBridge doesn't return avatars; resolve a best-effort one from the handle.
  const src = failed || !username
    ? ""
    : `https://unavatar.io/${platform}/${encodeURIComponent(username)}?fallback=false`;
  const initial = (username || "?").charAt(0).toUpperCase();
  return (
    <div className="relative shrink-0">
      <div className="flex size-10 items-center justify-center overflow-hidden rounded-full border border-border/60 bg-muted">
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt=""
            className="size-full object-cover"
            referrerPolicy="no-referrer"
            onError={() => setFailed(true)}
          />
        ) : (
          <span className="text-sm font-semibold text-muted-foreground">{initial}</span>
        )}
      </div>
      <span
        className="absolute -bottom-0.5 -right-0.5 flex size-[18px] items-center justify-center rounded-full border-2 border-card text-white"
        title={meta.label}
        style={{ backgroundColor: meta.color }}
      >
        <PlatformGlyph platform={platform} className="size-2.5" />
      </span>
    </div>
  );
}

function WhenCard({ icon: Icon, label, desc, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex flex-col items-start gap-1 rounded-xl border px-3 py-2.5 text-left transition-colors ${
        active
          ? "border-primary bg-primary/[0.06] ring-1 ring-primary/30"
          : "border-border hover:bg-muted/50"
      }`}
    >
      <Icon className={`size-4 ${active ? "text-primary" : "text-muted-foreground"}`} />
      <span className="text-xs font-semibold">{label}</span>
      <span className="text-[10px] leading-tight text-muted-foreground">{desc}</span>
    </button>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-5 py-1">
      <div className="space-y-2">
        <Skeleton className="h-3 w-24" />
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center gap-3 rounded-xl border border-border px-3 py-2.5">
            <Skeleton className="size-10 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-32" />
              <Skeleton className="h-2.5 w-20" />
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <Skeleton className="h-3 w-24" />
        <div className="grid grid-cols-3 gap-2">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
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
  if (/^\d{3}\b/.test(msg))    return "Publishing failed. Please try again in a moment.";
  return msg;
}
