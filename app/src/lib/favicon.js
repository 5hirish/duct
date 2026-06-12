"use client";

/** Extract a clean hostname from a possibly schemeless URL. Returns "" on failure. */
export function safeHostname(url) {
  if (!url) return "";
  try {
    const normalized = /^https?:\/\//i.test(url) ? url : `https://${url}`;
    return new URL(normalized).hostname;
  } catch {
    return "";
  }
}

/** Google favicon service URL for a site, or "" when no host can be resolved. */
export function faviconUrl(url, size = 64) {
  const host = safeHostname(url);
  if (!host) return "";
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=${size}`;
}
