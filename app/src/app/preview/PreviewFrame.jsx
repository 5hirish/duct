"use client";

import { useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";

import { install } from "./inspect";
import { TEXT_SCALES, VISION, VisionFilters, textScalePx, visionFilter } from "./lenses";
import { SCENES } from "./scenes";
import { SURFACES } from "./surfaces";

/**
 * Force a theme for THIS document only.
 *
 * next-themes lives in the root layout and keys off one localStorage entry, so
 * asking it for a theme would change every frame at once — and showing light
 * and dark side by side is most of the point. Setting the class directly on
 * this document is per-document, which is exactly the scope wanted.
 */
function useForcedTheme(theme) {
  useEffect(() => {
    if (!theme) return undefined;
    const root = document.documentElement;
    const dark = theme === "dark";
    root.classList.toggle("dark", dark);
    root.style.colorScheme = dark ? "dark" : "light";
    // next-themes writes the class on mount and on storage events; re-assert
    // after it settles so a late write does not flip this frame.
    const t = setTimeout(() => root.classList.toggle("dark", dark), 0);
    return () => clearTimeout(t);
  }, [theme]);
}

/**
 * Apply the review lenses to this document.
 *
 * The colour filter goes on <html> rather than the scene box so that portalled
 * overlays are simulated too — a dialog renders into <body>, so a filter on the
 * scene wrapper would leave the one surface most worth checking unfiltered. The
 * cost is that a filtered element becomes the containing block for `fixed`
 * descendants; frames are viewport-height, so overlays still land, but a scene
 * long enough to scroll will drag a fixed overlay with it. That is a preview
 * artifact, not a bug in the component.
 */
function useLenses({ vision, text }) {
  useEffect(() => {
    const root = document.documentElement;
    root.style.filter = visionFilter(vision);
    // Type and spacing are in `rem` by house rule, so moving the root size is
    // the whole simulation — nothing else has to know.
    root.style.fontSize = `${textScalePx(text)}px`;
    return () => {
      root.style.filter = "";
      root.style.fontSize = "";
    };
  }, [vision, text]);
}

export default function PreviewFrame() {
  const params = useSearchParams();
  const sceneId = params.get("scene") || "";
  const surfaceId = params.get("surface") || "inline";
  const theme = params.get("theme") || "";
  const inspect = params.get("inspect") || "off";
  const vision = params.get("vision") || "normal";
  const text = params.get("text") || "100";

  useForcedTheme(theme);
  useLenses({ vision, text });

  useEffect(() => {
    const api = install();
    api.overlay(inspect);
    // A manifest, so an agent can ask what exists instead of scraping the DOM.
    window.__preview.scene = sceneId;
    window.__preview.surface = surfaceId;
    window.__preview.lenses = { vision, text, inspect };
    window.__preview.scenes = SCENES.map((s) => ({
      id: s.id,
      group: s.group,
      title: s.title,
      state: s.state || "default",
    }));
    window.__preview.surfaces = SURFACES.map((s) => ({ id: s.id, label: s.label }));
    window.__preview.vision = VISION.map((v) => v.id);
    window.__preview.textScales = TEXT_SCALES.map((t) => t.id);
    window.__preview.ready = true;
  }, [inspect, sceneId, surfaceId, text, vision]);

  const scene = useMemo(() => SCENES.find((s) => s.id === sceneId), [sceneId]);
  const surface = SURFACES.find((s) => s.id === surfaceId) || SURFACES[0];

  if (!scene) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        No scene <code className="font-mono">{sceneId || "(none)"}</code>. Known ids:{" "}
        {SCENES.map((s) => s.id).join(", ")}
      </div>
    );
  }

  return (
    <div
      data-preview-scene={scene.id}
      data-preview-surface={surface.id}
      // `@container` so container queries resolve against this box, while the
      // iframe's own width drives the viewport ones. Both rulers, correct.
      className="@container min-h-dvh bg-background p-4 text-foreground"
      style={{ containerType: "inline-size" }}
    >
      <VisionFilters />
      {surface.host(scene.render(), scene)}
    </div>
  );
}
