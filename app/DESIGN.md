# Duct app — design & UX guide

[`AGENTS.md`](AGENTS.md) holds the mechanical UI rules — container sizing,
units, CSS file layout, accessibility basics. This file holds what the app
should **look, feel, and sound like**: the design system as actually built,
one canonical pattern per job, and the principles that keep new screens from
reading as generated defaults. The deep reasoning behind the layout system
lives in `docs/engineering/desktop-adaptive-ui-review.html`; this file does
not repeat it.

Rules cite their source where they came from research (NN/g, Apple HIG,
Material, Refactoring UI, WCAG 2.2, Emil Kowalski, Rauno Freiberg, Linear,
Slack/Mailchimp/Microsoft voice guides). Rules without a citation come from
this codebase's own measured conventions.

---

## North star

Duct is **built for the role that owns the decisions** — an operator drowning
in five dashboards who wants synthesis and a next step, not more charts. The
site promises "Stop tab-switching. Start deciding." The app has to keep that
promise in its bones:

- **The UI's job is to make the user feel ahead of their data.** Lead with
  what changed and what to do; totals are context, not headline.
- **Speed is the core delight.** For founders and growth operators, the answer
  appearing fast beats any animation (Linear: "designed for purpose…
  say no to busy work"; Raycast's founding complaint: tools "bloated, slow,
  and miss keyboard shortcuts"). Optimistic where safe, keyboard everywhere,
  nothing animating on the daily path.
- **Fun means curiosity, not gamification.** Celebrate *outcome* velocity
  ("3 weeks of rising branded clicks"), never usage streaks; nudges are
  opt-in; no guilt copy. Streak mechanics are the documented failure mode of
  productivity gamification (Duolingo's "streak creep").
- **Confident, plain, human.** The product already talks like this — "Duct
  checks a number before it trusts it." Keep that voice; never ship a string
  a smart coworker wouldn't say out loud.

---

## The system as built

**This file has a rendered half.** `/preview` in **Design system** mode (dev
only, `npm run dev` in `app/`) shows it running, in three sections that mirror
how a system is read:

| Section | What it shows |
|---|---|
| **Foundations** | Colour, type, shape, spacing, icons — read from the running app, so it is the value *after* the cascade, not what a stylesheet claims |
| **Primitives** | Every `components/ui/` part, with all the variants a call site can pick between |
| **Patterns** | The canon table below, one entry per row: the rule **parsed from this file**, beside a live example |

Rules are parsed, never retyped, so the screen cannot disagree with the prose.
Every entry gets the device, theme and lens axes, which makes "does this hold at
150% text, in dark, under deuteranopia" a dropdown rather than a project.

Two things follow. **Check a token or a variant there before shipping it** —
that is what caught `--destructive-foreground` missing from the `.dark` block.
And **do not add a canon row here without an example**: a row with none is
listed as a gap and counted in the header, which is the point, but it is your
gap.

Framework: Next.js 16 App Router, React 19, Tailwind CSS 4, shadcn/ui +
Radix primitives, lucide-react icons, next-themes. Also runs inside the Tauri
desktop shell — desktop is a first-class surface, not a port.

**Type.** DM Sans (`--font-sans`, also `--font-heading`) + JetBrains Mono
(`--font-mono`) via `next/font`, `display: swap`. Georgia (`--serif`) is
reserved for the wordmark and the signed-out hero — do not use it inside the
app. The app is deliberately a **two-size system**: `text-sm` body,
`text-xs` secondary; `text-2xl font-semibold tracking-tight` for the page
title (`.page-toolbar-title`), `text-sm font-semibold` for section headings.
Do not invent intermediate sizes — and do not write `text-[11px]`
arbitraries (see Known gaps). Hierarchy comes from weight and color, not a
parade of sizes (Refactoring UI: 2–3 weights, 2–3 text colors; de-emphasize
the secondary rather than enlarging the primary).

**Color.** Two systems in `src/app/styles/tokens.css`: raw brand hexes
(`--orange #ff5c00`, the navys) and the shadcn oklch semantic set. Dark mode
is next-themes class-attribute with **pure token substitution** — no
component writes its own `.dark` rules, and new code must not start.
Surfaces are dark grey, not black; elevation lightens; accents desaturate in
dark (Material dark-theme guidance — the tokens already follow it).

**Lifting a colour for dark means darkening its partner.** `--primary`,
`--success` and `--warning` each pair a lifted dark-mode colour with a
darkened `-foreground`; a `-foreground` left out of the `.dark` block does not
fail loudly, it silently inherits the light-mode value written for a *dark*
surface. `--destructive` was missing exactly that, so white sat on a lifted
coral at 2.89:1 while its three neighbours ran 7.8–9.9. Verify a new or
changed token at `/preview/frame?scene=tokens&theme=dark`, which renders every
pair with its live ratio — the whole reason it is a screen and not a comment.

The accent rule: **one accent, used semantically.** Status colors are
reserved for status — green means good movement, amber means waiting, red
means destructive/failed, and every status color needs a non-color channel
beside it (WCAG 1.4.1 — the ▲/▼/sign on a delta is not optional). Today
`--primary` is a shadcn-default violet while the brand is orange; that
conflict is the top item in Known gaps. Until it is resolved at the token
level, use `bg-primary` and never spread `bg-[var(--orange)]` ad hoc.

**Shape.** Page code's de-facto card is `rounded-xl border bg-card` —
radius `rounded-md`/`lg`/`xl` for surfaces, `rounded-full` for pills and
icon buttons. Shadows are quiet: `shadow-sm` + `ring-1 ring-border/40` at
most; depth comes from borders and background shifts, not glow.

**Spacing.** Tailwind's scale only — the house rhythm is `gap-8` between
page sections, `gap-3`/`gap-4` inside them, `p-4`/`p-5` card padding.
Proximity is grouping: space *between* groups must exceed space *within*
them — a label sits closer to its field than to the previous field
(Gestalt; the most-violated spacing rule in form layouts). No arbitrary
values (`p-[13px]`); if the scale doesn't fit, the layout is wrong.

**Motion.** Sparse and purposeful, and the bar for adding more is high:

- UI motion stays **under 300ms**, ease-out, `transform`/`opacity` only,
  and interruptible (Kowalski). Popovers scale from their trigger
  (`0.95→1`), never from zero.
- **Nothing animates on keyboard-driven or high-frequency paths.** The
  command palette does not animate, ever (Kowalski, Rauno: after ~100
  repetitions animation is cognitive burden — no motion reads as speed).
- Delight scales inversely with frequency (Family: "the potential for
  delight increases as the frequency of feature usage decreases"). A
  one-time flourish on the first connector linked or first insight
  generated: yes. Anything on the daily path: no.
- State changes prefer opacity to movement — `PipelineProgress` dims done
  steps rather than moving them; keep that temperament.
- Everything that loops respects `prefers-reduced-motion` (today only the
  logo is gated — Known gaps).

**Icons.** lucide only, one set, default stroke. `size-4` default (the
Button auto-sizes), `size-3.5`/`size-3` in dense rows, `size-5` for
banner-leading icons, `size-8`–`12` only as empty-state art. Decorative
icons take `aria-hidden`; icon-only buttons need `aria-label` + tooltip and
are allowed only for repeated row-level actions — primary actions carry
visible text labels (NN/g: almost no icons are universal; hover-revealed
labels raise interaction cost). Never put a themed pictogram next to a KPI —
superfluous icons measurably slow visual search (NN/g dashboards research).
Never use emoji as icons.

---

## The libraries, and how we hold them

Each library is used under one theme — the guideline is how it plugs into
the token system, not how the library works. Never add a parallel library
for a job one of these already does.

- **Tailwind CSS 4** — utilities read the tokens (`bg-card`,
  `text-muted-foreground`, `border-border` via the global reset), which is
  what makes dark mode free. The two banned moves: arbitrary values
  (`text-[11px]`, `bg-[#...]` — if the scale doesn't fit, the design is
  off-system) and viewport variants where a container variant belongs
  (`AGENTS.md` owns that rule). Conditional classes go through `cn()` from
  `lib/utils.ts` (clsx + tailwind-merge) — never string concatenation,
  which silently loses conflict resolution.
- **shadcn/ui + Radix** — `components/ui/` is the vendored layer:
  kebab-case `.tsx` files are generated, the two `.jsx` ones (`lightbox`,
  `spinner`) are ours. Restyle a primitive **at its source** through its
  CVA variants (`button.tsx` is the model — variants and sizes declared
  once, call sites pick by name); a call site that pastes a class string to
  override a primitive is a fork in disguise. The destructive `AlertDialog`
  styling was the standing example and is now closed, but it is worth keeping
  for what the fix found: two of the four call sites had pasted the exact
  string `buttonVariants({ variant: "destructive" })` returns, and the paste
  had gone stale — both were missing `dark:focus-visible:ring-destructive/40`,
  a rule the variant gained and no copy ever received. A fork does not
  announce itself; it just stops receiving fixes. Radix supplies the
  behavior — portal, focus trap, Escape, scroll lock — so never hand-roll
  an overlay, switch, or menu it already ships. New primitive: generate via
  the shadcn CLI, then re-theme it to the tokens before first use.
- **lucide-react** — the only icon set; conventions live in the Icons
  paragraph above. No heroicons, no emoji, no inline one-off SVGs where a
  lucide glyph exists.
- **next-themes** — class-attribute switching; components never branch on
  the theme in JS. If a color needs a dark variant, that belongs in a
  token, not a `resolvedTheme === "dark" ?` ternary (the `AuditReportV1`
  score ramp is the anti-pattern in the tree). Anything reading the theme
  for rendering (like `ThemeToggle`) uses the mounted-guard so SSR doesn't
  mismatch.
- **Recharts + Nivo** — both intentionally present: Recharts for general
  charts (six consumers), Nivo for heatmaps only. Chart series colors come
  from `--chart-1..5`, axes and gridlines from `border`/`muted` tokens,
  tick labels in `text-xs` with `tabular-nums` — a chart with hardcoded
  hexes (the `ArtifactRenderer` palette) is light-only by accident and on
  the gaps list. Follow the dataviz basics: no bare numbers without
  context, delta direction never by color alone.
- **The markdown chain** (react-markdown + remark-gfm/breaks +
  `workspace/CodeBlock` + DOMPurify + mermaid) — agent output renders
  through the existing components (`AuditChat`/`ContentChat`/
  `ArtifactRenderer` are the consumers); never fork a renderer or regex
  markdown by hand. Anything that touches `dangerouslySetInnerHTML` goes
  through DOMPurify, no exceptions.
- **tw-animate-css** — powers the primitives' enter/exit
  (fade/zoom/slide, already tuned to the motion budget). Overlay motion
  comes from it; custom `@keyframes` are for the rare bespoke moment
  (`PipelineProgress`), not for another dialog.
- **Fonts** — DM Sans and JetBrains Mono via `next/font` only. Never a
  Google Fonts `<link>`, never a new family; the serif stays the
  wordmark's.

---

## Go and look — the reference implementations

We vendor shadcn/ui, so shadcn's own site is the reference build of the
components in `components/ui/`. When a screen feels off and the words for
*why* are not coming, open the page below and compare — the answer is
usually spacing, density or type, and it is faster to see the difference
than to reason it out from a stylesheet.

**Browse them visually, not as HTML.** These pages are made to be looked at;
the markdown a fetcher returns drops exactly the part that matters. Open them
in a real browser, screenshot, and put the screenshot next to your `/preview`
frame of the same component. The same discipline as the rest of this file:
measure, do not squint.

| Reference | Open it when |
|---|---|
| [Components](https://ui.shadcn.com/docs/components) | Reaching for a primitive — 80+ of them, each with a live preview, the anatomy, props, and its keyboard/ARIA contract. Check here **before building** anything bespoke; the answer is often a primitive we already vendor and forgot. |
| [Blocks](https://ui.shadcn.com/blocks) | Composing a whole screen — dashboards, sidebars, sign-in, calendars, as full compositions rather than parts. Read them for **how pieces are arranged and spaced at page scale**, which is the judgement a component page cannot teach. Source is viewable and on GitHub. |
| [Charts](https://ui.shadcn.com/charts/area) | Any Recharts work. Same library we use, so this is the closest thing to a reference implementation: axis/gridline treatment, legends, tooltips, and where colour stops carrying meaning. Swap `area` for `bar`/`line`/`pie`/`radar`/`radial`/`tooltip` in the path. |
| [Typeset](https://ui.shadcn.com/typeset) | Prose and long-form: reports, briefs, artifact bodies. An interactive specimen for **measure, size, leading and flow** — the four knobs that decide whether a wall of text reads. It exports a `typeset.css`; read it as a second opinion on `--measure` and our leading, do not paste it in. |
| [Directory](https://ui.shadcn.com/docs/directory) | Before writing a component from scratch. Community registries installable as `npx shadcn add @<registry>/<component>`. **Treat installed code as untrusted** — read every line, and re-theme it to our tokens before first use, the same as a CLI-generated primitive. |

Two standing cautions. shadcn ships **defaults**, not our decisions: their
palette, radii and fonts are not ours, so copy structure, spacing and
behaviour, never the tokens — a pasted `bg-zinc-*`/`text-[13px]` is exactly
the off-system move the Tailwind entry above bans. And a block is a starting
composition, not a finished screen; it arrives without our empty, loading,
partial and error states, and this file's canon still governs each of those.

---

## The small things

Craft is mostly sweating alignment, spacing, and padding until nothing
snags the eye. These are the checkable habits:

**Spacing & padding.**

- The proximity inversion is the rule that makes layouts feel "off" when
  broken: space *within* a group stays smaller than space *between*
  groups. A label sits nearer its field than the previous field; a card
  title nearer its body than the card above.
- Padding is symmetric unless there's a stated reason; card interiors pick
  one value (`p-4`/`p-5`) and hold it on all sides. Controls that sit in
  one row share a height (`h-9` inputs beside `h-9` buttons) — mixed
  heights in a toolbar are the most common small snag.
- One `gap` per row type: `gap-2` for icon+label, `gap-1.5` in dense meta
  rows, `gap-3`/`gap-4` between siblings. Don't mix `gap` and per-child
  margins in the same container.

**Alignment.**

- Align to edges, not centers: labels, numbers, and icons in a list share
  a left (or right) edge down the column. Numeric columns right-align with
  `tabular-nums`.
- Mixed type sizes on one line align to the **baseline**, not vertical
  center (Refactoring UI) — `items-baseline`, not `items-center`, for a
  value + unit pair.
- Icons get optically centered next to text; a 1px `px` nudge is legal
  and expected (`AGENTS.md` units rule) — trust your eye over the flexbox.
  Chevrons and carets are the usual offenders.
- Hover and selection never move things: no font-weight change on hover,
  no border appearing that shifts layout (swap border color from
  transparent instead).

**Containment.**

- Every flex child that can carry a long name gets `min-w-0` and
  `truncate` (+ `title` for the full value) — an unbounded project name
  must never break a row.
- Hairlines come from the token (`border-border` is the global default);
  use `divide-y` over per-item borders; per component, pick border *or*
  ring, not both.

**Web, desktop, tablet.** The container-query system covers most of this
(a pane is a pane whatever the device — `AGENTS.md`), so the per-surface
checks are the residue containers can't express:

- **Web**: test at 200% browser zoom and a 360px-wide window — rem-based
  type and spacing must hold both.
- **Desktop (Tauri)**: the window can be any size. Enforce a minimum
  window size and persist bounds (gaps list); nothing critical lives at
  the window's bottom edge (HIG — users hide it); density can run higher
  than web defaults but targets never drop below 24×24px.
- **Tablet / touch**: gate hover-only affordances with
  `@media (hover: hover)` so touch never sticks in a hover state; the
  600–1100px band is where the split workspace must collapse gracefully;
  chat inputs keep ≥16px on iOS (`AGENTS.md` already pins this).

---

## Canon — one pattern per job

The survey found several jobs with two or more coexisting patterns. These
are the canonical choices; migrate the others when a change touches them.

| Job | Canonical | Retire on touch |
|---|---|---|
| Card | `rounded-xl border bg-card p-5` (the de-facto shape; restyle `ui/card.tsx` to it and adopt the component, which today has zero importers) | the four other hand-rolled shapes; `.connection-card` CSS |
| Busy indicator | `ui/spinner` (currentColor, `label` prop for `role="status"`) | `<Loader2 className="animate-spin">` — the fork that grew back after twelve were consolidated |
| Long-running agent work | `PipelineProgress` (ladder + rotating subtitle) | bare spinners on multi-second waits |
| Status badge | `ui/badge` with semantic tokens | `.status-pill` (lives in `ads-report.css`, hardcodes hexes, used far outside the report) |
| Destructive confirm | `ui/alert-dialog`: title quotes the object ("Delete \"Acme\"?"), body states scope + irreversibility, action button is verb + noun ("Delete project") in the *tinted* destructive style | the three `window.confirm` sites; the filled-red `bg-red-600` variant |
| Destructive action (the button that opens that confirm) | `Button variant="destructive"` — the tinted style above, already shipped: `bg-destructive/10 text-destructive`. Red **at rest**, not on hover: an action worth confirming is worth seeing before the pointer arrives. Pass `buttonVariants({ variant: "destructive" })` to `AlertDialogAction`, which defaults to the primary variant | hand-rolled danger links; pasting the class string inline; raw palette (`bg-red-600 text-white`) instead of the tokens, which cannot follow the theme; anything that is only red on `:hover` |
| Dialog actions | `DialogFooter` — bottom of the dialog, below the content they act on, destructive/secondary left and primary rightmost (it reverses to primary-first when the row stacks). Never mid-body | a hand-rolled right-aligned row anywhere above the content |
| Empty state (whole surface) | dashed panel: `rounded-xl border-dashed p-10 text-center`, `size-12` icon tile, `text-sm font-medium` title, `text-xs text-muted-foreground` body, verb-first `Button size="sm"` CTA | ad-hoc variants; pick this anatomy every time |
| Empty state (inside a stable layout) | one muted line in place (`DeskCards`) so the layout doesn't jump | — |
| First-run | the `DeskDayOne` pattern: labelled example data + a short checklist — "an empty board teaches nothing" | "No X yet" on a first-run surface |
| Inline error | `text-sm text-destructive` line with `role="alert"`, or the boxed `border-destructive/30 bg-destructive/5` variant for section-level failures | unlabelled error text (only 4 of 31 sites set `role="alert"` today) |
| Corner notification | the `UpdateToast` anatomy (fixed corner card, `role="status"`, renders null until it has something to say) — there is deliberately **no toast library**; don't add one | — |
| Loading a page | skeleton mirroring the loaded layout (the Desk pattern) when the shape is known; `Loading…` line for sub-second fetches | anonymous spinners for named work |

Empty states are onboarding surfaces (NN/g): show what the filled state will
look like or say exactly what to do, CTA verb-first ("Connect GA4", never
"Get started").

Loading states inform: for anything over ~1s, say what is happening
("Reading last 28 days of GSC…") — skeletons read faster than spinners, but
a sentence beats both when an agent is genuinely working (NN/g skeleton
research; Slack's "Hold tight, we're fetching your channels…").

---

## Layout & density

The container-query system, unit rules and the `@`-scale are in
[`AGENTS.md`](AGENTS.md) — enforced, not repeated here. On top of that:

- **Overview first, zoom and filter, details on demand** (Shneiderman).
  Every report surface names its three layers: the headline findings, the
  filter/scope affordance, and the drill-in. If one is missing the surface
  is either shallow or overwhelming. Prefer drill-in layers over cramming
  one screen (NN/g over Few on this contested point).
- **Progressive disclosure, two levels maximum** (NN/g). If a flow needs a
  third level of "advanced", restructure it.
- **Tables compare, cards browse** (NN/g data tables). A card grid where
  every card shows the same four metrics is a table wearing cards. Tables
  get sticky headers *inside their own scroll container*, tabular figures,
  and hover row-highlighting; one vertical scroll container per pane.
- **Every number carries a comparison.** A bare total is meaningless
  without a delta, benchmark, or trend beside it (Tufte: "a number is
  meaningless without a trend line"; Few's context mistake). Word-sized
  sparklines over big lonely tiles. Summarize by default — `$3.8M`, not
  `$3,848,305.93` — raw precision on demand.
- **Prose gets a measure.** 45–75ch (Bringhurst); the tokens exist
  (`--measure` 68ch / `--measure-tight` 56ch) but are almost never applied
  from JSX — chat transcripts and brief bodies in wide panes are the classic
  violation. Cap them.
- **The forgotten middle (~600–1100px)** is where split layouts break —
  Material puts two size-class boundaries inside that band. A
  `SplitWorkspace` pane at medium width drops to the single-pane toggle;
  test the band, not just phone-and-desktop.
- **The desktop shell remembers itself** (Apple HIG): minimum window size
  so nothing overlaps, persisted window bounds and pane-split ratios across
  launches. Tauri does none of this for free.
- **A conditional wrapper is not free in a `gap` layout.** `{cond && <div>{
  inner && <p/>}</div>}` renders an empty `div` whenever `inner` is false — and
  a flex/grid parent still gives that empty box a row and a full `gap` on each
  side. It reads as "mystery whitespace" and cannot be found by looking at the
  CSS, because the CSS is correct. Put the condition on the element that has
  the content, not on a wrapper around it, and measure the gap rather than
  adding margin until it looks right.
- **Spacing that arrives from two places is a bug even when each place is
  right.** A section with its own `padding-top` inside a body with its own
  `margin-top` sums silently; the first child of a container usually wants
  neither, because the container's edge already separates it.
- **Density is a desktop feature with a floor**: interactive targets never
  below 24×24 CSS px (WCAG 2.5.8). Denser than Material's touch defaults is
  fine here — Linear-dense, made tolerable by consistent spacing and muted
  color — but the floor is the floor.

---

## Not too texty

Users scan; they don't read — 79% scan any new page, and at most ~28% of
the words get read (NN/g eyetracking). So:

- **Halve the words.** Concise text measurably improves usability more than
  any other content change (Nielsen: "Be Succinct!"). One idea per surface;
  a brief that leads with three findings beats one that leads with twelve.
- **Front-load.** Headings, buttons and list items are judged by their
  first two words (NN/g) — "Google Ads settings", never "Settings for
  Google Ads".
- **Structure over prose.** Combine labels and values ("12 left in stock",
  not "In stock: 12" — Refactoring UI). "Sessions increased by 14% compared
  to last week" should be a value + delta chip + sparkline; prose is
  reserved for the *why*.
- Bold the keywords, chunk with headings, bullet the parallel things — the
  cure for the F-pattern is formatting, not more sentences.

---

## Voice & microcopy

The voice already exists in the app; this codifies it so new strings match.
It is **sentence case, second person, contractions, plain and declarative,
and it explains the consequence rather than naming the state**:

> "Nothing is waiting on you." · "No artifacts yet. Run an audit with your
> project selected and its report lands here." · "You're offline. Duct
> needs a connection. Your work is saved and will still be here." · "Duct
> checks a number before it trusts it."

Rules, checkable in review:

- **Sentence case everywhere.** Title Case only for product-name surfaces
  (Content Studio, SEO Audit).
- **Own the failure and give the next step.** "We couldn't reach GA4 —
  retrying in 30s", never "An error occurred" / "Request failed (500)"
  (Microsoft's style guide bans the passive phrasing outright). The
  existing `ConnectionBanner` copy is the model.
- **Tone maps to the user's state** (Mailchimp): playfulness is welcome in
  empty states, onboarding, and success moments; **errors, billing,
  data-loss and permissions copy stay straight-faced.** "If you're unsure,
  keep a straight face."
- **Buttons are terse verb(+noun)**: `Retry`, `Later`, `Delete project`,
  `Restart to update`. In-progress labels use the ellipsis character:
  `Saving…`, `Checking…`, `Working…`.
- **No setup sentences, no forced jokes** (Slack: "Get to the point";
  "write like you're having a conversation with one person").
- Apologize only for serious failures, once.

---

## Not AI slop

"Slop is design with no author" — the generated look comes from never
making a decision. The tells, and what this app does instead:

| Tell | Duct's corrective |
|---|---|
| Untouched shadcn violet primary | One brand accent used semantically (Known gaps: retire the violet at the token level) |
| Purple→indigo gradients, gradient text, glow orbs | Flat token colors; depth from borders and background shifts |
| Uniform `rounded-2xl shadow-lg p-6` card on everything, every element the same weight | One primary element per screen gets deliberate extra weight; whitespace and background shifts before borders; borders before shadows |
| ✨ sparkles on every AI feature, emoji as icons | AI-ness shown by behavior (the pipeline ladder, the phase line); lucide only |
| Badge/pill confetti | Pills only where they encode state |
| Centered-everything layouts | Left-aligned working layouts; asymmetric section rhythm |
| Generic copy ("Supercharge your workflow") | The founder-voice test: would you say it out loud? |
| Missing edge states | Every surface designs empty, loading, and error deliberately — these are the states scaffolds skip |
| Everything fades in uniformly | The motion budget above; delete anything that moves purely for decoration |

The meta-rule: the bottleneck is the judgment between generating a thing
and shipping it. That judgment is this file — run the checklist below
before calling a screen done.

---

## Screen review checklist

1. Squint (or blur): is the most important thing visibly heavier than the
   rest, or is everything the same weight?
2. Does every number carry a comparison (delta/sparkline/benchmark), with
   tabular figures, and a non-color channel on every up/down?
3. Read every string aloud: sentence case, contractions, would a smart
   coworker say it? Errors own the failure and give the next step?
4. Empty state teaches; loading state says what it's doing; error state has
   `role="alert"`.
5. Anything animating on a keyboard or high-frequency path? Cut it.
   Everything else ≤300ms, ease-out, transform/opacity, interruptible?
6. Tab through it: designed focus states, a keyboard path to every action,
   Enter submits the form.
7. Prose capped at a measure; tables scroll in their own container; no
   target under 24px.
8. Measure the whitespace you did not intend: any gap you cannot name the
   source of is two rules stacking or an empty conditional wrapper. Dialog
   actions in a `DialogFooter`, primary rightmost?
9. Drag the pane/window through the 600–1100px band: does the layout adapt
   or break?
10. Any raw hex, arbitrary `text-[Npx]`, or off-scale spacing? Token it.
11. Which canonical pattern (table above) does each element use — and if
    none, why does this job need a new one?

---

## Known gaps — close on touch

The tree, measured against this file. Fix each when a change touches it.

- **The violet `--primary` vs brand orange.** The default shadcn violet is
  the single most-cited "generated app" tell, and it isn't Duct's color.
  Recommended: re-token `--primary` to the brand orange (proper oklch
  light/dark pair, desaturated in dark) in `tokens.css`/`theme.css` — one
  change, every component inherits. Until then: `bg-primary` in code, no ad
  hoc `bg-[var(--orange)]`.
- **Semantic success/warning tokens exist now; most sites still don't use
  them.** `--success` / `--warning` (+ foregrounds) live beside
  `--destructive` in `tokens.css`/`theme.css`, and `connector-tiles.css` is
  migrated. Everything else still re-picks greens and ambers
  (`text-green-500`, `text-amber-600`…) with hand-managed dark partners, and
  `contentStatus.js` + `AuditStepProgress` remain two independent maps —
  migrate on touch. The hand-picks are not merely inconsistent: the common
  `#eab308` measures **1.9:1** on a light background, so any of them used as
  label text fails AA. The tokens are picked for it (light 4.96:1 / 4.56:1,
  dark 9.18:1 / 7.74:1 on `--card`).
- **`ui/card` has zero importers** while five card shapes coexist — restyle
  it to the canonical shape, then adopt it.
- **`Loader2` spinners (7 files)** → `ui/spinner`.
- **`.status-pill`** → `ui/badge`; move its colors to tokens. The
  `components/connections/` surfaces are migrated (they now use `ui/badge` or
  a glyph); the rest of the 8 files are not.
- **`window.confirm` (3 sites)** → `ui/alert-dialog`.
- **Off-scale type.** `npm run check:type` enforces the two-size rule above:
  font sizes must land on Tailwind's scale, and files on its clean list can
  never regress. It runs inside `check:parity`, so CI has it. Currently clean:
  `base`, `connector-tiles`, `forms`, `layout-grids`, `mode-selector`,
  `theme`, `tokens`, `typography`. Still owing, and reported on every run:
  `ads-report` (15), `generate` (14), `model-tiers` (9), `signin` (7),
  `chat` (5), `connections` (1), `app-shell` (1). Clean a file, add it to
  `CLEAN` in the script. Separately, ~300 arbitrary px type values in JSX
  (`text-[10px]` ×88, `text-[11px]` ×77…) contradict the rem rule in
  `AGENTS.md`, as does heavy inline `style={{}}` spacing in `execute/page.jsx`
  and `AuditReportV1.jsx` — neither is covered by the script yet.

  The rule needed a guard because prose could not hold it: `connector-tiles.css`
  grew **six** sizes between 10px and 16px while this file said "do not invent
  intermediate sizes", and the result was a section heading rendering *smaller*
  than the field label nested inside it — hierarchy inverted, which reads as
  visual noise long before anyone can name the cause.
- **Hardcoded hexes in JSX and CSS**: `AuditReportV1` score ramp,
  `ArtifactRenderer` chart colors (use `--chart-1..5`), `themes.js`, and
  `ads-report.css`, which bypasses the token layer entirely and is
  effectively light-only.
- **`.measure` never reaches JSX** — prose in React components is uncapped.
- **Forms never set `aria-invalid`/`aria-describedby`** even though the
  primitives style for them; only 4 of 31 inline-error sites have
  `role="alert"`.
- **`prefers-reduced-motion` gates only the logo** — the
  `animate-pulse`/`ping`/`bounce` sites are ungated.
- **The desktop shell does not persist window bounds** or enforce a
  minimum size (HIG expectation; pane ratios are already persisted).
- **`.app-subtle` (~55 uses)** → `text-sm text-muted-foreground` as files
  are touched; note it silently applies a measure.

---

## Sources

NN/g (delight theory, empty states, skeletons, progressive disclosure,
complex apps, dashboards & preattentive processing, data tables, sticky
headers, icon usability, F-pattern & succinct writing) · Apple HIG (windows,
layout) · Material 3 (window size classes, dark theme) · WCAG 2.2
(1.4.1, 1.4.3, 1.4.11, 2.5.8) · Refactoring UI · Emil Kowalski, "Great
Animations" · Rauno Freiberg, interfaces.rauno.me · Linear Method · Family
values (benji.org) · Slack, Mailchimp, Microsoft voice guides · Dan Saffer,
*Microinteractions* · Tufte on sparklines · Shneiderman, "The Eyes Have It"
· Every Layout · Josh Comeau on pixels & accessibility · Ahmad Shadeed on
container queries · mania.design "Spot the Slop" and related 2025–26
writing on generated-looking UI.
