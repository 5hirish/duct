// Shared date / number / string formatters.
//
// Every list, card and badge in the app was growing its own `fmtDate`,
// `fmtNum`, `prettify` and `relativeTime`; those copies drifted (some floored
// at "1m ago", some said "just now"; some collapsed `--` runs, some didn't).
// This is the one place they live now. Pure functions, no React, no DOM —
// safe to import from server components and `lib/` modules alike.

// ---------------------------------------------------------------------------
// Dates
// ---------------------------------------------------------------------------

/** Date from an ISO string / Date / epoch ms, or null when it isn't a real date. */
export function toDate(value) {
  if (!value) return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Stable YYYY-MM-DD key in *local* time (calendar bucketing, not serialisation). */
export function dayKey(value) {
  const d = toDate(value);
  if (!d) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * "Mar 15, 2026" — or "Mar 15" with `withYear: false`.
 *
 * `locale` defaults to the viewer's; pass "en" where the copy around it is
 * pinned to English so the date doesn't read half-translated.
 */
export function formatDate(value, { withYear = true, locale, fallback = "" } = {}) {
  const d = toDate(value);
  if (!d) return fallback;
  return d.toLocaleDateString(locale, {
    month: "short",
    day: "numeric",
    ...(withYear ? { year: "numeric" } : {}),
  });
}

/** "3:04 PM". */
export function formatTime(value, { locale, fallback = "" } = {}) {
  const d = toDate(value);
  if (!d) return fallback;
  return d.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

/**
 * "just now" / "5m ago" / "3h ago" / "2d ago" for past timestamps.
 *
 * `fallbackAfterDays` switches to an absolute date once the age passes that
 * many days — past a week "9d ago" stops meaning anything.
 */
export function relativeTime(value, { fallbackAfterDays = 0, locale } = {}) {
  const d = toDate(value);
  if (!d) return "";
  const seconds = Math.max(0, (Date.now() - d.getTime()) / 1000);
  const days = seconds / 86400;
  if (fallbackAfterDays > 0 && days >= fallbackAfterDays) {
    return formatDate(d, { locale });
  }
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(days)}d ago`;
}

/** "today" / "in 6 days" / "3 days ago" — day granularity, and it handles the future. */
export function relativeDays(value) {
  const d = toDate(value);
  if (!d) return "";
  const days = Math.round((d.getTime() - Date.now()) / 86_400_000);
  if (days === 0) return "today";
  const n = Math.abs(days);
  const unit = `${n} day${n === 1 ? "" : "s"}`;
  return days > 0 ? `in ${unit}` : `${unit} ago`;
}

// ---------------------------------------------------------------------------
// Numbers
// ---------------------------------------------------------------------------

/** Thousands-separated, with a dash for anything that isn't a number. */
export function formatNumber(value, { fallback = "—", locale } = {}) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString(locale)
    : fallback;
}

/** "938" / "1.2k" / "3M" — for metric chips where width is tight. */
export function compactNumber(value) {
  const v = Number(value) || 0;
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(v % 1_000_000 ? 1 : 0)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(v % 1_000 ? 1 : 0)}k`;
  return String(v);
}

// ---------------------------------------------------------------------------
// Strings
// ---------------------------------------------------------------------------

/** `face_shape` / `google-ads` -> "Face Shape" / "Google Ads". */
export function titleCase(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

/**
 * Display title for an insight slug: drops the `local-` prefix and the trailing
 * `-1712...` disambiguator the generator appends, then title-cases the rest.
 */
export function formatTitle(slug) {
  return titleCase(String(slug || "").replace(/^local-/, "").replace(/[-_]\d+$/, ""));
}

/** Sentence case for a single lowercase token: `high` -> "High". */
export function capitalize(value) {
  const s = String(value || "");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "SK" from a name, "sh" -> "SH" from an email — avatar fallbacks. */
export function initials(nameOrEmail) {
  const source = String(nameOrEmail || "?").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return source.slice(0, 2).toUpperCase();
}
