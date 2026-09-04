"use client";

// Component isolation — mount one thing, in the real app's CSS, on the surface
// and device you want to look at it, under the condition you want to see it in.
//
// Every scene renders in an IFRAME pointing at /preview/frame. That is the only
// honest way to show a device: media queries read the viewport, and a resized
// <div> is not one, so a `<div style="width:390px">` answers the container
// question and quietly gets `sm:`/`md:`/`dvh` wrong. The iframe also gives each
// frame its own document, which is what lets light and dark sit side by side.
//
// The alternative this replaced was reconstructing a component's markup by hand
// in a scratch HTML file next to a copy of its stylesheet. That is a replica,
// and replicas lie: the first one was missing Tailwind's preflight, measured
// every box 34px too wide, and sent a correct layout back for a fix it did not
// need.
//
// Deliberately not Storybook — a route in an app that already builds inherits
// globals.css, the tokens, the fonts and the providers for free, adds no
// dependency and no second build, and 404s in production.
//
// The chrome is built from the app's own primitives, and that is not decoration.
// This toolbar first shipped with native <select>s, and a native <select> draws
// its option list in the OS, not in the page: system font, system metrics,
// system light chrome over a dark app, ignoring every class on the element. A
// harness whose job is judging our components was the one screen in the app not
// using them. Use `ui/*` here, or the tool misrepresents the thing it is for.

import { useMemo, useState } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { DEFAULT_DEVICES, DEVICES } from "./devices";
import { OVERLAYS, TEXT_SCALES, VISION } from "./lenses";
import { SCENES } from "./scenes";
import { SURFACES } from "./surfaces";

const THEME_MODES = [
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
  { id: "both", label: "Both" },
];

function frameUrl({ scene, surface, theme, inspect, vision, text }) {
  const p = new URLSearchParams({ scene, surface, theme });
  // Only non-default lenses land in the URL, so a copied link says what is
  // unusual about it rather than restating the defaults.
  if (inspect && inspect !== "off") p.set("inspect", inspect);
  if (vision && vision !== "normal") p.set("vision", vision);
  if (text && text !== "100") p.set("text", text);
  return `/preview/frame?${p}`;
}

/**
 * One labelled dropdown.
 *
 * A Radix trigger is a <button>, and a <button> is not a labelable element — so
 * wrapping it in a <label> would give it no accessible name and no click
 * target, only the appearance of both. `aria-labelledby` naming the caption AND
 * the trigger is the documented pattern, and reads as "Surface, Dialog":
 * what it is, then what it says.
 */
function Picker({ id, label, value, onChange, options }) {
  return (
    <div className="flex items-center gap-2">
      <span id={`${id}-label`} className="text-xs whitespace-nowrap text-muted-foreground">
        {label}
      </span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} size="sm" aria-labelledby={`${id}-label ${id}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.id} value={o.id}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default function PreviewShell() {
  const [group, setGroup] = useState("all");
  const [surface, setSurface] = useState("inline");
  const [themeMode, setThemeMode] = useState("dark");
  const [inspect, setInspect] = useState("off");
  const [vision, setVision] = useState("normal");
  const [text, setText] = useState("100");
  const [deviceIds, setDeviceIds] = useState(DEFAULT_DEVICES);
  const [copied, setCopied] = useState("");

  // "all" rather than "" because Radix reserves the empty string: an empty
  // value means "no selection", so an <SelectItem value=""> can never be picked
  // and the trigger would sit permanently blank.
  const groups = useMemo(
    () => [
      { id: "all", label: "All" },
      ...[...new Set(SCENES.map((s) => s.group))].map((g) => ({ id: g, label: g })),
    ],
    [],
  );

  const shown = group === "all" ? SCENES : SCENES.filter((s) => s.group === group);
  const devices = DEVICES.filter((d) => deviceIds.includes(d.id));
  const themes = themeMode === "both" ? ["light", "dark"] : [themeMode];
  const lens = { inspect, vision, text };

  function toggleDevice(id) {
    setDeviceIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="sticky top-0 z-40 flex flex-col gap-3 border-b bg-background/95 px-5 py-3 backdrop-blur">
        {/* What am I looking at. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="text-sm font-semibold">Preview</span>
          <span className="text-xs text-muted-foreground">
            dev only · {shown.length} scenes · {devices.length || "no"} device
            {devices.length === 1 ? "" : "s"}
          </span>

          <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2">
            <Picker id="pv-component" label="Component" value={group} onChange={setGroup} options={groups} />
            <Picker id="pv-surface" label="Surface" value={surface} onChange={setSurface} options={SURFACES} />
            <Picker id="pv-theme" label="Theme" value={themeMode} onChange={setThemeMode} options={THEME_MODES} />
          </div>
        </div>

        {/* How am I looking at it. Devices change what the component is; lenses
            change who is looking. Same row, because both are review axes. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Devices">
            {DEVICES.map((d) => (
              <button
                key={d.id}
                type="button"
                title={`${d.w}×${d.h} — ${d.note}`}
                onClick={() => toggleDevice(d.id)}
                aria-pressed={deviceIds.includes(d.id)}
                className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                  deviceIds.includes(d.id)
                    ? "border-transparent bg-secondary text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {d.label}
                <span className="ml-1.5 opacity-60">{d.w}</span>
              </button>
            ))}
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2">
            <Picker id="pv-vision" label="Vision" value={vision} onChange={setVision} options={VISION} />
            <Picker id="pv-text" label="Text" value={text} onChange={setText} options={TEXT_SCALES} />
            <Picker id="pv-inspect" label="Overlay" value={inspect} onChange={setInspect} options={OVERLAYS} />
          </div>
        </div>
      </header>

      <main className="flex flex-col gap-10 p-5">
        {devices.length === 0 && (
          <p className="text-sm text-muted-foreground">Pick at least one device.</p>
        )}

        {shown.map((scene) => (
          <section key={scene.id}>
            <header className="mb-2 flex flex-wrap items-baseline gap-2">
              <h2 className="text-sm font-semibold tracking-tight">{scene.title}</h2>
              <span className="text-xs text-muted-foreground">{scene.group}</span>
              {scene.state && (
                <span className="rounded-full border px-1.5 text-xs text-muted-foreground">
                  {scene.state}
                </span>
              )}
              <button
                type="button"
                className="text-xs text-muted-foreground underline underline-offset-2"
                onClick={() => {
                  const url = frameUrl({ scene: scene.id, surface, theme: themes[0], ...lens });
                  navigator.clipboard?.writeText(new URL(url, location.origin).href);
                  setCopied(scene.id);
                  setTimeout(() => setCopied(""), 1500);
                }}
              >
                {copied === scene.id ? "copied" : "copy frame URL"}
              </button>
              {scene.note && (
                <p className="basis-full text-xs leading-relaxed text-muted-foreground">
                  {scene.note}
                </p>
              )}
            </header>

            <div className="flex flex-wrap gap-4">
              {devices.map((d) =>
                themes.map((theme) => (
                  <figure key={`${d.id}-${theme}`} className="m-0">
                    <figcaption className="mb-1 text-xs text-muted-foreground">
                      {d.label} · {d.w}×{d.h} · {theme}
                    </figcaption>
                    {/* Scaled down so a 1680px device still fits on screen.
                        `transform` only — the iframe's own layout viewport
                        stays the real width, so what is measured inside is
                        the device, not the thumbnail. */}
                    <div
                      style={{
                        width: Math.min(d.w, 560),
                        height: Math.min(d.h, 560),
                        overflow: "hidden",
                        borderRadius: 12,
                      }}
                      className="border"
                    >
                      <iframe
                        title={`${scene.title} — ${d.label} — ${theme}`}
                        src={frameUrl({ scene: scene.id, surface, theme, ...lens })}
                        width={d.w}
                        height={d.h}
                        style={{
                          border: 0,
                          transform: `scale(${Math.min(1, 560 / d.w)})`,
                          transformOrigin: "top left",
                        }}
                      />
                    </div>
                  </figure>
                )),
              )}
            </div>
          </section>
        ))}
      </main>
    </div>
  );
}
