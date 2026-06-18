"use client";

import { useEffect, useRef, useState } from "react";
import {
  BarChart3,
  Bookmark,
  Check,
  Clock,
  ExternalLink,
  Eye,
  Gauge,
  Heart,
  MessageCircle,
  Pencil,
  Radio,
  RefreshCw,
  Share2,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import { syncPostMetrics, updatePostMetrics } from "../../lib/contentApi";
import {
  audienceAgeOf,
  coreMetrics,
  derivedRates,
  extraMetrics,
  fmtCount,
  fmtPct,
  fmtRate,
  fmtSeconds,
  hasAnyMetric,
  isPostBridgeBacked,
  lastUpdatedAt,
  retentionOf,
  safeHref,
  timeAgo,
} from "../../lib/contentMetrics";

// The five headline tiles. The first four are synced from PostBridge when it
// published the post (read-only then); `saves` is always hand-entered.
const CORE = [
  { field: "views",    label: "Views",    icon: Eye },
  { field: "likes",    label: "Likes",    icon: Heart },
  { field: "comments", label: "Comments", icon: MessageCircle },
  { field: "shares",   label: "Shares",   icon: Share2 },
  { field: "saves",    label: "Saves",    icon: Bookmark, manual: true },
];

// PostBridge-owned counts — read-only on a post it published.
const AUTO_FIELDS = new Set(["views", "likes", "comments", "shares"]);

// Platform-native scalars PostBridge never returns — all manual.
const EXTRA = [
  { field: "reach",          label: "Reach",          icon: Radio,    kind: "int", fmt: fmtCount },
  { field: "profileViews",   label: "Profile views",  icon: Eye,      kind: "int", fmt: fmtCount },
  { field: "newFollowers",   label: "New followers",  icon: UserPlus, kind: "int", fmt: fmtCount },
  { field: "avgWatchTime",   label: "Avg watch",      icon: Clock,    kind: "sec", fmt: fmtSeconds },
  { field: "completionRate", label: "Watched full",   icon: Gauge,    kind: "pct", fmt: fmtPct },
];

// camelCase form field → snake_case ManualMetrics key.
const SNAKE = {
  views: "views", likes: "likes", comments: "comments", shares: "shares", saves: "saves",
  reach: "reach", profileViews: "profile_views", newFollowers: "new_followers",
  avgWatchTime: "avg_watch_time", completionRate: "completion_rate",
};

const AUDIENCE_BUCKETS = ["13-17", "18-24", "25-34", "35-44", "45-54", "55+"];

const numStr = (v) => (v == null ? "" : String(v));

// slide1..slideN keys, unioning the post's slide count with any keys already
// stored, so retention rows match the actual carousel.
function slideKeys(post, retention) {
  const n = Math.max(
    Array.isArray(post?.slides) ? post.slides.length : 0,
    Number(post?.slide_count) || 0,
    retention ? Object.keys(retention).length : 0,
  );
  return Array.from({ length: n }, (_, i) => `slide${i + 1}`);
}

function audienceKeys(audience) {
  const extra = audience ? Object.keys(audience).filter((k) => !AUDIENCE_BUCKETS.includes(k)) : [];
  return [...AUDIENCE_BUCKETS, ...extra];
}

function seedForm(post) {
  const perf = post?.perf || {};
  const c = coreMetrics(perf);
  const e = extraMetrics(perf);
  const ret = retentionOf(perf) || {};
  const aud = audienceAgeOf(perf) || {};
  return {
    values: {
      views: numStr(c.views), likes: numStr(c.likes), comments: numStr(c.comments),
      shares: numStr(c.shares), saves: numStr(c.saves),
      reach: numStr(e.reach), profileViews: numStr(e.profileViews),
      newFollowers: numStr(e.newFollowers), avgWatchTime: numStr(e.avgWatchTime),
      completionRate: numStr(e.completionRate),
    },
    retention: Object.fromEntries(slideKeys(post, ret).map((k) => [k, numStr(ret[k])])),
    audience: Object.fromEntries(audienceKeys(aud).map((k) => [k, numStr(aud[k])])),
  };
}

// Turn the form into a ManualMetrics payload — only filled-in fields, and never
// the auto (PostBridge) counts on a post it published.
function buildPayload(form, editableCore) {
  const out = {};
  for (const [field, snake] of Object.entries(SNAKE)) {
    if (!editableCore && AUTO_FIELDS.has(field)) continue;
    const raw = form.values[field];
    if (raw === "" || raw == null) continue;
    const num = Number(raw);
    if (Number.isFinite(num) && num >= 0) out[snake] = num;
  }
  const collect = (obj) => {
    const r = {};
    for (const [k, raw] of Object.entries(obj)) {
      if (raw === "" || raw == null) continue;
      const num = Number(raw);
      if (Number.isFinite(num) && num >= 0) r[k] = num;
    }
    return r;
  };
  const ret = collect(form.retention);
  if (Object.keys(ret).length) out.retention = ret;
  const aud = collect(form.audience);
  if (Object.keys(aud).length) out.audience_age = aud;
  return out;
}

/**
 * Performance card for a published post. Shows stored perf immediately, pulls
 * the latest from PostBridge on open (for posts it published), and lets the user
 * hand-enter the metrics PostBridge can't supply — saves, reach, watch time,
 * completion, per-slide retention and audience age. Rendered for ANY posted post
 * (PostBridge-backed or not); a non-PostBridge post is fully manual.
 *
 * Props:
 *   - post       : the post (reads post.perf, post.post_bridge_post_id, slides)
 *   - onUpdated(updatedPost) : bubble a fresh post up so the parent stays in sync
 */
export default function PostMetrics({ post, onUpdated }) {
  const [perf, setPerf] = useState(post?.perf || {});
  const [syncing, setSyncing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => seedForm(post));
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState("");
  const fetchedIdRef = useRef(null);

  const pbBacked = isPostBridgeBacked(post);
  const editableCore = !pbBacked; // non-PostBridge posts hand-enter the core too

  // On mount AND whenever you navigate to a different post (Next reuses this
  // component across route-param changes), re-seed the display + form from the
  // post's stored perf, then pull the latest from PostBridge. Keyed on post.id
  // so it re-fires per post; fetchedIdRef dedupes StrictMode's double-mount and
  // ignores the parent's perf-only re-renders (same id → no refetch/clobber).
  // 429s are swallowed server-side, so a refetch on every visit is safe.
  useEffect(() => {
    setPerf(post?.perf || {});
    setForm(seedForm(post));
    setEditing(false);
    if (pbBacked && fetchedIdRef.current !== post?.id) {
      fetchedIdRef.current = post?.id;
      refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [post?.id]);

  async function refresh() {
    setSyncing(true);
    setNote("");
    try {
      const updated = await syncPostMetrics(post.id);
      setPerf(updated?.perf || {});
      onUpdated?.(updated);
    } catch (e) {
      const msg = e?.message || "";
      // Platform analytics arrive on a lag — a freshly-posted item exists but has
      // no numbers yet. Say so plainly (vendor-neutral) instead of erroring.
      setNote(/synced|processing|finished|publish|result|few minutes/i.test(msg)
        ? "Analytics for this post aren't in yet — they can take a day or two. Add them manually in the meantime to help Duct plan better."
        : (msg || "Couldn't refresh automatically — add numbers manually or try again shortly."));
    } finally {
      setSyncing(false);
    }
  }

  function startEdit() {
    setForm(seedForm({ ...post, perf }));
    setNote("");
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setNote("");
  }

  async function save() {
    const payload = buildPayload(form, editableCore);
    if (!Object.keys(payload).length) { setEditing(false); return; }
    setSaving(true);
    setNote("");
    try {
      const updated = await updatePostMetrics(post.id, payload);
      setPerf(updated?.perf || {});
      onUpdated?.(updated);
      setEditing(false);
    } catch (e) {
      setNote(e?.message || "Couldn't save metrics — try again.");
    } finally {
      setSaving(false);
    }
  }

  const setVal = (field, v) => setForm((f) => ({ ...f, values: { ...f.values, [field]: v } }));
  const setRet = (k, v) => setForm((f) => ({ ...f, retention: { ...f.retention, [k]: v } }));
  const setAud = (k, v) => setForm((f) => ({ ...f, audience: { ...f.audience, [k]: v } }));

  const core = coreMetrics(perf);
  const extra = extraMetrics(perf);
  const { saveRate, engagementRate } = derivedRates(perf);
  const retention = retentionOf(perf);
  const audience = audienceAgeOf(perf);
  const updatedAt = lastUpdatedAt(perf);
  const shareUrl = safeHref(perf?.share_url);
  const showExtras = EXTRA.some(({ field }) => extra[field] != null);

  return (
    <section className="space-y-3 rounded-2xl border border-border bg-card p-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <BarChart3 className="size-4 text-primary" /> Performance
        </h3>
        <div className="flex items-center gap-2">
          {!editing && updatedAt && (
            <span className="text-[11px] text-muted-foreground">Updated {timeAgo(updatedAt)}</span>
          )}
          {editing ? (
            <>
              <button
                type="button"
                onClick={cancelEdit}
                disabled={saving}
                className="inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs font-medium hover:bg-muted/50 disabled:opacity-50"
              >
                <X className="size-3.5" /> Cancel
              </button>
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                <Check className="size-3.5" /> {saving ? "Saving…" : "Save"}
              </button>
            </>
          ) : (
            <>
              {pbBacked && (
                <button
                  type="button"
                  onClick={refresh}
                  disabled={syncing}
                  title="Pull the latest numbers for this post"
                  className="inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs font-medium hover:bg-muted/50 disabled:opacity-50"
                >
                  <RefreshCw className={`size-3.5 ${syncing ? "animate-spin" : ""}`} /> {syncing ? "Syncing…" : "Refresh"}
                </button>
              )}
              <button
                type="button"
                onClick={startEdit}
                title="Enter or correct metrics by hand"
                className="inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs font-medium hover:bg-muted/50"
              >
                <Pencil className="size-3.5" /> Edit
              </button>
            </>
          )}
        </div>
      </div>

      {/* Core tiles */}
      <div className="grid grid-cols-5 gap-2">
        {CORE.map(({ field, label, icon: Icon, manual }) => {
          const locked = editing && AUTO_FIELDS.has(field) && !editableCore;
          return (
            <div key={field} className="rounded-xl border border-border/60 bg-muted/30 px-3 py-2.5">
              <div className="flex items-center justify-between">
                <Icon className="size-4 text-muted-foreground" />
                {editing && (manual || editableCore) && !locked && (
                  <span className="text-[9px] font-medium uppercase tracking-wide text-primary/70">edit</span>
                )}
                {editing && locked && (
                  <span className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground/60">auto</span>
                )}
              </div>
              {editing && !locked ? (
                <NumberInput value={form.values[field]} onChange={(v) => setVal(field, v)} />
              ) : (
                <p className="mt-1.5 text-lg font-semibold leading-none tabular-nums">
                  {syncing && !hasAnyMetric(perf) ? "…" : fmtCount(core[field])}
                </p>
              )}
              <p className="mt-1 text-[11px] text-muted-foreground">{label}</p>
            </div>
          );
        })}
      </div>

      {/* Derived rates */}
      {(saveRate != null || engagementRate != null) && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <span>Save rate <span className="font-medium text-foreground tabular-nums">{fmtRate(saveRate)}</span></span>
          <span>Engagement <span className="font-medium text-foreground tabular-nums">{fmtRate(engagementRate)}</span></span>
        </div>
      )}

      {/* More metrics */}
      {editing ? (
        <Group title="More metrics" icon={Gauge}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {EXTRA.map(({ field, label, kind }) => (
              <Field key={field} label={label}>
                <NumberInput
                  value={form.values[field]}
                  onChange={(v) => setVal(field, v)}
                  step={kind === "int" ? 1 : 0.1}
                  max={kind === "pct" ? 100 : undefined}
                  suffix={kind === "pct" ? "%" : kind === "sec" ? "s" : ""}
                />
              </Field>
            ))}
          </div>
        </Group>
      ) : showExtras ? (
        <Reveal title="More metrics" icon={Gauge}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {EXTRA.filter(({ field }) => extra[field] != null).map(({ field, label, icon: Icon, fmt }) => (
              <ReadStat key={field} icon={Icon} label={label} value={fmt(extra[field])} />
            ))}
          </div>
        </Reveal>
      ) : null}

      {/* Retention per slide */}
      {editing ? (
        Object.keys(form.retention).length > 0 && (
          <Group title="Retention per slide" icon={BarChart3}>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {Object.keys(form.retention).map((k, i) => (
                <Field key={k} label={`Slide ${i + 1}`}>
                  <NumberInput value={form.retention[k]} onChange={(v) => setRet(k, v)} max={100} suffix="%" />
                </Field>
              ))}
            </div>
          </Group>
        )
      ) : retention ? (
        <Reveal title="Retention per slide" icon={BarChart3}>
          <div className="space-y-1.5">
            {Object.entries(retention).map(([k, v], i) => (
              <RetentionBar key={k} label={`Slide ${i + 1}`} pct={typeof v === "number" ? v : null} />
            ))}
          </div>
        </Reveal>
      ) : null}

      {/* Audience age */}
      {editing ? (
        <Group title="Audience age" icon={Users}>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            {Object.keys(form.audience).map((k) => (
              <Field key={k} label={k}>
                <NumberInput value={form.audience[k]} onChange={(v) => setAud(k, v)} max={100} suffix="%" />
              </Field>
            ))}
          </div>
        </Group>
      ) : audience ? (
        <Reveal title="Audience age" icon={Users}>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            {Object.entries(audience).map(([k, v]) => (
              <span key={k}>{k} <span className="font-medium text-foreground tabular-nums">{fmtPct(typeof v === "number" ? v : null)}</span></span>
            ))}
          </div>
        </Reveal>
      ) : null}

      {note && <p className="text-[11px] text-muted-foreground">{note}</p>}

      {editing ? (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {pbBacked
            ? "Views, likes, comments and shares are tracked automatically. Add saves, watch time and audience from your post's analytics — it sharpens what Duct plans next."
            : "Add every metric from your post's analytics — it sharpens what Duct plans next."}
        </p>
      ) : (
        // Persistent nudge: automatic numbers are basic and lag a little, so
        // hand-entered metrics (especially saves) materially improve planning.
        <p className="border-t border-border/50 pt-2.5 text-[11px] leading-relaxed text-muted-foreground">
          Tracked numbers can lag a day or two and only cover the basics.{" "}
          <button type="button" onClick={startEdit} className="font-medium text-primary hover:underline">
            Add saves, watch time and audience
          </button>{" "}
          to sharpen what Duct plans next.
        </p>
      )}

      {!editing && shareUrl && (
        <a
          href={shareUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          <ExternalLink className="size-3.5" /> View on platform
        </a>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

function NumberInput({ value, onChange, step = 1, max, suffix = "" }) {
  return (
    <div className="mt-1.5 flex items-center gap-1">
      <input
        type="number"
        inputMode="decimal"
        min={0}
        step={step}
        max={max}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="—"
        className="w-full rounded-lg border border-input bg-input/40 px-2 py-1 text-sm tabular-nums outline-none transition-[box-shadow,border-color] focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25"
      />
      {suffix && <span className="text-[11px] text-muted-foreground">{suffix}</span>}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

// Edit-mode group — always expanded, titled.
function Group({ title, icon: Icon, children }) {
  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-muted/20 p-3">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" /> {title}
      </p>
      {children}
    </div>
  );
}

// View-mode collapsible (native <details> — no state needed).
function Reveal({ title, icon: Icon, children }) {
  return (
    <details className="group rounded-xl border border-border/60 bg-muted/20 p-3 [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" /> {title}
        <span className="ml-auto text-muted-foreground/60 transition-transform group-open:rotate-180">⌄</span>
      </summary>
      <div className="mt-2.5">{children}</div>
    </details>
  );
}

function ReadStat({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-background/40 px-2.5 py-1.5">
      <Icon className="size-3.5 text-muted-foreground" />
      <div className="min-w-0">
        <p className="truncate text-[10px] text-muted-foreground">{label}</p>
        <p className="text-sm font-semibold leading-none tabular-nums">{value}</p>
      </div>
    </div>
  );
}

function RetentionBar({ label, pct }) {
  const w = pct == null ? 0 : Math.max(0, Math.min(100, pct));
  return (
    <div className="flex items-center gap-2">
      <span className="w-14 shrink-0 text-[11px] text-muted-foreground">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary/70" style={{ width: `${w}%` }} />
      </div>
      <span className="w-10 shrink-0 text-right text-[11px] font-medium tabular-nums">{fmtPct(pct)}</span>
    </div>
  );
}
