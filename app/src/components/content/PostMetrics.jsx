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
  Images,
  MapPin,
  MessageCircle,
  Pencil,
  Radio,
  RefreshCw,
  Search,
  Share2,
  TrendingUp,
  UserCircle,
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
  genderOf,
  hasAnyMetric,
  isPostBridgeBacked,
  lastUpdatedAt,
  locationsOf,
  retentionOf,
  safeHref,
  searchQueriesOf,
  timeAgo,
  trafficSourcesOf,
} from "../../lib/contentMetrics";
import MetricCurveInput from "./MetricCurveInput";
import MetricBars from "./MetricBars";
import { countryNames } from "../../lib/countries";

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

// camelCase form field → snake_case ManualMetrics key.
const SNAKE = {
  views: "views", likes: "likes", comments: "comments", shares: "shares", saves: "saves",
  reach: "reach", profileViews: "profile_views", newFollowers: "new_followers",
  avgWatchTime: "avg_watch_time", completionRate: "completion_rate",
  retentionRate: "retention_rate", photosViewed: "photos_viewed",
};

const AGE_BUCKETS    = ["13-17", "18-24", "25-34", "35-44", "45-54", "55+"];
const GENDER_BUCKETS = ["Male", "Female", "Other"];
// TikTok's traffic-source rows, in its order.
const TRAFFIC_BUCKETS = [
  "For You", "Search", "Following", "Direct messages", "Personal profile", "Sound", "Other",
];

const numStr = (v) => (v == null ? "" : String(v));
const round1 = (v) => Number(Number(v).toFixed(1));

// Treat it as a video if typed so, OR if it carries a clip / storyboard — so a
// post whose post_type didn't round-trip still shows the video metrics.
function isVideoPost(post) {
  return (
    post?.post_type === "video" ||
    Boolean(post?.video_url) ||
    (Array.isArray(post?.video_storyboard) && post.video_storyboard.length > 0)
  );
}

// seconds → "M:SS" (matches TikTok's retention-curve axis labels).
function fmtTime(s) {
  const sec = Math.max(0, Math.floor(Number(s) || 0));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

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

// Retention is curve-shaped, but the X-axis differs by type:
//   VIDEO     → one point per SECOND, 0..duration (keys "0".."N", time-labelled)
//   SLIDESHOW → one point per SLIDE  (keys "slide1".."slideN")
// Integer-string keys ("0","1",…) iterate in numeric order in JS objects, so the
// video curve stays in order without extra sorting.
function retentionBuckets(post, retention) {
  if (isVideoPost(post)) {
    const stored = Object.keys(retention || {}).map(Number).filter(Number.isFinite);
    const dur = Number(post?.video_duration_seconds) || (stored.length ? Math.max(...stored) : 0) || 10;
    const n = Math.min(Math.max(dur, 1), 60);   // 0..dur, capped for sanity
    return Array.from({ length: n + 1 }, (_, i) => String(i));
  }
  return slideKeys(post, retention);
}

// Label one retention bucket: a time for video, a slide number for a carousel.
const retentionLabel = (post, key, i) =>
  isVideoPost(post) ? fmtTime(key) : `Slide ${i + 1}`;
const retentionTitle = (post) =>
  isVideoPost(post) ? "Retention over time" : "Retention per slide";

function ageKeys(audience) {
  const extra = audience ? Object.keys(audience).filter((k) => !AGE_BUCKETS.includes(k)) : [];
  return [...AGE_BUCKETS, ...extra];
}

// Fixed-bucket dict → form values (string per bucket).
const bucketForm = (keys, d) => Object.fromEntries(keys.map((k) => [k, numStr(d?.[k])]));
// MetricBars items ([{key,value}]) → a {key: value} object (fixed-bucket dims).
const itemsToObj = (items) => Object.fromEntries((items || []).map((it) => [it.key, it.value]));
// Free-form dict → editable rows (sorted desc so the biggest shares lead).
const dictToRows = (d) =>
  Object.entries(d || {})
    .filter(([, v]) => typeof v === "number")
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ key, value: numStr(value) }));

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
      completionRate: numStr(e.completionRate), retentionRate: numStr(e.retentionRate),
      photosViewed: numStr(e.photosViewed),
    },
    retention: bucketForm(retentionBuckets(post, ret), ret),
    audience:  bucketForm(ageKeys(aud), aud),
    gender:    bucketForm(GENDER_BUCKETS, genderOf(perf) || {}),
    traffic:   bucketForm(TRAFFIC_BUCKETS, trafficSourcesOf(perf) || {}),
    locations: dictToRows(locationsOf(perf)),
    queries:   dictToRows(searchQueriesOf(perf)),
  };
}

// Collect a fixed-bucket form ({bucket: str}) → {bucket: number}, dropping blanks.
function collectDict(obj) {
  const r = {};
  for (const [k, raw] of Object.entries(obj)) {
    if (raw === "" || raw == null) continue;
    const num = Number(raw);
    if (Number.isFinite(num) && num >= 0) r[k] = num;
  }
  return r;
}

// Collect free-form rows ([{key,value}]) → {key: number}, dropping blank rows.
function rowsToDict(rows) {
  const r = {};
  for (const { key, value } of rows || []) {
    const k = (key || "").trim();
    if (!k || value === "" || value == null) continue;
    const num = Number(value);
    if (Number.isFinite(num) && num >= 0) r[k] = num;
  }
  return r;
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
  const add = (key, dict) => { if (Object.keys(dict).length) out[key] = dict; };
  add("retention",       collectDict(form.retention));
  add("audience_age",    collectDict(form.audience));
  add("gender",          collectDict(form.gender));
  add("traffic_sources", collectDict(form.traffic));
  add("locations",       rowsToDict(form.locations));
  add("search_queries",  rowsToDict(form.queries));
  return out;
}

/**
 * Performance card for a published post. Shows stored perf immediately, pulls
 * the latest from PostBridge on open (for posts it published), and lets the user
 * hand-enter the metrics PostBridge can't supply — saves, reach, watch time,
 * retention, per-slide retention / photos viewed, audience age, gender, traffic
 * sources, locations and search queries. Several inputs are post-type aware:
 * a VIDEO shows avg-watched %; a SLIDESHOW shows photos-viewed (avg of N) and
 * the slide-number-based per-slide retention.
 *
 * Props:
 *   - post       : the post (reads post.perf, post.post_bridge_post_id, slides, post_type)
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
  const isVideo = isVideoPost(post);
  const slideTotal = Math.max(
    Array.isArray(post?.slides) ? post.slides.length : 0,
    Number(post?.slide_count) || 0,
  );

  // Watch-time / completion fields, post-type aware. VIDEO: avg-watched % +
  // watched-full %. SLIDESHOW: photos viewed (avg of the N slides).
  const extras = [
    { field: "reach",        label: "Reach",         icon: Radio,    step: 1,   fmt: fmtCount },
    { field: "profileViews", label: "Profile views", icon: Eye,      step: 1,   fmt: fmtCount },
    { field: "newFollowers", label: "New followers", icon: UserPlus, step: 1,   fmt: fmtCount },
    { field: "avgWatchTime", label: "Avg watch",     icon: Clock,    step: 0.1, suffix: "s", fmt: fmtSeconds },
    ...(isVideo
      ? [
          { field: "retentionRate",  label: "Retention rate", icon: Gauge, step: 0.1, max: 100, suffix: "%", fmt: fmtPct },
          { field: "completionRate", label: "Watched full",   icon: Gauge, step: 0.1, max: 100, suffix: "%", fmt: fmtPct },
        ]
      : [
          {
            field: "photosViewed", label: "Photos viewed", icon: Images, step: 0.1,
            suffix: slideTotal ? `/ ${slideTotal}` : "",
            fmt: (v) => (slideTotal ? `${round1(v)} / ${slideTotal}` : `${round1(v)}`),
          },
        ]),
  ];

  // On mount AND whenever you navigate to a different post (Next reuses this
  // component across route-param changes), re-seed the display + form from the
  // post's stored perf, then pull the latest from PostBridge. Keyed on post.id
  // so it re-fires per post; fetchedIdRef dedupes StrictMode's double-mount and
  // ignores the parent's perf-only re-renders (same id → no refetch/clobber).
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
  const setObjDim = (dim, items) => setForm((f) => ({ ...f, [dim]: itemsToObj(items) }));
  const setRows = (dim, rows) => setForm((f) => ({ ...f, [dim]: rows }));

  // Ordered retention keys (seconds for video, slides for a carousel) — the
  // curve reads/writes them as a positional array.
  const retKeys = Object.keys(form.retention);

  const core = coreMetrics(perf);
  const extra = extraMetrics(perf);
  const { saveRate, engagementRate } = derivedRates(perf);
  const retention = retentionOf(perf);
  const audience = audienceAgeOf(perf);
  const gender = genderOf(perf);
  const traffic = trafficSourcesOf(perf);
  const locations = locationsOf(perf);
  const queries = searchQueriesOf(perf);
  const updatedAt = lastUpdatedAt(perf);
  const shareUrl = safeHref(perf?.share_url);
  const showExtras = extras.some(({ field }) => extra[field] != null);

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

      {/* More metrics (reach, watch time, retention/avg-watched or photos viewed) */}
      {editing ? (
        <Group title="More metrics" icon={Gauge}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {extras.map(({ field, label, step, max, suffix }) => (
              <Field key={field} label={label}>
                <NumberInput
                  value={form.values[field]}
                  onChange={(v) => setVal(field, v)}
                  step={step}
                  max={max}
                  suffix={suffix}
                />
              </Field>
            ))}
          </div>
        </Group>
      ) : showExtras ? (
        <Reveal title="More metrics" icon={Gauge}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {extras.filter(({ field }) => extra[field] != null).map(({ field, label, icon: Icon, fmt }) => (
              <ReadStat key={field} icon={Icon} label={label} value={fmt(extra[field])} />
            ))}
          </div>
        </Reveal>
      ) : null}

      {/* Retention curve. VIDEO → per second (0:00..duration); SLIDESHOW → per
          slide (slide-number based, not time based). */}
      {editing ? (
        retKeys.length > 0 && (
          <Group title={retentionTitle(post)} icon={BarChart3}>
            <MetricCurveInput
              values={retKeys.map((k) => Number(form.retention[k]) || 0)}
              labels={retKeys.map((k, i) => retentionLabel(post, k, i))}
              onChange={(vals) =>
                setForm((f) => ({
                  ...f,
                  retention: Object.fromEntries(retKeys.map((k, i) => [k, vals[i]])),
                }))
              }
            />
          </Group>
        )
      ) : retention ? (
        <Reveal title={retentionTitle(post)} icon={BarChart3}>
          <div className="space-y-1.5">
            {Object.entries(retention).map(([k, v], i) => (
              <PercentBar key={k} label={retentionLabel(post, k, i)} pct={typeof v === "number" ? v : null} />
            ))}
          </div>
        </Reveal>
      ) : null}

      {/* Gender */}
      {editing ? (
        <Group title="Gender" icon={UserCircle}>
          <MetricBars
            items={GENDER_BUCKETS.map((k) => ({ key: k, value: form.gender[k] }))}
            onChange={(items) => setObjDim("gender", items)}
            balance
          />
        </Group>
      ) : (
        <BreakdownView title="Gender" icon={UserCircle} data={gender} />
      )}

      {/* Audience age */}
      {editing ? (
        <Group title="Audience age" icon={Users}>
          <MetricBars
            items={Object.keys(form.audience).map((k) => ({ key: k, value: form.audience[k] }))}
            onChange={(items) => setObjDim("audience", items)}
            balance
          />
        </Group>
      ) : (
        <BreakdownView title="Audience age" icon={Users} data={audience} />
      )}

      {/* Traffic sources */}
      {editing ? (
        <Group title="Traffic sources" icon={TrendingUp}>
          <MetricBars
            items={TRAFFIC_BUCKETS.map((k) => ({ key: k, value: form.traffic[k] }))}
            onChange={(items) => setObjDim("traffic", items)}
            balance
          />
        </Group>
      ) : (
        <BreakdownView title="Traffic sources" icon={TrendingUp} data={traffic} />
      )}

      {/* Locations (free-form) */}
      {editing ? (
        <Group title="Locations" icon={MapPin}>
          <MetricBars items={form.locations} onChange={(rows) => setRows("locations", rows)} editableKeys keyPlaceholder="Country" keyOptions={countryNames()} />
        </Group>
      ) : (
        <BreakdownView title="Locations" icon={MapPin} data={locations} />
      )}

      {/* Search queries (free-form) */}
      {editing ? (
        <Group title="Search queries" icon={Search}>
          <MetricBars items={form.queries} onChange={(rows) => setRows("queries", rows)} editableKeys keyPlaceholder="Search term" />
        </Group>
      ) : (
        <BreakdownView title="Search queries" icon={Search} data={queries} />
      )}

      {note && <p className="text-[11px] text-muted-foreground">{note}</p>}

      {editing ? (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {pbBacked
            ? "Views, likes, comments and shares are tracked automatically. Add the rest from your post's analytics — saves, watch time, retention, audience, traffic and search — it sharpens what Duct plans next."
            : "Add every metric from your post's analytics — it sharpens what Duct plans next."}
        </p>
      ) : (
        // Persistent nudge: automatic numbers are basic and lag a little, so
        // hand-entered metrics (especially saves) materially improve planning.
        <p className="border-t border-border/50 pt-2.5 text-[11px] leading-relaxed text-muted-foreground">
          Tracked numbers can lag a day or two and only cover the basics.{" "}
          <button type="button" onClick={startEdit} className="font-medium text-primary hover:underline">
            Add saves, retention, audience and traffic
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
      {suffix && <span className="shrink-0 text-[11px] text-muted-foreground">{suffix}</span>}
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

// View-mode breakdown (gender, age, traffic, locations, queries) — sorted-desc
// percent bars. Renders nothing when there's no data.
function BreakdownView({ title, icon, data }) {
  const entries = Object.entries(data || {})
    .filter(([, v]) => typeof v === "number")
    .sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  return (
    <Reveal title={title} icon={icon}>
      <div className="space-y-1.5">
        {entries.map(([k, v]) => <PercentBar key={k} label={k} pct={v} />)}
      </div>
    </Reveal>
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

function PercentBar({ label, pct }) {
  const w = pct == null ? 0 : Math.max(0, Math.min(100, pct));
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 truncate text-[11px] text-muted-foreground" title={label}>{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary/70" style={{ width: `${w}%` }} />
      </div>
      <span className="w-11 shrink-0 text-right text-[11px] font-medium tabular-nums">{fmtPct(pct)}</span>
    </div>
  );
}
