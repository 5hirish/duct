# design/

**Every UI change starts from the screen as it ships, at all eight sizes.** Anyone can capture that with this folder's tools. The maintainer also keeps the captures as an editable canvas on Claude, which helps but is never a step a contributor needs.

```
 capture the screen ──► design the change ──► build it ──► capture again ──► PR shows both
 (all eight sizes,      (in code, /preview,    (the app)    (same sizes)      (before, after)
  Playwright only)       or any tool you like)
```

## At a glance

- **The screen list** ([`tools/screens.mjs`](tools/screens.mjs)) names every screen, dialog and sheet and how to open it. CI fails when a page or dialog is missing from it.
- **The capture** (`tools/capture.mjs`) shoots any of them at eight sizes, from a phone to a 4K screen. It needs Playwright and the app's dev server, nothing else: no account, no backend, no keys.
- **The canvas and design system** are the maintainer's Claude-hosted view of the same captures: an editable board per screen, tokens and components. Built from the code, never redrawn by hand.
- `storyboard/` and `motion/` are the launch film, unrelated to the above.

## Show a change at every size

1. Start the app: `npm --prefix app run dev`.
2. Capture the screen before you change it: `node design/tools/capture.mjs <id>` (the id is in `screens.mjs`). Pictures land in `$TMPDIR/duct-design/asbuilt/<id>@<size>.webp`.
3. Design and build the change. The [`/preview`](../app/AGENTS.md) route shows one component in every state.
4. Capture again, and run `npm --prefix app run check:layout`.
5. Attach before and after at 390, 1100 and 1440 to the PR, plus any size the change affects.

The eight sizes: a phone (390), an iPad either way up (820, 1180), the desktop app's window (1100), a laptop (1440, light and dark), a 4K screen at 150% (2560) and at 100% (3840). `SIZES=390,1440 node design/tools/capture.mjs <id>` shoots only the ones named.

A design is never one frame: the extra width has to show something the phone couldn't. Every size is judged against the page frame and the screen review checklist in [`app/DESIGN.md`](../app/DESIGN.md), not against "nothing broke".

## Every screen is in the list

`npm --prefix app run check:parity` fails when a page or a dialog has no entry in [`tools/screens.mjs`](tools/screens.mjs) (`app/scripts/check-screen-coverage.mjs`, with the reason for each deliberate exception). Fixing it needs only code: add the entry (its route, and how to open it) and run the capture on it to see it opens.

The screens show the README's story: Solo, a budgeting app, in the week of 8–14 Sep 2026. Every backend answer lives in `scripts/shots/routes/`, one file per area, each shape named after the handler it copies. A screen that comes out empty is a route missing there.

## The maintainer's canvas

| What | Link | What it holds |
| --- | --- | --- |
| Canvas | [Duct Prototype](https://claude.ai/artifact/BBDispmr2B1UYoNR3E9aCK) | 49 editable boards (1440, light); 50 screens, dialogs and sheets as built at eight sizes |
| Design system | [Duct Design System](https://claude.ai/artifact/Y4DKNzQU96Go4kRx7r9JNt) | tokens, components, assets, the brand book |

Both are private Claude artifacts: they need a Claude account and the maintainer's invite. Agents read and publish them with the Artifact tool. With access, the loop is the one above with a board in the middle:

1. Find the screen on *As built*, then its board on *Core*.
2. Copy the board beside the original and design on the copy. A refresh replaces the originals, never a copy.
3. Build from the approved board, link it in the PR, and refresh the canvas after the change ships.

## A board is the app, not a drawing of it

Each board is the screen's own rendered markup, with the app's own stylesheet and fonts. So it matches the app to within font smoothing, and it reflows the way the app does. Resize one to 390 and it becomes the phone layout; add `dark` to its root and it turns dark. The board check proves both at every size.

Three things are adapted, because a canvas cannot hold them:

- A document in a frame (a brief, a slide) becomes a picture of itself, fixed at its captured size.
- Links go to the matching board, so Play moves through the app.
- A pane scrolled to an answer stays there, pinned to its end, so a narrower board still shows the latest turn.

## Refresh the canvas after a release

With the app's dev server running (`npm --prefix app run dev`):

1. `node design/tools/capture.mjs`: shoots every screen at every size and writes the boards. About ten minutes.
2. `node design/tools/board-check.mjs --size <id>`, once per size in `VARIANTS` (1440, 1440-dark, 1100, 390, 820, 1180, 2560, 3840): renders each board at that size and theme beside the app's picture there, and fails on a mean difference over 3.
3. `node design/tools/layout.mjs --from <live canvas.json> --ds <system link>`: lays out the canvas, keeping everything people added.
4. `node design/tools/assets.mjs plan --map <live project/assets.json>`, upload each batch it stages to the canvas's asset store, then `record` and `apply`. The canvas serves only stylesheets, scripts and JSON, so every picture and font has to live in that store.
5. `node design/tools/design-system.mjs`: rebuilds the tokens, the stylesheet and the component previews.
6. Publish both with the Artifact tool. That step is Claude's, not a script's.

**Check it worked:** board-check passes at all eight sizes, `assets.mjs apply` finds nothing the canvas cannot load, and the canvas's blue notes carry the new date and commit.

## The site on the canvas

The canvas's **Site** page holds getduct.ai's landing pages as boards, built the same way as the app's: each is the page's own markup at 1440, linking the site's own stylesheet, so a board reads as the page and Play moves through the nav. Both captures share [`tools/board.mjs`](tools/board.mjs).

1. Serve the site: `python3 site/dev_server.py --port 8090`.
2. `node design/tools/capture-site.mjs`: every page in its `PAGES` list (or the ids named) to `$TMPDIR/duct-design-site/boards/`. Scroll reveals are shown finished, a video becomes a picture of itself, the icon sprite is inlined, and a page's state attribute on `<body>` (the SEO audit's `data-lm-state`) moves to the board's root.
3. `node design/tools/capture-site.mjs --check`: each board beside its page with a difference image in `check/`, marking ✗ a page over a mean difference of 3. A page whose photos load lazily reads a little high, because the live page has not loaded them yet; read the picture.
4. Upload `boards/img/` to the canvas's asset store, point the boards and `duct-site.css` at the returned `/_blob/` urls, and publish the boards with a merged `project/canvas.json` (boards on the `site` page, a frame at most 8,000px tall).

To compare another branch's copy of a page, serve a worktree of it (inside the repo, under `.worktrees/`) on another port and set `COMPARE=http://localhost:<port>`: its `/connect-agent` is captured as `site-connect-agent-main`, with its own stylesheet. `CHROMIUM=<path>` points Playwright at a browser binary when the site's pinned version is not installed.

## The design system follows the code

Tokens are read from the app's stylesheets, previews are captured from the app's preview route, and each component's guideline is its row of the canon table in the app's design guide, word for word. The brand book is the one part written by hand, condensed from that guide, which wins wherever the two disagree.

So a token is changed in the code and re-synced, never on the system's page: an edit there changes the canvas's Theme menu, not the app.

## Go deeper

- [`app/DESIGN.md`](../app/DESIGN.md): the rules, with their reasons. [`app/AGENTS.md`](../app/AGENTS.md): sizing, units, `/preview`.
- [`tools/screens.mjs`](tools/screens.mjs): every screen and how each is reached. [`tools/components.mjs`](tools/components.mjs): the system's components.
- [`../scripts/shots/`](../scripts/shots/): the story the screens show, shared with the README's pictures and `check:layout`.
- The board format: `artifact-type/reference/format.md` on the canvas itself.

**The one rule, again: start from the screen as it ships, at every size, and show the change at every size.**
