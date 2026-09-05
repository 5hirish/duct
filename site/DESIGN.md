# Duct site — design & voice guide

[`AGENTS.md`](AGENTS.md) holds the mechanical rules CI enforces — head
checklist, canonicals, asset order, the demo contract. This file holds what
the site should **look, sound, and convert like**: the visual system as
actually built, the voice codified from its best lines, and the principles
that keep a new landing page from reading as a template. It is the site-side
companion to [`../app/DESIGN.md`](../app/DESIGN.md); the research citations
(NN/g, WCAG 2.2, Refactoring UI, Kowalski, the anti-generated-UI writing)
are shared between them.

Every page here is an experiment (`AGENTS.md`: landing pages validate
conversion; blog compounds search). Design serves the hypothesis — a page
that looks generic tests nothing, because nothing about it argues Duct made
it.

---

## The system as built

No build step, no framework — the whole brand is 13 custom properties at the
top of `assets/duct.css`, two system font stacks, and a handful of moves
used consistently. That economy is the style; keep it.

**The signature moves** (these make a page recognizably Duct):

- **Georgia display over system sans body.** All display type is the
  `--serif` stack; body/UI is `--sans`. The strongest move on the site is
  the *italicized second beat in the accent color* — `<em>` inside an
  `h1`/`h2` ("Stop checking dashboards. / *Start shipping decisions.*").
  Use it on every major headline; it is the wordmark of the copy.
- **The `.tag` eyebrow** — 11px/600 uppercase with the 20×2.5px accent dash
  — opens nearly every section (~45 uses). Keep it.
- **Section rhythm: white ↔ `--off`, punctuated by full-bleed navy and one
  full-bleed accent band.** The alternation is the page's pacing; a new
  section picks the next background in the rhythm, and navy/accent bands
  stay rare so they keep their weight.
- **Hairline grids**: card groups render 1px gaps over a `--border`
  background instead of per-card borders (`.pain-grid`, `.feat-grid`).
- **Fluid display type**: `clamp()` on `h1`/`h2` only — body sizes are
  fixed, spacing is fixed. Don't extend `clamp()` to spacing.
- **The logo is text**: lowercase Georgia `duct` + the orange dot. The dot
  is the brand's one graphic element.

**Structure numbers**: container `max-width: 1160px`, side padding 52px →
24px mobile; section padding 96–100px → 64px mobile; primary breakpoint
860px (nav collapse and grid→1col), desktop-first `max-width` queries.
Buttons are one `.btn` pill base + `-orange`/`-dark`/`-ghost` variants and
`-lg`; hover is darken + `translateY(-2px)` + tinted shadow on the primary.

**What the site deliberately does not have**: dark mode, photography,
testimonials (the `.quotes` CSS is dead until real quotes exist — never
fake them), a `<form>` element (the Google Forms data-attribute contract in
`AGENTS.md`), or any runtime dependency beyond `marked` on the blog.

---

## Stack guidelines — the framework is its absence

The site's "framework" is a deliberate nothing (`AGENTS.md`: no build
tools, no frameworks), so the library guidelines are mostly prohibitions
with one theme each:

- **Fonts: system stacks only.** Georgia (`--serif`) for display, the
  `-apple-system` stack (`--sans`) for body. Never add a webfont `<link>` —
  the 14 pages currently loading Google Fonts nothing uses are the
  cautionary tale (Known gaps). A new page inherits both stacks from
  `duct.css` and declares no font of its own.
- **`marked` (blog only)** — the one runtime dependency, pinned from
  jsDelivr in `blog/post.html`. It renders trusted repo content
  (`blog/posts/*.md`), which is why there's no sanitizer; never point it
  at anything user-supplied, and don't introduce it on other pages.
- **Vanilla JS, ES5-leaning** — `duct.js` owns the behaviors (reveal, nav,
  drawer, forms); a page adds at most a small inline script in its own
  `<style>`-adjacent block. No Alpine, no jQuery, no module imports.
- **GTM** stays lazy-loaded through `duct.js` and configured via
  `DUCT_CONFIG` — never a synchronous tag, never a hardcoded ID.

**Text readability rules** (the site's thin-grey habit is the risk):

- `font-weight: 300` is legal only at ≥15px; below that, body text runs
  400 — 13px/300 in `--navy-3` is the survey's "technically AA, visually
  faint" finding, and it's the default today.
- Line-height pairs inversely with size: display 1.02–1.1, subheads
  ~1.3, body 1.6–1.8 (`.prose` is 1.8 — the model).
- Negative letter-spacing only on large serif display (it's -2.5px on the
  h1; never on body sizes).
- Every text block capped at 45–75ch; body text never below 13px, and
  13px is meta-only (dates, read times, footnotes).

---

## The small things

The site is hand-written HTML, so nothing enforces consistency except
habit. These are the habits:

- **Radii come from the three tokens** — `--r` 12px, `--r-lg` 20px,
  `--pill` — never a fourth ad-hoc value.
- **Hover motion is a vocabulary, not a per-page choice**: `-2px` lift on
  buttons, `-3px` on cards, `translateX(4px)` on list rows. A new
  hover state picks from those three.
- **Section padding holds the rhythm**: 96–100px desktop / 64px mobile;
  the CTA band's 120px and the strip's 36px are the two sanctioned
  outliers. Don't invent 80px.
- **The proximity inversion applies here too**: an eyebrow sits closer to
  its heading than the heading to the previous section; a `.field-hint`
  closer to its input than to the next field.
- **Alignment does the work of borders**: card groups share edges via the
  hairline-grid trick; inside a card, everything hangs off one left edge.
  Numbers in the stats band and calculators align on tabular-looking
  layouts even though the fonts lack `tabular-nums` — keep figures short
  and rounded instead.
- **Arrows and dashes**: the arrow is ` →` (space + character) at the end
  of a label, never `&rarr;`/`&nbsp;` variants (they wrap differently);
  em dashes are spaced ( — ) matching the copy on the site.
- **One inline `<style>` block per page, at the end of `<head>`** — the
  confirmed convention; a second block or a `style=""` attribute for
  anything reusable is drift. (Inline `style` survives only for the
  per-card reveal delays and blog-card gradients today; don't grow it.)

**Web, tablet, mobile.** Desktop-first `max-width` queries; 860px is the
primary breakpoint, 640/600 for tool internals. The checkable residue:

- Test at 360px (small phone), 768px (tablet portrait — inside the
  forgotten 600–1100 band where grids must have already collapsed
  sensibly), 1024px (tablet landscape), and 1440px+.
- **Tablet landscape gets the desktop nav** (>860px) — the Solutions and
  Free Tools dropdowns are hover-driven, so verify tap opens them on
  touch; hover-only affordances need a touch path.
- Touch targets ≥24×24px everywhere (WCAG 2.5.8) — the nav's inline-styled
  small CTA and footer links are the ones to watch.
- Nothing depends on hover to be discovered: the marquee pauses on hover
  (fine, it's decorative); card links must be obvious without it.
- Test once with JS off: today that blanks the page (Known gaps —
  `.reveal` and fetched partials); a new page must not make that worse.

---

## Accent variants — one override, not a repaint

Landing experiments re-tint the accent (blue on `/for-paid-ads` and the
tools, green on `/for-organic-growth`, terracotta on `/seo-audit`). Three
strategies coexist today; only one is right:

**Redefine `--orange` and `--orange-h` in the page's inline `<style>` —
nothing else.** Everything downstream (buttons, tags, links, demo chrome)
inherits in one line, which is exactly how `for-paid-ads.html` and the
tools pages do it. Never invent a parallel variable and hand-repaint
selectors — `for-organic-growth.html` overrides ~35 selectors by hand,
including one that no longer exists, and that is the maintenance bill this
rule avoids. If the demo is on the page, set `sparkColor` in the variant JS
to match (it defaults to blue — `for-product-intelligence` currently ships
an orange page with a blue sparkline).

Two consequences to resolve at the token level (see Known gaps): split
`--brand` (the fixed orange the logo dot and favicon use) from the
overridable accent, so an experiment can re-tint the page without
repainting the brand mark; and give the accent a **text-safe** dark
variant, because the next section makes plain orange illegal for body text.

---

## Color & contrast — the orange rule

`--orange #FF5C00` on white is ≈3.1:1. WCAG 2.2 AA needs 4.5:1 for normal
text and 3:1 for large text (≥24px, or ≥18.66px bold) and UI components. So:

- **Accent-on-white is for display and accents only**: the `h1 em`, big
  serif stat numbers, the `.tag` dash, borders, icons — large or non-text
  uses that clear 3:1.
- **Never for body-size text.** `.prose a` (16px links), `.uc-link`,
  `.feat-label`, `.aud-badge` all fail today. Body links become navy text
  with the accent underline, or use a darkened text-safe accent token that
  measures ≥4.5:1. (The tools pages' blue is ~5.2:1 — accidentally the most
  accessible accent on the site; the brand orange needs the same courtesy.)
- **The `.stats` band fails outright** — 13px labels at 70%-alpha white on
  orange is ≈2.2:1. Fix: full-opacity white, larger/bolder, or a navy band.
- **Amber badges** (`#c9a84c` on `#fff7e6` ≈2.1:1) need darker ink.
- Status colors keep their meaning: green = good movement, amber = soon/
  waiting, red = negative — always paired with a non-color cue (WCAG 1.4.1).

---

## Voice — the copy is the brand

The site's voice is imperative, contrastive, second-person, and specific.
Its two signature structures, straight from the pages:

1. **"Stop X. Start Y."** — the two-beat hero, second beat italicized in
   accent: "Stop checking dashboards. *Start shipping decisions.*" · "Stop
   reading tools. *Start reading signals.*" Even the 404 runs it: "Your
   tools have the answer. *This page doesn't.*"
2. **Concession → twist** — "You have the data. You just can't read all of
   it *at once.*" · "The signal is in your platforms. But none of them
   *talk to each other.*"

Rules, checkable in review:

- **Numbers beat adjectives.** The strongest copy on the site is numeric:
  "ROAS up 14% but Android 7-day retention down 2.4×… You are paying to
  acquire churners." · "3–5 hours gone before the week starts." Write that,
  not "actionable insights".
- **The founder test**: would you say it out loud? "Join growth
  intelligence beta" fails it; "That's me — get early access →" (the
  site's best CTA — canonical for audience-fit sections) passes.
- **Don't reuse a headline template thrice.** The three `for-*` pages run
  "Built for X who *move fast*" with a swapped noun — the third copy of a
  headline is a template, and templates read as generated. Each experiment
  earns its own line.
- **First two words carry the meaning** (NN/g): "Google Ads settings",
  "Keyword gap analysis…" — front-load headings, links, and CTAs.
- **FAQ answers are voice, not filler.** Several current answers are
  visibly LLM-flavored ("This gives teams both a strategic weekly view…")
  and get mirrored into JSON-LD verbatim — rewrite in the page's voice
  when touched, since search engines quote them.
- Mechanics: sentence case (Title Case only for proper names and blog post
  titles); American spelling ("synthesizes", per the site's own meta
  description — no "optimising" beside "prioritized"); the arrow is the
  `→` character with a normal space, not `&rarr;`/`&nbsp;` variants.

---

## Landing-page craft

- **One page, one hypothesis, one primary CTA.** The email capture is the
  conversion path; every section either argues for it or gets cut. Halve
  the words — concise text is the most measurable usability win there is
  (NN/g), and visitors read ~28% of them.
- **Break the uniform grid.** The home page runs four consecutive
  equal-cell grids and the `for-*` pages three more; nothing is ever
  featured, sized up, or pulled out of line. Slop reads as "every element
  the same weight" — give each page one deliberately heavier element (the
  hero brief-card mock is the model) and let one card in a grid be wider
  or deeper when it carries the argument.
- **Earn the center.** Centered text is for short display moments (CTA
  band, stats); working sections read better left-aligned with an
  asymmetric split (the home hero, `.problem`, `.preview` are the good
  examples). A page that centers everything reads as a template.
- **Social proof stays honest.** Real numbers ("9+ tools", "10 minutes to
  connect") over fake logos or invented testimonials — the dead `.quotes`
  CSS stays dead until real quotes exist.
- **The demo is the best salesman** — it shows the product reasoning over
  real-looking numbers. Prefer extending the demo (a new variant per
  `AGENTS.md`) to adding another static feature grid.
- **Prose gets a measure everywhere**: caps exist (`700px` prose, `500px`
  hero sub) but a few blocks run ~120 characters; anything textual gets a
  max-width in the 45–75ch band.

---

## Motion

The vocabulary is small and consistent — keep it that way:

- Scroll-reveal (`.reveal`, opacity + 24px rise, .55s) for section
  entrances, staggered ≤.32s; hover lift `-2px` buttons / `-3px` cards;
  `fadeUp` in the hero; the marquee; the logo-dot pulse.
- Nothing else. No parallax, no scroll-jacking, no decorative loops.
  Transitions stay ≤.3s, ease-out, transform/opacity (Kowalski).
- **`prefers-reduced-motion` must cover all of it** — today it covers
  three demo transitions and misses the reveal, the marquee, and the
  infinitely pulsing logo dot (Known gaps).
- **Reveal must not be able to hide the page**: `.reveal { opacity: 0 }`
  with no fallback means a JS failure leaves content invisible. Gate the
  hidden state behind a JS-added class.

---

## Blog

- The measure is the design: 700px `.prose`, 16px/1.8 body, orange links
  (→ text-safe accent per the contrast rule), the 3px reading-progress bar.
  One idea per H2; front-load the H2s — they are what scanners read.
- Post titles are Title Case; everything else sentence case. Excerpts on
  the index must match the post's front-matter excerpt — they drifted once.
- Card art is currently an emoji on a brand-tinted gradient `div`. That's
  the interim canon — consistent tint direction (135deg, brand-family
  colors), one emoji, `aria-hidden`. Real per-post cover images (and
  per-post OG images — today one 670KB PNG serves every page on the site)
  are the upgrade path.
- A post teaches the reader to *stop doing manual work* — the two live
  posts' shape ("The old way… The new way…") is the house post structure.

---

## Not template slop

The site's specific risk is not the app's (no shadcn defaults here) — it's
the *landing-page* tells:

| Tell | This site's corrective |
|---|---|
| Interchangeable hero copy | The two signature structures, numbers in the sub, founder test |
| Same headline, three pages | One earned line per experiment |
| Uniform card grids, nothing featured | One heavier element per page; break a grid when the argument needs it |
| Centered-everything | Asymmetric working sections; center only display moments |
| Fake testimonials/logos | Real numbers or nothing |
| Emoji standing in for an icon system | Emoji are the current system — used consistently and `aria-hidden` — but migrate to one inline-SVG set when touched (the white-on-navy `filter: brightness(0) invert(1)` hack renders differently per platform) |
| Stock three-step "How it works" copy | The steps exist; write their bodies in voice ("Connect your tools" is the flattest copy on the site) |
| One OG image for 24 pages | Per-page OG images, compressed |

---

## Review checklist for a new page

1. What's the hypothesis, and does the `<!-- EXPERIMENT: -->` comment state
   it? (From `AGENTS.md` — but design review starts here too.)
2. Hero: signature structure, italic accent beat, a numeric sub, one CTA?
3. Squint: is one element visibly heavier, or is it grids all the way down?
4. Read every string aloud — founder test, first-two-words test, no
   template line reused from a sibling page.
5. Accent: one-line `--orange`/`--orange-h` override only; sparkline color
   matches; no hand-repainted selectors.
6. Contrast: no accent-colored body text; badges and bands pass their AA
   number; status never color-alone.
7. Keyboard: skip link present, focus visible on buttons/nav/FAQ (not just
   the UA default on an orange button), email-capture errors have text +
   `role="alert"`, not a color flash.
8. Motion: reveal-stagger only, reduced-motion covered, page readable with
   JS off.
9. Measure: every text block capped in the 45–75ch band.
10. Weight: no new fonts, no new dependencies, inline `<style>` stays the
    only page CSS, and the page adds zero rules to `duct.css` that only it
    uses.

---

## Known gaps — close on touch

- **14 pages load Google Fonts that nothing uses** (`Instrument Serif` +
  `DM Sans` on `for-paid-ads` and all tools) — render-blocking, zero
  visual effect. Delete the `<link>`s.
- **Accent strategy**: `for-organic-growth.html`'s `--green` + ~35 hand
  overrides → the one-line `--orange` override; its demo markup is also
  minified onto a single 14KB line and inlined instead of linking
  `demo.css` like `for-paid-ads` does.
- **Token splits to make**: `--brand` (fixed, logo dot/favicon) vs the
  overridable accent; a text-safe accent (≥4.5:1) for links and labels;
  the success green `#1a9e5c` currently invented inline in `duct.js`.
- **Contrast fixes**: `.stats` band labels, accent-colored body links,
  `.tag-soon`/amber badges, `.sev-high` at 10px.
- **Focus-visible styles exist only in `demo.css`** — `.btn`, nav links,
  `.faq-q`, cards all ride the UA default, which is invisible on orange;
  `.email-in` sets `outline: none` with only a border-color swap behind it.
- **Hero email validation is a 2s color flash** — no message, no
  `role="alert"`; the calculators already do this right
  (`assets/tool-validation.js`), apply the same pattern.
- **`.reveal` has no no-JS fallback** — content is invisible if `duct.js`
  fails; nav/footer/CTAs also all arrive via `duct-partials.js` fetch.
- **`prefers-reduced-motion`** covers 3 demo transitions; extend to
  `.reveal`, `fadeUp`, the marquee, the logo pulse, smooth scroll.
- **Dead code**: `.quotes`/`.qcard` family; `.prose pre/code` unexercised;
  `.blog-card-img` styled for `<img>` but used as a gradient div.
- **Five shadow recipes, no shadow tokens; no spacing scale** — tokenize
  when a page is touched, don't add a sixth.
- **`.skip-link` re-declared inline on 6+ pages** (it's in `duct.css`);
  five pages have no skip link at all (`about`, `404`, `privacy`, `terms`,
  `seo-audit`).
- **Semantic drift**: 20–22px serif "titles" marked up as `<p>`
  (`.feat-title`, `.step-title`) — they read as headings but aren't in the
  outline; `role="list"` on the blog grid overrides the links' semantics.
- Mixed root-absolute vs relative asset paths within one head
  (`index.html`); `→` vs `&rarr;` inconsistency; British/American mix on
  `for-organic-growth`.
