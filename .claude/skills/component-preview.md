---
name: component-preview
description: Render an app/ component in isolation at /preview to inspect layout, states, responsiveness and surfaces (dialog, sheet, alert, corner notice) without signing in or loading the real screen. Use before calling any UI change done.
argument-hint: "<ComponentName> [state or surface to check]"
---

Look at a component on its own, in the real app's CSS, before calling a UI
change done. **Do not** reconstruct its markup in a scratch HTML file, and do
not load the real screen just to see one card.

## When to use

- You changed layout, spacing, alignment, colour or copy in `app/`.
- You need a state the happy path never shows: partial, empty, loading,
  failed, long name, disabled.
- You need to know how something behaves in a dialog, a bottom sheet, an alert
  or a corner notice — or at a narrow container width.

## When *not* to use

Full-app visual review — opening real screens, walking flows, checking a change
in context — is a separate, heavier job. **Do it only when asked**, or when the
change is to a whole screen's composition rather than to a component. In-place
work uses this route.

## The two routes

Dev only (`notFound()` in production), no auth, no backend.

- **`/preview/frame`** — one scene, alone in its own document. **This is the one
  to drive.** Everything is in the URL, so no clicking:

  ```
  /preview/frame?scene=<id>&surface=<id>&theme=dark|light
                &inspect=outline|spacing|grid
                &vision=protanopia|deuteranopia|tritanopia|greyscale
                &text=100|125|150|200
  ```

  Set the browser viewport to the device you care about and go straight there.

- **`/preview`** — the human chooser. Embeds frames as iframes in a
  device × theme matrix, with a "copy frame URL" button on each scene.

Iframes, not resized `<div>`s, because media queries read the **viewport**: a
`<div style="width:390px">` answers the container question and silently gets
`sm:`/`md:`/`dvh` wrong. Each frame also declares `container-type`, so both
rulers are correct at once.

| File | Holds |
|---|---|
| `app/src/app/preview/scenes.jsx` | **the scenes — this is what you edit** |
| `app/src/app/preview/surfaces.jsx` | in place · dialog · sheet · drawer · alert · notification · page · toolbar |
| `app/src/app/preview/devices.js` | phone · iPad ↕↔ · desktop-min · desktop · wide |
| `app/src/app/preview/lenses.jsx` | colour-vision filters · text scales · overlays |
| `app/src/app/preview/TokenSheet.jsx` | the `tokens` scene — the palette, live |
| `app/src/app/preview/inspect.js` | the `window.__preview` API below |
| `app/src/app/preview/PreviewShell.jsx` · `PreviewFrame.jsx` · `page.jsx` | shell, frame, production guard |

## The inspection API

Every frame exposes `window.__preview`. Use it instead of retyping measurement
code into `page.evaluate` — it answers the same question the same way twice,
which is the point.

| Call | Answers |
|---|---|
| `measure(sel)` | box, font px, weight, line-height, colour, for every match |
| `styles(sel, props)` | named computed properties, for asserting a rule |
| `contrast(sel)` | WCAG ratio against the real painted background, with pass/fail |
| `aligned(sel, axis)` | do these share a left rail / centre? exact, not eyeballed |
| `smallTargets()` | interactive targets under the 24×24 floor (WCAG 2.5.8) |
| `unnamed()` | controls with no accessible name, images with no alt |
| `overflowing()` | anything wider than the viewport — the stray-scrollbar cause |
| `typeScale()` | how many distinct size/weight pairs are on screen |
| `tokens()` | every CSS custom property, resolved after the cascade |
| `overlay("outline"\|"spacing"\|"grid"\|"off")` | debug overlays |

`__preview.scenes` and `__preview.surfaces` are the manifest — enumerate what
exists rather than scraping the DOM. `__preview.lenses` reports the conditions
this frame is rendering under.

## Lenses

The third axis. A device changes what the component is; a lens changes who is
looking at it, and that is the axis nothing on the machine simulates by default.

- **`vision=`** — colour-vision simulation, applied as an SVG filter on `<html>`
  so portalled overlays are covered too. The question it answers is the one
  WCAG 1.4.1 asks: does this still parse when the hue difference goes away? A
  green "connected" dot and an amber "partial" one are the same dot under
  `deuteranopia`; the word beside them is what carries the meaning.
- **`text=`** — the reader's text size. The house rule puts type and spacing in
  `rem` so they follow this setting, and the rule is only worth anything if
  someone moves it. 200% is the WCAG 1.4.4 bar; 150% is where dense rows start
  to argue.
- **`inspect=grid`** — the spacing scale drawn, in `rem`, so it stays in phase
  with the layout when the text lens grows it.

## The token sheet

`?scene=tokens` is the palette as the app actually resolves it: every semantic
pair with a live contrast ratio, the colours used as ink on the page background,
the type ladder, the radii. Read from computed style, so it cannot drift from
`tokens.css` and shows the value **after** the cascade — open it in a dark frame
to see the dark half of every token.

Check a new or changed token here before shipping it. On its first render it
caught `--destructive-foreground` missing from the `.dark` block: white on the
lifted coral at 2.89:1, where its three neighbours sat at 7.8–9.9.

## How to use it

1. **Add scenes** to `scenes.jsx` for the states you changed —
   `{ id, group, title, state, note, render }`. Import the real component and
   pass real props; never rebuild its markup.
2. Start the dev server if needed (`npm run dev` in `app/`). On `EMFILE: too
   many open files`, run `ulimit -n 4096` first — the soft limit sits above
   `kern.maxfilesperproc`, which Turbopack's watcher trips. Never run
   `next build` against a `.next` a dev server owns; it kills it.
3. Navigate to the frame URL at the device viewport, then **measure, do not
   squint.** Assert what the guides make checkable: shared rails, equal slots,
   the 24×24 floor, rows that must stay on one line, contrast, and a type
   ladder of three sizes rather than six.
4. Check the states that are not the happy one, and at least one narrow device.
5. **If it still looks wrong and you cannot say why**, open the reference build
   beside it. `app/DESIGN.md` → "Go and look" lists them (shadcn's components,
   blocks, charts and typeset pages — the reference implementation of the
   primitives we vendor). Browse them in a real browser and screenshot: these
   pages are made to be looked at, and the markdown a fetcher returns drops the
   part that matters. Put that screenshot next to your frame of the same
   component. Copy structure, spacing and behaviour; never their tokens.

## Data without a backend

A component that fetches takes an injectable loader with a real default — see
`loadEntities` on `ProjectEntitySelect`. Pass a stub from a scene to render
populated, empty, slow and failed side by side. One optional prop with a sane
default beats a copy of the component's markup that silently stops matching.

## Why it exists

Bugs it caught in its first hour, none of them visible on the screen they ship
on: a connector tile's status row wrapped onto three lines under a long account
name (dot orphaned, storage glyph stranded); a tooltip mounting its own
`TooltipProvider` on top of the app-wide one, so it opened on a different beat
from every other tooltip; and a dialog opening with a tooltip already showing,
because Radix focuses the first focusable descendant and Radix tooltips open on
*any* focus, not just keyboard focus.

Before it existed, "look at it" meant copying a stylesheet next to a
hand-written HTML replica. The first such replica was missing Tailwind's
preflight, measured every box 34px too wide, and sent a correct layout back for
a fix it did not need. A replica is a copy, and copies drift.

## Related

- `app/AGENTS.md` — "Look at it before you call it done", plus the container
  sizing and accessibility rules the scenes are checked against.
- `app/DESIGN.md` — the canon each component is supposed to match, and the
  review checklist to run before calling a screen done.
