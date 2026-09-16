# Let the product do the talking

**Author:** Shirish Kadam · **Date:** 2026-09-16

The landing page was written for a commercial product that sent a weekly brief
to your inbox. Duct is now an open-source agent that reads across twelve tools,
acts with your approval, and remembers. The page shows none of that: 1,134
words, zero screenshots, zero video, and a hero "brief" that is hand-written
HTML pretending to be the product.

**Scope** site/ (static, no build) · **Method** side-by-side inspection of
openseo.so and getduct.ai in Playwright, DOM and stylesheet audit of both ·
**Status** plan only, nothing changed

---

## What OpenSEO actually does

The "motion graphics" on openseo.so are one asset. Everything else is still.

| Measured | openseo.so | getduct.ai |
|---|---|---|
| Visible words | 540 | 1,134 |
| Page height at 1280 | 4,422 px | 7,715 px |
| Product shown | 56 s screen recording, `demo.mp4` 1280×966, `autoplay muted loop playsinline`, `preload=metadata`, `poster=demo-poster.webp`, inside a browser mockup | none; a CSS mock of a brief card |
| Animation libraries | none; 0 CSS animations on the page, 21 hover transitions | none; `.reveal` rise + hover lift |
| Scripts | one 1st-party file + analytics | four 1st-party files |
| Open-source signals | GitHub star count in the nav, "100% open source" section, "Star on GitHub" | "GitHub" link in the nav, "Open-source" twice in body copy |
| Social proof | 3 quotes with names, Product Hunt badge | a stats band with unverifiable numbers (`9+`, `~4h`, `10min`, `0`) |

Their section order: hero (text only, one CTA, "no credit card") → agent/MCP
with a terminal mock → testimonials → open source → **the demo video** →
8 feature tiles → newsletter → footer taxonomy.

The lesson is not "add motion". It is: say less, show the real product once,
in motion, and let the rest be tiles.

## Tooling: what makes the video

Not a screen recording. A motion-graphics piece, the kind a launch video is:
type beats, UI that assembles on screen, data that animates, a cursor that
means something. The site has no build step and no runtime dependencies
(`site/AGENTS.md`), so the tool runs offline and ships a file.

**Remotion.** React compositions, one frame per render call, rendered to
mp4/webm by headless Chromium. It is the right tool here for three reasons
that are specific to this repo, not generic:

1. **The product is React + Tailwind + the same tokens.** The compositions
   can import `app/src/components/ui/*` (Badge, Button, Card, the review
   card, the status pills) and the token sheet, and animate *real* UI states
   fed by the Kestrel story fixtures. The video shows the product without
   recording it, and it cannot drift from the product the way a designer's
   mock does.
2. **An agent writes it.** Remotion is code; springs, sequences and
   transitions are functions of the frame number. The
   `remotion-best-practices` skill is already installed, with rules for
   timing, text animation, transitions, charts and Tailwind.
3. **One source, every cut.** The same compositions render the 16:10 hero
   loop, four 8-second feature loops for the tiles, a 9:16 vertical for
   TikTok and LinkedIn, and a 16:9 with music for YouTube and Product Hunt.
   `calculateMetadata` handles the sizes; nothing is redrawn.

It lives in `scripts/motion/` as its own package with its own `node_modules`,
never in `site/`. Renders are committed to `site/assets/media/` (a 2–3 MB mp4
per re-render is acceptable; re-render rarely, not on every tweak). Licence:
free for companies of up to three people; check the count before the first
render.

**Considered and rejected.** Playwright screen recording: what OpenSEO did;
you said no, and it is also the least designed thing on their page. Motion
Canvas: capable, TypeScript, generator-based; no skill installed and no
component reuse. Lottie and Rive: a runtime library plus a designer tool,
for illustration rather than product. GSAP and Motion.dev: scroll-driven
animation in the page, which `site/DESIGN.md` forbids ("no parallax, no
scroll-jacking, no decorative loops"). After Effects, Jitter, Screen Studio:
not agent-operable. GIF: 10× the bytes of a webm for worse quality.

**Output set per composition:**

```
remotion render → demo.mp4         (h264, crf 24, 30 fps, ≤3 MB)
                → demo.webm        (av1 or vp9, ≤2 MB)
                → demo-poster.webp (a chosen still, ≤80 KB)
```

## The film: one Monday, one job done

Not a feature tour. One person, one question she gets asked every week, and
the five minutes it takes now. 30 s hard cap, 30 fps, 1600×1000 (16:10, the
window's ratio), loops: the last frame dissolves into the first. Brand:
`site/DESIGN.md` tokens, Georgia display with the italic orange second beat,
system sans for UI, navy ground for the type beats, off-white for the app.
Every number is one the README already shows (Kestrel story).

The delight is in three devices, used once each: a clock that runs the wrong
way, a cursor with intent, and a reply that lands back where the question
came from.

**Staging: one canvas, not nine cuts.** The chat thread, the five tabs, the
Duct window and the closing type all live on one large plane; scene changes
are camera moves (scale + translate on a master `<AbsoluteFill>`, 1.5–2.5 s,
cubic-bezier 0.4/0/0.2/1), so a viewer never loses where they are. The only
hard cut is into scene 8. This is the pattern from the Claude Design launch
film, below, and it is what separates a film from a slideshow.

| # | Time | Scene | Motion | Beat |
|---|---|---|---|---|
| 0 | 0–3 s | A chat bubble drops in: **@maya why are signups down this week?** Typing dots under it. A clock in the corner reads **09:02** | Bubble springs from below with 0.6 damping; dots loop | The job, as it actually arrives |
| 1 | 3–7 s | The old way. Five browser tabs fan out of the bubble: Google Ads, GA4, Stripe, Mixpanel, Search Console, each showing a fragment of a number that disagrees with the next. The clock spins **09:02 → 11:40**. Type, small: *five tabs · three hours · still a guess* | Tabs fan on staggered springs; numbers flicker; clock hands blur | The pain, without a paragraph |
| 2 | 7–9 s | Tabs collapse into one sidebar. The clock **rewinds** to 09:02 with a tick. Duct's window is on screen | Scale-to-point collapse; clock reverses with an ease-in-out; a single frame of orange | The promise: same question, back at 9:02 |
| 3 | 9–14 s | The same question is pasted into the session. Three chips light in parallel, not in sequence: **Ads · GA4 · Stripe**, counters ticking. The finding lands: **ROAS ↑ 14 %** green, **Android D7 retention ↓ 2.4×** red, then the sentence underlines itself: *you're paying to acquire churners* | Chips spring simultaneously; counters interpolate; numbers overshoot-spring; underline is a width tween | Reads across tools; finds the thing a dashboard can't |
| 4 | 14–19 s | A change card slides up: *Pause "Android – broad"*, est. **–€1.2k/wk** spend. A cursor travels to **Approve**, presses. Check. Ledger line: *rolled back in one click*. Below, a brief assembles in four lines with citation chips | Cursor on a bezier with ease-out; button 0.96→1; check springs; lines fade-up staggered 120 ms | Acts, only with approval; writes it down with sources |
| 5 | 19–22 s | A stamp: **learned · Android churn is paid-driven · 16 Sep**. The clock reads **09:07** | Stamp 1.3→1 with a 2-frame ink bleed; clock ticks once | Remembers; five minutes |
| 6 | 22–26 s | Cut back to the chat. Maya's reply lands under the question: *Android paid users churn 2.4× faster. Paused the campaign, brief attached.* The asker reacts 🎯 | Bubble springs in; the reaction pops with a 1.2 overshoot | The job is done where it started |
| 7 | 26–28 s | Two cards flip in over the chat, small: **SEO audit · 12 fixes, prioritised** and **Content Studio · 5 posts scheduled** | Y-flip, 80 ms stagger | Other jobs, same desk |
| 8 | 28–30 s | Navy. *Open source. MIT.* then in orange italic, *Your keys stay yours.* Download · Star on GitHub. Dissolves to scene 0 | Cross-dissolve into the loop | The ask |

Cut points for the shorter renders: 3, 4, 5, 6 each pad to 8 s as a tile
loop. The vertical cut stacks scene 1's tabs and drops the ledger line.

## Motion vocabulary, taken from the Claude Design launch film

Reference: the 81 s film on the Claude Design announcement (YouTube
`t_LBECIQQqs`), broken down shot by shot at 3 fps. It has roughly five true
cuts; everything else is a camera move on one canvas. Four devices recur,
and they are the whole vocabulary we need. Timings are theirs; use them as
written, then tune by eye.

| Device | When | Timing | Implementation |
|---|---|---|---|
| **Origin-anchored panel** | Any panel, card, dropdown or bubble that a click or an event produces | 250–300 ms, spring (stiffness ~150, damping ~15) | `transform-origin` at the pixel that spawned it; `scale 0.85→1`, `opacity 0→1`. The change card in scene 4 and the reply bubble in scene 6 use this, anchored to the Approve button and to the question |
| **Spatial canvas navigation** | Every scene change except the last | 1.5–2.5 s, ease-in-out (`0.4, 0, 0.2, 1`) | One master wrapper holding every scene; animate `scale` and `translate` together so the camera arrives exactly on the next scene's centre. Unfocused regions drop to 60 % opacity |
| **Latency pill** | Scene 3, while the three tools are being read | Pill springs in with slight overshoot; word swaps by a masked slide-up, 300 ms; progress fills linearly | One centred pill with the orange dot rotating, *reading Ads → reading GA4 → reading Stripe*, instead of three spinners. Standardises "thinking" wherever it appears |
| **Staggered build-in** | The brief's four lines, the sidebar's connector marks, the tile cards | 400 ms per element, 50–100 ms stagger, ease-out | `opacity 0→1`, `translateY 20px→0`, driven by `frame − index × stagger` |

Also worth taking: the **stroke-dashoffset draw** for the bar-to-line chart
(800 ms, ease-out) is exactly scene 2's lines-into-one-node; the **global
palette interpolation** on the dark-mode toggle (500 ms, every colour at
once) is how the navy↔off-white ground should change between scenes 2 and 3;
and the generous **30–45 frame hold** after narrative type finishes animating
is the reason their film is legible at speed.

Do not copy: the constant one-character-per-frame typewriter. Scene 3's
question types with a human cadence: variable 1–3 frame intervals, a 6-frame
pause after the comma.

## Micro-loops on the page

The film is the hero. Elsewhere, motion is a short loop that shows one thing,
or nothing. Every loop comes from the same Remotion project (a composition
per loop, `calculateMetadata` for size), ships as `webm` + `mp4` + `webp`
poster, `autoplay muted loop playsinline preload="metadata"`, source attached
only near the viewport, and falls back to the poster under
`prefers-reduced-motion`. Budgets are per asset.

| Where | Length | What moves | Budget |
|---|---|---|---|
| Hero | 30 s | The film | 3 MB |
| "What it does", tile 1: reads across tools | 4 s | Twelve marks draw lines into one node (scene 2) | 300 KB |
| Tile 2: acts with approval | 4 s | Cursor → Approve → check → *rolled back in one click* (scene 4) | 300 KB |
| Tile 3: remembers | 2 s | The memory stamp lands (scene 5) | 150 KB |
| Tile 4: your keys, your plan | 2 s | The "Continue with ChatGPT" card's toggle springs, key field masks itself | 150 KB |
| Three agents, each card | 10 s | Insights: scene 3 → 4. SEO audit: URL pasted, crawl counter, fixes list builds in. Content Studio: card moves across the board, slide renders, *published* chip | 800 KB each |
| Nav, GitHub star count | 1 s, CSS only | The count ticks up from 0 on first paint, once per session | 0 |
| Open-source section | 1 s, CSS only | The MIT badge and the key-in-keychain mark fade-up on reveal | 0 |
| FAQ, footer, free tools | none | | |

Page weight ceiling for video: 6 MB total, none of it before the hero's
poster has painted. Nothing autoplays with sound anywhere.

## Claude Design's part

Claude Design (the `design` skill: a multi-artboard canvas, editable by hand,
published as an artifact) is the storyboard tool, not the render tool. Use it
three times:

1. **Storyboard**: nine artboards at 1600×1000, one per scene, with the
   Kestrel numbers and the site tokens, so the film is signed off as stills
   before a frame is rendered. Tweak in the canvas; the agent reads it back.
2. **Posters and tile stills**: the poster frames and the reduced-motion
   fallbacks are exports from the same boards, so they match the loops.
3. **The page**: the landing page's new sections mocked at desktop and phone
   width before the HTML is written, which is cheaper than iterating in
   `site/`.

It does not make the video. Remotion does, from the signed-off boards.

Shipping rules for the `<video>` on the site: `autoplay muted loop playsinline
preload="metadata"`, `poster` always set (scene 4's finding), the source
attached only when the element is near the viewport (IntersectionObserver,
same pattern as `.reveal`), and under `prefers-reduced-motion` no autoplay:
poster plus a play button. That last one is where OpenSEO is wrong and
DESIGN.md is right. No audio on the site version; the YouTube composition
adds music and, if wanted, a voiceover.

## The page, section by section

Word budget: 600. Every section either shows the product or is one row of
tiles.

| # | Section | Now | Proposed |
|---|---|---|---|
| 0 | Nav | Solutions · Free tools · How it works · Blog · Download | **Use cases** (the `for-*` pages, kept for search; "Solutions" is agency-speak) · Free tools · Blog · **GitHub ★ count** (live from `api.github.com`, cached 1 h in localStorage; shown only at ≥ 100 stars, plain "GitHub" below that) · Download |
| 1 | Hero | H1, two paragraphs, CTA, CSS brief mock | Eyebrow *Open source · MIT · your own model keys*. H1 keeps the serif + italic beat, ≤8 words. One line. **Download for macOS** + **Star on GitHub**. Below: the demo in a window frame, poster = the finding |
| 2 | Problem ("You have the data…") | 4 text cards | Cut. The demo's first 12 s say it |
| 3 | "Why make it complicated?" comparison | two lists | Cut |
| 4 | How it works (dark band) | 3 text steps | **What it does**: four tiles, each an existing README shot: reads across tools (`connectors.webp`), acts with approval (`review-card.webp`), remembers (`memory-timeline.webp`), runs on your ChatGPT plan or your keys (`chatgpt-card.webp`). ≤15 words each |
| 5 | The brief in your inbox | text + mock | Cut. Briefs live in the desktop app now; nothing is mailed |
| 6 | Built for the role | 6 cards, half "in development" | **Three agents, written as jobs, not features.** Each: a README shot, then *When… / Today… / With Duct…* in ≤ 30 words. Insights: *when someone asks "why did signups drop", today it's five tabs and three hours; Duct reads Ads, GA4 and Stripe together and answers with the change it proposes.* SEO audit: *when a site needs a look, today it's a paid tool or a consultant; paste a URL, no account, prioritised fixes.* Content Studio: *when the week's posts are due, today it's a plan in Notion and five upload boxes; plan on a board, generate, publish to nine networks, results come back to the card.* Under them, a **Coming next** row of three chips from the README: Sales & RevOps · E-commerce & DTC · Customer Success. Roles become a single line of chips linking to the `for-*` pages |
| 7 | Free tools | keep | keep, shorter |
| 8 | Stats band | `9+ · ~4h · 10min · 0` | Cut until the numbers are real |
| 9 | FAQ | 9 questions | 5, and add the honest one: *Is it free? Core is MIT and stays that way; a hosted team plan comes later* |
| 10 | Footer | Product · Free tools · Company · … | Product column stays. **"Company" becomes "Project"**: there is no company yet, there is an open-source project. About, Doctrine, Changelog, GitHub, Licence (MIT), Privacy, Terms. The line under the logo says so too: *an open-source project by Alleviate Lab*, not a company boilerplate |

Social proof: none faked. When there are three real quotes or a Product Hunt
day, they go between 4 and 6.

## Pages to add or change (commercial → open source + commercial later)

- **`/open-source`, new.** The trust page a commercial-later OSS project needs
  and the one the site is missing. Why it is open, MIT, what stays on your
  machine (model keys in the OS keychain, the desktop app runs the service for
  you), self-host in four commands (pointing at the README's section, not
  duplicating it), a desktop-vs-self-host table, and one honest paragraph on
  what will be paid. Nav and footer link to it.
- **`/pricing`: not yet.** There is nothing to sell; a pricing page with one
  "Free during beta" box reads as a placeholder. The FAQ line and the
  `/open-source` paragraph carry it until there is a plan. The likely shape
  of that plan is the one OpenCode took with *Go*: the tool stays free with
  your own keys, and a flat monthly plan bundles model access so nobody has
  to hold keys at all. Write the FAQ answer so it is still true when that
  ships: *free with your own keys, always; a paid plan later bundles the
  models.*
- **One page per agent, for discovery, not as feature pages.** Yes, and
  after the landing page. The `for-*` pages answer *who* ("for paid ads
  teams"); an agent page answers *what job* ("why did signups drop",
  "AI content agent for TikTok and LinkedIn"), which is a different query
  cluster and the one people actually type. Three pages: `/growth-insights`,
  `/content-studio`, and `/seo-audit`, which already exists as the free
  front door and becomes the template. Each: the 8 s tile loop from the
  film, the *When / Today / With Duct* copy, three FAQs from real questions,
  `SoftwareApplication` JSON-LD with `featureList`, and a link from the
  README's agent section so the repo sends authority to it. Written with the
  `new-page` skill, whose first question is "what's the hypothesis?"; the
  hypothesis for each is a named query cluster in Search Console within
  eight weeks, or the page is folded back into the landing page. Coming-soon
  agents get no page until they exist: a page with nothing behind it is the
  thin-content pattern search engines punish.
- **`/about`**: rewrite the story from "we built a brief service" to why it
  went open source.
- **`/download`**: add "or self-host" beside the buttons.
- **`for-*` pages**: keep; add the GitHub CTA next to Download; replace the
  CSS mocks with the relevant shot.
- **SEO/AIO across the site**: H1 and `<meta name=description>` carry the
  README's own line ("open-source AI agent for product and growth teams");
  `SoftwareApplication` JSON-LD gains `license`, `isAccessibleForFree`,
  `codeRepository`; `llms.txt` rewritten; per-page OG images (DESIGN.md's
  known gap: one 670 KB PNG serves 24 pages).

## Order

0. Storyboard in Claude Design: nine boards, signed off as stills. Half a
   day, and it is the only step where taste is cheap to change.
1. `scripts/motion/`: the Remotion project, the token bridge to `app/`'s
   components, and the 30 s film rendered to `site/assets/media/`. Everything
   else needs the video.
2. Landing page rewrite against the table above, with the video.
3. `/open-source`, `/about`, `/download`, `for-*` CTAs.
4. SEO/AIO sweep and OG images.
5. The tile loops, the vertical cut and the YouTube cut: same compositions,
   new `calculateMetadata`, once 2 has shipped.
6. The agent pages, `/seo-audit` first as the template, each with its loop
   from 5 and its own hypothesis.

Each is its own issue; none is a small fix, so each goes through
`prioritize` before code.
