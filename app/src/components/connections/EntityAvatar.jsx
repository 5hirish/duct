"use client";

// The small square in front of an entity in the picker.
//
// Search Console properties, Tag Manager containers and GA4 properties all
// look like each other in a list — "daspire.com" and "designsense.ai" are two
// lines of grey text a scanning eye has to actually read. A favicon is the one
// mark that identifies a site before the word does, which is exactly what a
// picker needs and exactly what a generic globe icon would not give.
//
// The icon is fetched from the site's own origin, not from a favicon service.
// The obvious implementation is Google's `s2/favicons`, and it would tell
// Google every domain in a user's Search Console — a list they did not send us
// to have forwarded on. The site's own `/favicon.ico` is a request the browser
// would make anyway if you opened the site, and when it 404s the monogram is
// already there behind it.

import { useEffect, useState } from "react";

/** The site's own icon, or "" for anything that is not a fetchable web page. */
function faviconHref(url) {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return "";
    return `${parsed.origin}/favicon.ico`;
  } catch {
    return "";
  }
}

/**
 * One letter, from the first part of the name that carries meaning.
 *
 * Deliberately one and not two: at 20px a second glyph costs legibility and
 * buys nothing, since this is a recognition aid beside the full name, not an
 * identifier on its own.
 */
function monogram(name) {
  const cleaned = String(name || "")
    .replace(/^[a-z]+:\/\//i, "")
    .replace(/^www\./i, "")
    .trim();
  const first = cleaned.match(/[\p{L}\p{N}]/u);
  return first ? first[0].toUpperCase() : "•";
}

export default function EntityAvatar({ url, name }) {
  const href = faviconHref(url);
  const [broken, setBroken] = useState(false);

  // A new row can reuse this component instance, and a previous row's failed
  // load must not blank out an icon that would have worked.
  useEffect(() => {
    setBroken(false);
  }, [href]);

  if (!href || broken) {
    return (
      <span className="conn-entity-avatar" aria-hidden="true">
        {monogram(name || url)}
      </span>
    );
  }

  return (
    <span className="conn-entity-avatar" aria-hidden="true">
      {/* Plain <img>: these are third-party origins that next/image would have
          to be told about one domain at a time, and the payload is a favicon. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={href} alt="" width={16} height={16} loading="lazy" onError={() => setBroken(true)} />
    </span>
  );
}
