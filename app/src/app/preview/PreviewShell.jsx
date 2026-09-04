"use client";

// Component isolation — mount one thing, in the real app's CSS, on the surface
// and device you want to look at it, under the condition you want to see it in.
//
// Two modes, because there are two jobs and they were being confused:
//
//   Working  — the workbench. Scenes for whatever is being built right now.
//              Ad hoc by design; the list is short and skewed to the last thing
//              touched, and that is correct for what it is for.
//   Canon    — the design system. One entry per rule in DESIGN.md's canon
//              table, with the rule beside a live example of it.
//
// The rules are PARSED from DESIGN.md (see canon.js), never retyped here. This
// repo has been bitten twice by a second copy of a rule, and a catalogue that
// restated the canon would be the third — with the added insult that the copy
// would be the one people look at.
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

import { CATALOGUE_BY_ID } from "./catalogue";
import { DEFAULT_DEVICES, DEVICES } from "./devices";
import { OVERLAYS, TEXT_SCALES, VISION } from "./lenses";
import { SCENES } from "./scenes";
import { SURFACES } from "./surfaces";

const MODES = [
  { id: "working", label: "Working" },
  { id: "canon", label: "Canon" },
];

const THEME_MODES = [
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
  { id: "both", label: "Both" },
];

// Surfaces whose content is `position: fixed` and sized to the viewport. The
// catalogue crops a frame to its specimen, and measuring one of these would
// find a near-empty box and crop the overlay away.
const VIEWPORT_SURFACES = new Set(["dialog", "sheet", "alert", "drawer", "toast"]);

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

/**
 * One iframe, optionally cropped to its content.
 *
 * The iframe keeps the device's real height whatever happens here — only the
 * window onto it shrinks. That distinction is load-bearing: `dvh`, sticky
 * offsets and viewport media queries all still resolve against the device, so
 * what is measured inside a cropped frame is the same as in a full one.
 *
 * Without this the catalogue was thirteen rules at full device height, each
 * showing a sixty-pixel specimen against five hundred pixels of empty
 * background — the design system as a scroll test.
 */
function Frame({ src, label, theme, device, fit }) {
  const [contentH, setContentH] = useState(null);
  const scale = Math.min(1, 560 / device.w);

  function measure(event) {
    if (!fit) return;
    const el = event.currentTarget.contentDocument?.querySelector("[data-preview-content]");
    if (!el) return;
    // `bottom` rather than `height`: the scene box pads above the specimen, and
    // cropping to the height alone would clip its own last row.
    setContentH(Math.max(96, Math.ceil(el.getBoundingClientRect().bottom) + 16));
  }

  const boxH = Math.min(device.h, fit && contentH ? contentH : device.h);

  return (
    <figure className="m-0">
      <figcaption className="mb-1 text-xs text-muted-foreground">
        {device.label} · {device.w}×{device.h} · {theme}
      </figcaption>
      {/* Scaled down so a 1680px device still fits on screen. `transform` only
          — the iframe's own layout viewport stays the real width, so what is
          measured inside is the device, not the thumbnail. */}
      <div
        style={{
          width: Math.min(device.w, 560),
          height: boxH * scale,
          overflow: "hidden",
          borderRadius: 12,
        }}
        className="border"
      >
        <iframe
          title={label}
          src={src}
          width={device.w}
          height={device.h}
          onLoad={measure}
          style={{ border: 0, transform: `scale(${scale})`, transformOrigin: "top left" }}
        />
      </div>
    </figure>
  );
}

/**
 * The inline markdown the canon rules actually use — `code` and **bold** — and
 * nothing else.
 *
 * Deliberately not react-markdown: the chain in `AGENTS.md` is for agent output
 * that can contain anything. This is one table cell from a file in the repo,
 * and pulling a renderer plus a sanitiser in to bold two words would be the
 * kind of dependency the same file tells you not to add.
 */
function CanonText({ children }) {
  const parts = String(children || "").split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={i} className="rounded bg-muted px-1 py-0.5 font-mono">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={i} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}

/** A rule as DESIGN.md states it. "—" means the row has nothing to retire. */
function Rule({ row }) {
  const retire = row.retire && row.retire !== "—" ? row.retire : "";
  return (
    <div className="mb-3 flex max-w-[68ch] flex-col gap-1.5 text-xs leading-relaxed">
      <p className="text-muted-foreground">
        <span className="font-semibold text-foreground">Canonical. </span>
        <CanonText>{row.canonical}</CanonText>
      </p>
      {retire && (
        <p className="text-muted-foreground">
          <span className="font-semibold text-destructive">Retire on touch. </span>
          <CanonText>{retire}</CanonText>
        </p>
      )}
    </div>
  );
}

export default function PreviewShell({ canon = [] }) {
  const [mode, setMode] = useState("working");
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

  // A canon row and its example are joined by id. A row with no example is a
  // GAP and is listed as one — the alternative is a catalogue that looks
  // complete because the missing entries are invisible.
  const canonRows = useMemo(
    () => canon.map((row) => ({ ...row, example: CATALOGUE_BY_ID.get(row.id) || null })),
    [canon],
  );
  const covered = canonRows.filter((r) => r.example).length;

  const working = group === "all" ? SCENES : SCENES.filter((s) => s.group === group);
  const devices = DEVICES.filter((d) => deviceIds.includes(d.id));
  const themes = themeMode === "both" ? ["light", "dark"] : [themeMode];
  const lens = { inspect, vision, text };
  const isCanon = mode === "canon";

  function toggleDevice(id) {
    setDeviceIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function copyUrl(id) {
    const url = frameUrl({ scene: id, surface, theme: themes[0], ...lens });
    navigator.clipboard?.writeText(new URL(url, location.origin).href);
    setCopied(id);
    setTimeout(() => setCopied(""), 1500);
  }

  /** The device × theme matrix for one scene id. */
  function Frames({ id, title }) {
    // Canon specimens are small and there are thirteen of them, so their frames
    // crop to the content. Working scenes keep the full device, where the empty
    // space below a component is part of what is being judged.
    const fit = isCanon && !VIEWPORT_SURFACES.has(surface);
    return (
      <div className="flex flex-wrap gap-4">
        {devices.map((d) =>
          themes.map((theme) => (
            <Frame
              key={`${d.id}-${theme}`}
              src={frameUrl({ scene: id, surface, theme, ...lens })}
              label={`${title} — ${d.label} — ${theme}`}
              theme={theme}
              device={d}
              fit={fit}
            />
          )),
        )}
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="sticky top-0 z-40 flex flex-col gap-3 border-b bg-background/95 px-5 py-3 backdrop-blur">
        {/* What am I looking at. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="text-sm font-semibold">Preview</span>
          <span className="text-xs text-muted-foreground">
            {isCanon
              ? `${canonRows.length} rules · ${covered} with examples · ${
                  canonRows.length - covered
                } gaps`
              : `dev only · ${working.length} scenes`}{" "}
            · {devices.length || "no"} device{devices.length === 1 ? "" : "s"}
          </span>

          <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2">
            <Picker id="pv-mode" label="Mode" value={mode} onChange={setMode} options={MODES} />
            {!isCanon && (
              <Picker
                id="pv-component"
                label="Component"
                value={group}
                onChange={setGroup}
                options={groups}
              />
            )}
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

        {isCanon && canonRows.length === 0 && (
          <p className="max-w-[68ch] text-sm text-muted-foreground">
            No rules parsed from <code className="font-mono">DESIGN.md</code>. The canon table
            moved or its heading changed — see <code className="font-mono">canon.js</code>.
          </p>
        )}

        {isCanon
          ? canonRows.map((row) => (
              <section key={row.id}>
                <header className="mb-2 flex flex-wrap items-baseline gap-2">
                  <h2 className="text-sm font-semibold tracking-tight">{row.job}</h2>
                  {row.example ? (
                    <button
                      type="button"
                      className="text-xs text-muted-foreground underline underline-offset-2"
                      onClick={() => copyUrl(row.id)}
                    >
                      {copied === row.id ? "copied" : "copy frame URL"}
                    </button>
                  ) : (
                    <span className="rounded-full border border-dashed px-1.5 text-xs text-muted-foreground">
                      no example yet
                    </span>
                  )}
                </header>

                <Rule row={row} />

                {row.example ? (
                  <Frames id={row.id} title={row.job} />
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Add one to <code className="font-mono">preview/catalogue.jsx</code>, keyed by
                    this row&rsquo;s job name.
                  </p>
                )}
              </section>
            ))
          : working.map((scene) => (
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
                    onClick={() => copyUrl(scene.id)}
                  >
                    {copied === scene.id ? "copied" : "copy frame URL"}
                  </button>
                  {scene.note && (
                    <p className="basis-full text-xs leading-relaxed text-muted-foreground">
                      {scene.note}
                    </p>
                  )}
                </header>

                <Frames id={scene.id} title={scene.title} />
              </section>
            ))}
      </main>
    </div>
  );
}
