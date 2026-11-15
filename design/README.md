# design/

**Every screen of the app lives on one canvas as an editable board, and a UI change is designed there before it is built.** This folder holds the tools that keep that canvas, and the design system beside it, equal to the app.

```
 As built ──► pick its board ──► copy it ──► design the change ──► build it ──► refresh
 (every screen,  (Core page:      (beside the   (approved on        (the PR      (capture after
  every size)     the app's own    original)     the canvas)         links it)    it ships)
                  markup)
```

## At a glance

- **Duct Prototype** is the canvas. Its *Core* page holds an editable, clickable board per screen; its *As built* page shows every screen at four sizes.
- **Duct Design System** holds the tokens (55 colours in two themes, type, spacing, radii), 30 components with previews and their rules, the logos, mosaic panels and connector marks.
- **Both come from the code.** One command captures the app, one lays out the canvas, one builds the system. Nothing is redrawn by hand, so nothing drifts unseen.
- `storyboard/` and `motion/` are the launch film, unrelated to the above.

## Where they are

| What | Link | What it holds |
| --- | --- | --- |
| Canvas | [Duct Prototype](https://claude.ai/artifact/BBDispmr2B1UYoNR3E9aCK) | 30 editable boards (1440, light), 39 screens and overlays as built |
| Design system | [Duct Design System](https://claude.ai/artifact/Y4DKNzQU96Go4kRx7r9JNt) | tokens, components, assets, the brand book |

Both are private to the maintainer: ask for access. Agents read and publish them with the Artifact tool.

## Design first, then build

1. **Find the screen** on *As built*. It shows the screen at a phone (390), the desktop app's window (1100) and a laptop (1440), and the laptop again in dark.
2. **Start from its board** on *Core*. No board yet? Add the screen to the screen list (Go deeper) and capture it.
3. **Copy the board** beside the original and design the change on the copy. A refresh replaces the originals, never a copy.
4. **Get it approved on the canvas,** then build from the board. The PR links it.
5. **Refresh the canvas** after the change ships, so the next change starts from the truth.

A design is never one frame. The extra width has to show something the phone couldn't, and every size is judged against the page-frame rules in [`app/DESIGN.md`](../app/DESIGN.md), not against "nothing broke".

## A board is the app, not a drawing of it

Each board is the screen's own rendered markup, with the app's own stylesheet and fonts. So it matches the app to within font smoothing, and it reflows the way the app does. Resize one to 390 and it becomes the phone layout; add `dark` to its root and it turns dark. The board check proves both at every size.

Three things are adapted, because a canvas cannot hold them:

- A document in a frame (a brief, a slide) becomes a picture of itself, fixed at its captured size.
- Links go to the matching board, so Play moves through the app.
- A pane scrolled to an answer stays there, pinned to its end, so a narrower board still shows the latest turn.

The screens show the README's story: Solo, a budgeting app, in the week of 8–14 Sep 2026. Every backend answer lives in `scripts/shots/routes/`, one file per area, each shape named after the handler it copies. A screen that comes out empty is a route missing there.

## Refresh after a release

With the app's dev server running (`npm --prefix app run dev`):

1. `node design/tools/capture.mjs`: shoots every screen at every size and writes the boards. About ten minutes.
2. `node design/tools/board-check.mjs --size <1440|1100|390|1440-dark>`, once per size: renders each board at that size and theme beside the app's picture there, and fails on a mean difference over 3.
3. `node design/tools/layout.mjs --from <live canvas.json> --ds <system link>`: lays out the canvas, keeping everything people added.
4. `node design/tools/assets.mjs plan --map <live project/assets.json>`, upload each batch it stages to the canvas's asset store, then `record` and `apply`. The canvas serves only stylesheets, scripts and JSON, so every picture and font has to live in that store.
5. `node design/tools/design-system.mjs`: rebuilds the tokens, the stylesheet and the component previews.
6. Publish both with the Artifact tool. That step is Claude's, not a script's.

**Check it worked:** board-check passes at all four sizes, `assets.mjs apply` finds nothing the canvas cannot load, and the canvas's blue notes carry the new date and commit.

## The design system follows the code

Tokens are read from the app's stylesheets, previews are captured from the app's preview route, and each component's guideline is its row of the canon table in the app's design guide, word for word. The brand book is the one part written by hand, condensed from that guide, which wins wherever the two disagree.

So a token is changed in the code and re-synced, never on the system's page: an edit there changes the canvas's Theme menu, not the app.

## Go deeper

- [`app/DESIGN.md`](../app/DESIGN.md): the rules, with their reasons. [`app/AGENTS.md`](../app/AGENTS.md): sizing, units, `/preview`.
- [`tools/screens.mjs`](tools/screens.mjs): every screen on the canvas and how each is reached. [`tools/components.mjs`](tools/components.mjs): the system's components.
- [`../scripts/shots/`](../scripts/shots/): the story the screens show, shared with the README's pictures and `check:layout`.
- The board format: `artifact-type/reference/format.md` on the canvas itself.

**The one rule, again: design on the canvas first, on a copy of the board that matches the app.**
