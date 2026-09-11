---
name: mosaic-panel
description: Generate a Roman mosaic threshold panel for an empty state, error state, 404 or onboarding screen, and ship it as a WebP the app can load. Use when a surface needs illustration rather than another icon.
argument-hint: "<state the panel is for, e.g. 'connector rate-limited'>"
---

Duct's illustrations are square Roman mosaic panels — the kind set into a
doorway threshold, a street, a floor. The reasoning is in
[`site/about.html`](../../../site/about.html): *ductus* is a leading, and Rome's
aqueducts never made a drop of water, they carried it. The illustrations draw
the carrying, not the empire — engineering Rome, never togas, laurels or
centurions.

A threshold mosaic greets whoever arrives, which is exactly what an empty or
error state does. That is why the form fits, and it is also the placement rule:
**panels go where someone arrives**, never mid-flow.

## Before generating anything

**Does this state need a panel at all?** Most do not. `app/DESIGN.md` holds the
placement rules — the short version is that panels are for rare, high-emotion
arrivals (first run, a break, a dead end) and small frequent empty states get a
lucide icon instead. `DeskDayOne` is the model of an empty state that is better
off with information than art.

**Does the state map to a real thing in a Roman water system?** A dry channel, a
broken span, sinter choking a pipe, an empty basin, a milestone, a threshold. If
you cannot name the object, the state is probably not distinct enough to earn a
panel — reuse an existing one.

## What already exists

Do not duplicate these. Masters in `app/art-src/mosaic/`, shipped WebP
in `app/public/art/mosaic/`.

| Slug | State | Subject | Inscription |
|---|---|---|---|
| `fons` | the signed-out front door | spring-head basin spilling into the first channel | `FONS` |
| `salve` | first run, onboarding | open arched doorway, water beyond | `SALVE` |
| `nihil` | empty — no results yet | dry basin, two pigeons, one peering in | `NIHIL` |
| `fractum` | error, connection failed | aqueduct with one arch gone, water stops | — |
| `cdiv` | 404 | road ends at a milestone | `CDIV` |
| `cave-canem` | 403, no access | the Pompeii guard dog | `CAVE·CANEM` |
| `otium` | all caught up | water running full, pigeon asleep | `OTIVM` |

`fons` and `salve` are both arrival panels because the arrival has two steps:
the front door is the spring, `/start` is the threshold you cross a click later.
That is the bar for a second panel of the same kind — a distinct moment in one
flow, not a second surface with the same feeling.

Unbuilt, if a surface ever needs them: sinter-choked channel (rate limited),
the *asaroton* unswept floor (no results left), `FESTINA·LENTE` (a long check
running — Augustus's motto, "make haste slowly").

## The rules

**Three zones.** Every panel has them, and getting the contrast relationship
wrong is the one failure that kills a panel outright:

1. **Border** — one Greek key meander, two tiles thick, near-black on cream.
   Identical on every panel. It is what makes the thing read as a mosaic in the
   first 200ms.
2. **Ground** — fine, regular, *low contrast*. Texture, never information. A
   ground drawn at the same contrast as the subject is why the first attempt at
   this style was unusable.
3. **Subject** — coarse tiles, noticeably bigger than the ground, high
   contrast, filling roughly 60% of the inner field.

**Cover the word: can you still tell which state this is?** If not, the picture
failed and no inscription will rescue it. The picture carries the concept; the
inscription is a caption in stone.

**Six stones, fixed jobs.** Not a palette to be creative with — the fixed jobs
are what make separately-generated panels look like one set.

| Stone | Job |
|---|---|
| Travertine cream | the ground, most tiles |
| Warm grey limestone | second neutral |
| Golden ochre limestone | structure — arches, paving, piers |
| Near-black basalt | outlines, letters, the border |
| Blue-green glass paste | **water only** — nothing else is ever blue |
| Terracotta `#FF5C00` | **consequence only** — the break, the blockage. Under 8% of tiles |

The water rule does the most work: blue is water, water is data. Dry channel, no
blue. Connected, blue enters. Broken, blue stops. One glance reads the state.

**Lettering.** Capitals only — lowercase did not exist. `V` never `U`, no `J`,
no `W`, no punctuation. No spaces between words: the separator is an
**interpunct, and the interpunct is one terracotta tessera** — the same orange
dot as the `duct` wordmark. Letters sit *on an object in the scene* (a milestone
shaft, a basin face) and stay under a tenth of the panel height; a foot band is
legal only for two-word inscriptions like `CAVE·CANEM`, which is the authentic
Pompeii layout. One word, two at most.

The Latin never carries meaning. It cannot be translated, a screen reader gets
nothing from it, and it does not scale with browser text settings — so the panel
is always `aria-hidden` and the real heading is real HTML text. `CDIV` above,
"That page doesn't exist" below.

**Flat, side-on, orthographic.** No perspective, no gradients, no drop shadows.
One exception: **a vessel may open** — you cannot show *empty* from the side, so
tip the bowl toward the viewer. The Capitoline Doves mosaic does the same.

## Generating one

Use `mcp__gemini-image-generation__generate_image` with
`model: gemini-3-pro-image-preview`, `aspect_ratio: 1:1`, `image_size: 2K`.
These models take no seed, so a regenerated panel is a *different* panel — which
is why masters are committed rather than regenerated.

Build the prompt from this template. The style block is fixed; only the subject
and inscription paragraphs change.

```
A square ancient Roman mosaic floor panel (opus tessellatum), the kind set into
a doorway threshold. The whole square is filled edge to edge with small square
hand-cut stone tesserae — a complete tile field, no empty space anywhere.

Three zones:
1. Border on all four edges: one band of classic Greek key / meander pattern in
   near-black basalt tesserae on cream, two tiles thick.
2. A QUIET ground: pale travertine cream tesserae in fine regular rows, very low
   contrast, near-uniform texture.
3. The subject in BOLD COARSE LARGE tesserae, much bigger tiles than the ground,
   high contrast. The subject must FILL roughly 60% of the inner field — do not
   leave large empty areas of ground.

MAIN SUBJECT, understandable with no words: <...>

SMALL INSCRIPTION: on <object in the scene> only, <n> SMALL capital letters
reading exactly "<WORD>", built from individual chunky square tesserae —
blocky, squared-off, stencil-like, made of tiles. Absolutely NOT smooth painted
serif type, NOT elegant carved letterforms. Less than one tenth of the panel
height. No other text anywhere.

Materials, six stones: pale travertine cream (ground), warm grey limestone,
golden ochre limestone (structure), near-black basalt (outlines, letters,
border), blue-green glass paste (<water, or: NO blue anywhere at all>),
terracotta orange #FF5C00 only <where the consequence is>, under 8% of tiles.

Strict rules: completely flat lighting, no gradients, no glow, no drop shadows,
no perspective — flat side-on orthographic elevation. Perfect square 1:1. Clean
and new, not worn, aged or cracked. No people.
```

Two failure modes to expect and re-roll on: the model drifts to smooth **serif**
letterforms instead of tessellated ones, and it leaves **large dead areas** of
ground when the subject is not explicitly told to fill the field. Both are worth
one more pass; everything else is usually right first time.

## Shipping it

```bash
# 1. Save the 2K generation as a 1024px master (the source of truth)
python3 - <<'PY'
from PIL import Image
Image.open("<generated>.jpeg").convert("RGB").resize((1024, 1024), Image.LANCZOS) \
     .save("app/art-src/mosaic/<slug>.jpg", "JPEG", quality=88, optimize=True)
PY

# 2. Re-encode every master into the WebP the app loads
python3 scripts/build_mosaic_assets.py
```

`scripts/build_mosaic_assets.py` is the only thing that writes
`app/public/art/mosaic/` — never hand-edit a file in there. `--check` re-encodes
to a temp dir and fails if a committed output has drifted from its master.

Panels render at 320px at most, so the shipped asset is 640px WebP, about 115KB
— the tile texture is high-frequency and does not compress further without
visible damage (q60 saves 28% and smears the tesserae). One panel loads per
page, and it loads eagerly: on these surfaces the panel is the above-the-fold
hero, so deferring it only delays the thing that makes the page feel handled.

Render it through `app/src/components/MosaicPanel.jsx` rather than a bare
`<img>` — it owns the `aria-hidden`, the 240px floor and the slug list, and it
carries explicit width/height so the panel still sizes correctly in
`global-error.js`, which replaces the root layout and may render without the
app's CSS.

## Verifying before you call it done

1. Squint at it at 240px. Border, subject and inscription all still legible?
2. Cover the inscription. Does the picture still say which state this is?
3. Count the orange. Over 8% means it competes with the CTA beside it.
4. Anything blue that is not water? Fix it — the water rule is load-bearing
   across the whole set.
5. Rendered on the real surface via the `component-preview` skill, not just
   viewed as a file.
