"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Slugify a string. Default separator is "-" (URL-style); pass "_" for
 * underscore keys (e.g. content pillar ids like "face_shape").
 */
export function slugify(value, sep = "-") {
  const cleaned = String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, sep);
  const esc = sep.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return cleaned.replace(new RegExp(`^${esc}+|${esc}+$`, "g"), "");
}

/**
 * Reusable slug field that auto-generates from a name/title and stops doing so
 * once the user edits the slug by hand.
 *
 *   const { slug, setSlug, reset, syncFromName } = useAutoSlug("", "-");
 *   <Input value={name} onChange={...} onBlur={() => syncFromName(name)} />
 *   <Input value={slug} onChange={(e) => setSlug(e.target.value)} />
 *   // when loading an existing record: reset(record.slug)
 *
 * - `syncFromName(name)` fills the slug from the name, but only while the slug
 *   hasn't been manually touched (call it on the name field's onBlur).
 * - `setSlug` marks the slug as manually touched (use for the slug input).
 * - `reset(value)` seeds the slug and treats a non-empty value as touched.
 */
export function useAutoSlug(initial = "", sep = "-") {
  const [slug, setSlugState] = useState(initial);
  const touched = useRef(Boolean(initial));

  const setSlug = useCallback((value) => {
    touched.current = true;
    setSlugState(value);
  }, []);

  const reset = useCallback((value = "") => {
    touched.current = Boolean(value);
    setSlugState(value);
  }, []);

  const syncFromName = useCallback((name) => {
    if (touched.current) return;
    const next = slugify(name, sep);
    if (next) setSlugState(next);
  }, [sep]);

  return { slug, setSlug, reset, syncFromName };
}
