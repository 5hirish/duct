# Black text on a red button

**Author:** Shirish Kadam · **Date:** 2026-09-06

The status tokens are correct. Three of them are also unreachable, because the theme never names them — and a token nothing can reference is indistinguishable from one that was never added.

**Scope** app/ (Next.js), main @ db4f295 · **Method** token math + live probe + grep · **Status** findings only, nothing changed

## The short version

Duct's token *values* are sound. Every status pair measures 4.5:1 or better in both themes, including the ones the recent design pass added. What is broken is the wiring and the adoption: three colours the theme defines cannot be referenced from a class at all, and the two newest tokens have two uses in the whole app, both on the preview page. Every failure that reaches a user happens *off* the tokens.

3status colours whose `-foreground` is defined but never mapped, so the utility is never generated.2uses of `--success`/`--warning` in JSX, both in `preview/TokenSheet.jsx`. In real UI, none.179uses of `text-[Npx]` at 11px or smaller, on top of a two-size type system.332raw palette colour classes in JSX; 15 files carry them with no `dark:` at all.

**The headline, because it is invisible from the code.** The `@theme inline` block in `theme.css` maps `--color-destructive`, `--color-success` and `--color-warning`. It maps none of their `-foreground` partners. Tailwind v4 generates utilities only from what that block names, so `.text-destructive-foreground`, `.text-success-foreground` and `.text-warning-foreground` are never emitted. Ten other `-foreground` pairs in the same block *are* mapped, which is exactly why nothing looks wrong when you read the file.

**What that does to the Stop button.** `workspace/ChatInput.jsx:153` paints `bg-destructive text-destructive-foreground`. The background applies, the text colour silently does not, and the label falls back to the page foreground: near-black on red in light (3.13:1), near-white on a light coral in dark (2.77:1). Both fail. The live probe confirms the cause and not just the symptom: `.bg-destructive` is in the served stylesheet, `.text-destructive-foreground` is absent from it.

**Why the earlier fix did not land.** The design pass correctly caught that `.dark` was inheriting a white `--destructive-foreground` written for a light-mode red, and darkened it to `oklch(0.14 0.03 22)`, which measures a clean 6.91:1. That value is right, and it is read by nothing. A token with no mapping is indistinguishable from a token that was never added — which is the argument for the CI check in phase 05.

Light · real token values

Stopas shipped · 3.13:1Stopwhat the class meant · 6.02:1StopSendwhat ui/button renders · 5.52:1 / 5.90:1posteddraftWARNPostCard badges 2.2:1 / 2.1:1 · 10px sidebar pill 2.9:1

Dark · real token values

Stopas shipped · 2.77:1Stopwhat the token now says, if the class existed · 6.91:1StopSendwhat ui/button renders · 3.16:1 (large only) / 7.77:1

Rendered with the app's oklch values, not screenshots, so the swatches stay honest across theme changes to this page. Numbers are WCAG 2.x contrast ratios computed from the same values.

## What I measured

- **Token pairs.** Every foreground/background pairing the theme defines, in `:root` and `.dark`, converted oklch → linear sRGB → WCAG relative luminance. Alpha tints (`/10`, `/15`, `/70`) composited over the real background first.
- **Palette classes.** Every Tailwind colour utility that appears in `src/`, measured against both theme backgrounds using Tailwind v4's own oklch values from `node_modules/tailwindcss/theme.css`.
- **Hex in CSS.** The 37 literals in `ads-report.css` and the handful in `generate.css`, `connector-tiles.css`, `signin.css`.
- **Live probe.** Playwright against the running dev server on :3003: injected the shipped class strings into a page, read computed colours, checked which utilities exist in the served stylesheet, screenshotted light, dark, 375px and 1024px. Screenshots live in the gitignored `.playwright-mcp/`, so they are described, not embedded.
- **Grep census.** Primitive versus raw element counts, type-size distribution, radius distribution, breakpoint prefixes, fixed widths, focus handling, motion.

### Token pairs, both themes

| Pair | Light |  | Dark |  | Where it bites |
| --- | --- | --- | --- | --- | --- |
| foreground / background | 18.83 | pass | 18.96 | pass | body text |
| muted-foreground / background | 7.77 | pass | 7.63 | pass | secondary text, placeholders |
| primary-foreground / primary | 5.90 | pass | 7.77 | pass | default Button, Send |
| primary as text / background | 5.90 | pass | 7.47 | pass | links, link variant |
| foreground / destructive | 3.13 | fail | 2.77 | fail | **the Stop button as shipped** |
| destructive-foreground / destructive | 6.02 | pass | 6.91 | pass | correct values, unreachable — the utility is never generated |
| success-foreground / success | 4.54 | pass | 8.55 | pass | same: no `--color-success-foreground` mapping |
| warning-foreground / warning | 4.93 | pass | 9.92 | pass | same: no `--color-warning-foreground` mapping |
| success, warning as text / background | 4.54 / 4.93 | pass | 8.53 / 10.10 | pass | these two *are* mapped and usable; 2 uses app-wide |
| destructive / destructive-10% tint | 5.52 | pass | 4.32 | large only | Button + Badge destructive variant |
| destructive-20% tint (dark variant) | — |  | 3.16 | large only | dark destructive Button at 14px |
| destructive/70 / background | 2.40 | fail | 5.09 | pass | `AuditStepProgress.jsx:186,193` |
| border, input / background (3:1 non-text) | 1.27 | fail | 2.88 / 3.82 | border fails | input boundaries rely on border alone (WCAG 1.4.11) |
| select chevron #9ca3af / background | 2.54 | fail | 7.80 | pass | global `select` reset in `theme.css` |
| brand orange #ff5c00 as text | 3.10 | large only | 6.39 | pass | AuditReportV1 "Unblock", footer "Duct" |
| chart-3, chart-5 / background | 2.59 / 1.89 | fail | 2.54 / 1.31 | fail | chart series against the canvas |
| disabled Send (opacity 40%) | ≈1.7 | exempt | 4.41 | large only | reads as broken rather than disabled |

## Colour contrast

Ordered by how many people see it. The threshold is WCAG 2.2 AA: 4.5:1 for text under 24px (18.66px bold), 3:1 for large text and for UI component boundaries.

### C1 · The Stop button, and the mapping that is missing

Covered above. Three things are wrong at once and each is worth naming separately, because the branch that already looked at this fixed only one of them:

1. `theme.css` maps every shadcn colour except `--color-destructive-foreground`. Nothing in the cascade generates the utility. This is the root cause and a one-line fix.
2. `.dark` never overrides `--destructive-foreground`. Dark `--destructive` is a light coral (L 0.704) designed to be read *as text* on a dark canvas; white on it is 2.89:1 even once the class exists.
3. The two chat inputs hand-roll their buttons (`rounded-md`, custom padding) instead of using `ui/button`, so they neither get the primitive's focus ring, active state and disabled treatment nor follow the destructive variant when it changes.

### C2 · Solid status chips with white text

This is the "green and yellow shades make the white text hard to read" observation, and it is measurable:

| Where | Classes | Ratio |  |
| --- | --- | --- | --- |
| `PostCard.jsx:22` | `bg-green-500/90 text-white` · "posted" | 2.22 | fail |
| `PostCard.jsx:24` | `bg-amber-500/90 text-white` · "draft" | 2.15 | fail |
| `PostCard.jsx:23` | `bg-sky-500/90 text-white` · "scheduled" | 2.71 | fail |
| `PostCard.jsx:25` | `bg-rose-500/90 text-white` · "discarded" | 3.76 | large only |
| `AuditWorkspace.jsx:484`, lead page CTA | `bg-orange-600 text-white` | 3.59 | large only |
| site buttons (for reference) | white on brand `#ff5c00` | 3.10 | large only |

Mid-lightness greens and ambers cannot carry white text at 12px. Nothing in the Tailwind 400–600 range of those hues does: white on green-600 is 3.22:1, on amber-600 3.19:1, on yellow-400 1.57:1. The system already has the right answer in the destructive variant: **tint the background, colour the text** (`bg-x/15 text-x-700`) which passes at 4.5–4.7:1 in light. What it lacks is a success and a warning token to do it with, so every file re-picks a hue.

### C3 · Palette colours used as text in light mode

Counts are bare uses, not `dark:`-prefixed ones. The dark-prefixed 400s are fine in dark; the problem is the 500s that are the light-mode value.

| Class | Light ratio |  | Uses | Files |
| --- | --- | --- | --- | --- |
| `text-green-500` | 2.22 | fail | 11 | AuditStepProgress (HTTP 2xx, canonical ✓), contentStatus, workspace/Todos, PipelineProgress, InsightsWorkspace, AccountsTab, StyleGallery |
| `text-amber-500` | 2.15 | fail | 5 | AuditStepProgress (3xx), contentStatus "Draft" |
| `text-sky-500` | 2.71 | fail | 3 | AnalyticsView, lead page |
| `text-orange-500` / `-400` | 2.89 / 2.38 | fail | 3 + 3 | InsightsWorkspace, lead page |
| `text-amber-600` | 3.19 | large only | 10 | sidebar "v3 only" pill at 10px, AuditStepProgress warn pill, AppSidebar |
| `text-green-600` | 3.22 | large only | 7 | AppSidebar permission "granted", AuditStepProgress ok pill |
| `text-blue-500`, `text-rose-500` | 3.76 | large only | 7 + 4 | spinner tint, contentStatus "Discarded" |
| `text-amber-700`, `text-green-700`, `text-red-700` | 5.05 / 4.94 / 6.42 | pass | 7 + 3 + 6 | the pill text colours, which are right |

The "large only" rows matter because none of these are large text. Most are 10–12px, where the requirement is 4.5:1 and the practical need is higher.

### C4 · Light-only hex that inverts badly in dark

| Where | Value | Light | Dark |  |
| --- | --- | --- | --- | --- |
| `AuditReportV1.jsx:418` | `text-[10px] text-[#6b7280]/70` | 2.26 | — | fail at 10px |
| `AuditReportV1.jsx:421` | `text-[11px] text-[#6b7280]/50` "Nothing here" | 1.66 | — | fail |
| `AuditReportV1.jsx:937` | footer `rgba(13,15,26,.3)` | 1.40 | — | fail |
| `AuditReportV1.jsx:428,450` | `text-[#1a1a1acc]` finding titles | 4.07 | 1.11 | invisible in dark |
| `ExecutionOffer.jsx:236` | `bg-white text-[#1a1a1a]` dialog | ok | white card in a dark app | light-only |
| `ads-report.css:180` | `.kpi-trend.tone-yellow #ca8a04` on white | 2.94 | — | fail |
| `ads-report.css:181` | `.kpi-trend.tone-green #16a34a` on white | 3.30 | — | large only |
| `generate.css:347` | `#166534` on green 22% over `--card` | 6.05 | 1.25 | fail in dark |
| `ads-report.css:33-35, 222-224` | `.rpt-verdict`, `.signal-pill` pastel pills | 5.3–6.5 | pastel islands | light-only |

`ads-report.css` carries 37 hex literals and hard `#fff` rows in `.camp-table` and the KPI chips. It is a light-mode report living inside a themed app. Either it declares `color-scheme: light` and owns that decision, or it moves to tokens. Half-way is what produces a white table on a dark page.

### C5 · Non-text contrast

- Light `--border` and `--input` are 1.27:1 against the background. Inputs whose only boundary is that border fail WCAG 1.4.11 (3:1). The `.app-input` rule adds a 50% `--input` fill, which helps, but that class has no users in JSX any more; the shadcn `Input` does not fill.
- The global `select` chevron is hard-coded `#9ca3af`: 2.54:1 in light. It should be `currentColor` or `--muted-foreground`.
- `--chart-3` and `--chart-5` sit at 2.6:1 and 1.9:1 against the canvas in light. Chart marks are exempt from the text rule but adjacent-series separation still wants 3:1.

## Component harmony

A design system is only the parts people reach for. Here is what they reach for instead.

### H1 · Two button systems

121 raw `<button>` in 49 files against 137 `<Button>` in 42. The raw ones each re-derive shape: `rounded-md` (Stop, Send, the "That turn failed" retry), `rounded-full` (scroll-to-bottom), plain text (the memory chips). The primitive is a pill (`rounded-4xl`). The same viewport shows a pill Send in the sidebar and a rectangular Send in the chat bar. Worst offenders: `PostViewport` (8), `AuditChat` (7), `ContentChat` and `ExecutionOffer` (6 each), both inputs (4 each).

The primitive also has a gap that invites the fork: no solid destructive. If a solid red Stop is wanted, add a variant; if not, the tint is the answer and the call sites should say `variant="destructive"`. Either way it is a system decision, not a per-file one.

### H2 · Nine corner radii

`rounded-full` 136, `-md` 70, `-xl` 65, `-lg` 58, bare `rounded` 44, `-2xl` 26, `-3xl` 12, `-sm` 5, `-4xl` 4. Button is 4xl, Badge and Input are 3xl, cards are xl, chat bubbles are a hand-written `10px 10px 2px 10px`, the Stop button is md. Three steps would cover it: control (pill), container (xl), inset (md).

### H3 · Three vocabularies for one status

"Success" is `text-green-500`, `-600`, `-700`, `emerald-400`, `emerald-600`, `#16a34a`, `#166534` or `#4ade80` depending on the file. "Warning" is amber-400 through amber-800, `#eab308`, `#ca8a04` or `#854d0e`. Eight hues for four meanings, 332 palette classes in total.

The tokens to end this now exist and are correct. They are used twice, both on the preview page. `execute/page.jsx:200` is the tell: it writes `color: "var(--warning, #b98900)"` as an inline style with a hardcoded fallback. The fallback was necessary when it was written and is dead now, but the inline style still bypasses the token layer — and because `--color-warning-foreground` is unmapped, the author could not have used a class for the paired text colour even if they had wanted to.

### H4 · Pills

`.status-pill` (28 uses, defined in `ads-report.css`), `<Badge>` (19), and ad-hoc `inline-flex rounded-full px-1.5 py-px text-[10px]` spans in `AppSidebar:538`, `AuditStepProgress:40`, `ChangeSetCard:139`, `PostCard:22`. Four pill shapes, three text sizes, no shared colour map.

### H5 · Spinners came back

`ui/spinner`'s own docblock says twelve hand-rolled rings were consolidated into it. Since then `Loader2` has crept back in 17 places (`ProjectMembers` ×4, `invite` ×2, `UpdateToast`, `DiscoverPage`) against 12 `<Spinner>`. Consolidation without a lint rule is a snapshot.

### H6 · The rest of the forks

- `window.confirm` ×3 and `window.alert` ×1 (`AuditChat.jsx:103` among them) beside `AlertDialog` in 4 files.
- Three hand-rolled `role="switch"` toggles with `bg-white` knobs in `audit/seo/page.jsx`; `ui/switch` used once elsewhere.
- Native `<select>` ×5 against `<Select>` ×15; the natives get the hard-coded grey chevron.
- `execute/page.jsx` has 68 inline `style={{}}` objects with `fontSize: 12`/`13` and hex fallbacks. It is a page written outside the system; `GoogleAdsReport.js` is the same.
- 61 `title=` tooltips and 10 `data-tooltip` attributes versus 19 `<Tooltip>`. Title tooltips do not exist on touch or keyboard.

### H7 · Focus is inconsistent

19 `focus:ring` (fires on mouse click too) versus 34 `focus-visible:ring` outside the primitives, and 17 elements with `outline-none` and no `focus-visible` replacement at all, 5 of them in `audit/seo/page.jsx`. Those are keyboard dead spots (WCAG 2.4.7). The primitives get this right; the raw elements are the leak.

### H8 · Three accents in one viewport

Sidebar logo dot: brand orange. Buttons and links: shadcn violet `--primary`. Sidebar "v3 only" pill: amber. The 1024px screenshot has all three in the first 300px. This is the open orange-versus-violet decision from the earlier design pass, still open, and it is the one harmony call that a token change cannot make for you.

## Text readability

### R1 · The unofficial third and fourth type sizes

The system is two sizes: `text-sm` body (229 uses) and `text-xs` secondary (271). Beside them: `text-[10px]` 86, `text-[11px]` 75, `text-[9px]` 5, `text-[8px]` 2, and the rest at fractional pixel sizes (11.5, 12.5, 13.5). 228 arbitrary sizes in total, 179 at or below 11px. Ten-pixel text is as common as the official secondary size. The CSS partials add 17 more `font-size` declarations at 10–11px.

Concentrated in `AuditStepProgress` (29, including 10px monospace URLs and 10px `<pre>` blocks), `AuditReportV1` (27), `DeskDayOne` (18), `FormatLibrary` (16), `DiscoverPage` (15). The sidebar's "v3 only" is 10px mono at 2.9:1, a size failure and a contrast failure on the one label that explains why a nav item is disabled.

There is no WCAG minimum font size, but every platform guideline lands in the same place: Apple's floor is 11pt, Material's 11sp, and 12px is the practical floor for anything a user must act on. A `text-2xs` token at 11px for genuinely decorative labels, and a rule that nothing interactive or informational goes below `text-xs`, would replace all 232.

### R2 · Small and faint together

The worst cases stack both: `text-[10px] text-[#6b7280]/70` (2.26:1), `text-[11px] text-[#6b7280]/50` (1.66:1), the report footer at 1.40:1. Opacity on already-muted text is the pattern to ban; `--muted-foreground` is 7.8:1 for a reason and halving it is not a lighter shade, it is illegible.

### R3 · Measure

`--measure` (68ch) and the `.measure` utility exist and are used once in JSX. `Desk.jsx:190` and `DeskDayOne.jsx:96` use `max-w-[640px]`/`[660px]` instead, which stops following the font when the user resizes text. Report bodies inside `SplitWorkspace` have no cap at all on a wide pane.

### R4 · Heading scale is ad hoc

`h1–h3` elements carry `text-2xl` (17), `text-xl` (7), `text-lg` (7), `text-sm` (12), `text-xs` (6) and `text-[13px]` (5). A heading at 12px is a label wearing a heading tag, which is bad for screen readers and for the visual hierarchy. Three heading sizes, mapped to the three levels, would end the drift.

## Theme adaptability

### T1 · The dark theme is a different brand

Light is warm and tinted: neutrals at hue 80, foreground a navy at hue 265, sidebar off-white. Dark is stock shadcn: every neutral at zero chroma. The sign-in hero uses the brand navy `#0d0f1a`; the dark app behind it uses neutral `oklch(0.145 0 0)`. The two do not read as one product. A dark palette that keeps the light theme's hue (dark navy surfaces, warm-grey text) is a token-only change.

### T2 · Fifteen files with no dark variant

Files that use palette colours and contain zero `dark:`: `PostCard` (14 palette classes), `ExecutionOffer` (14, and a `bg-white` dialog), `AuditWorkspace` (7), the lead-magnet page (7), `AnalyticsView` (6), `SlidesCarousel` (5, `bg-white` slide frame), `CodeBlock`, `workspace/Todos`, `BrandContextForm`, `AccountsTab`, `InsightsWorkspace` and five more. `InsightsWorkspace.jsx:337` and `ArtifactRenderer.jsx:255` render a 74vh iframe with a hard white background, which is a white flash on every dark-mode report load.

The reason this keeps happening: with only `destructive` as a status token, any success or warning colour *must* be a palette pick, and a palette pick needs a hand-managed dark partner. Add the tokens and the `dark:` pairs stop being the author's job.

### T3 · Motion ignores the OS preference

53 `animate-pulse`/`animate-spin`/`transition-all` utilities, zero `motion-reduce:` variants. The CSS partials gate only the logo mark, smooth scroll, and three component animations behind `prefers-reduced-motion`. The two pulsing "you have something to see" dots in `SplitWorkspace` are exactly what WCAG 2.3.3 is about.

### T4 · Small things that follow from the above

- `.dark` is missing `--destructive-foreground` (C1) and would be missing `--success-foreground`/`--warning-foreground` if the tokens were added without them.
- `CodeBlock.jsx:47` paints a fixed `#21252b` header in both themes. Intentional as a "code is always dark" surface, but it should be a token so it can be revisited.
- `GoogleSignInButton` hard-codes Google's dark button hexes. That is Google's brand spec and is fine; it is the one legitimate hex island.

## Responsiveness

The container-query convention from the earlier desktop review is real and mostly honoured: 67 `@`-variants against 41 viewport prefixes, and almost all of the 41 are the legitimate cases the app guide lists (sign-in, the pane toggle, the sidebar sheet, `md:text-sm`). What remains:

### S1 · Fixed two-column grids that never collapse

`audit/seo/page.jsx:272` is `grid grid-cols-2` with no container variant. At 375px the live probe shows "Business name" and "Primary content type" squeezed side by side and the select's own placeholder truncated to "Select typ". Same pattern in `PreferencesDialog.jsx:231` and `AuditStepProgress.jsx:206` (two columns of 10px text).

### S2 · Viewport prefixes inside container regions

`DeskLists.jsx` uses `sm:` seven times to add and hide list columns. It renders inside `.app-main`, which is a container: with the sidebar open at a 1024px window the content region is roughly 740px, so `sm:` fires at the wrong width. This is the exact trap `app/AGENTS.md` documents. Smaller leaks: `ProjectMembers` (2), `content/page` (2), `DeskCards`, `DeskDayOne`, `projects/page`, `execute/page` (1 each).

### S3 · iOS zooms the audit form

The chat textareas carry `text-base md:text-sm` precisely so iOS Safari does not zoom a sub-16px field on focus. The SEO audit form's inputs (`audit/seo/page.jsx:269` and siblings) are plain `text-sm`, so every field on that page triggers the zoom. The shadcn `Input` primitive already has the fix built in; these are raw `<input>` elements (27 raw against 31 primitives app-wide).

### S4 · Fixed heights

- `.chat-sidebar { height: 520px; position: sticky; top: 5rem }` in `chat.css`. On a 700px-tall laptop viewport the input row sits at the fold; on anything shorter it is below it, and sticky keeps it there.
- `h-[48vh]` editor panes in `FormatLibrary` ×2, `h-[74vh]` report iframes ×2, `h-[460px]`, `h-[220px]`, `max-h-[520px]`. Viewport-fraction heights inside a resizable pane size off the window, not the pane.
- `.app-shell { min-height: 100vh }` in `base.css:13` (and `signin.css:7`) beside the `min-h-dvh` used elsewhere. On iOS Safari `100vh` is taller than the visible area; the shell should use `dvh` like the rest.

### S5 · The connection banner covers content

`ConnectionBanner` is `fixed bottom-0` with no bottom padding reserved on the page. At 375px it covers the last form fields; at 1024px it sits over the sidebar's theme toggle and account row. A `padding-bottom` on the scroll container while the banner is mounted, or a top-of-page placement, fixes both.

### S6 · The overflow guard hides regressions

`body { overflow-x: hidden }` in `theme.css`. Both live probes measured `scrollWidth` below `innerWidth`, so nothing overflows today. But the guard means the next component that does will be clipped silently rather than caught in QA. Remove it and let overflow be visible in development.

### S7 · What passes

- Tap targets: no raw button under 24px; primitive `xs` and `icon-xs` are 24px, the WCAG 2.5.8 floor.
- `SplitWorkspace`: keyboard-resizable divider, pane toggle on mobile, both panes are containers. The 375px insights screenshot from the September 5 smoke run shows the shell behaving.
- The sidebar sheet, the sign-in split, the page toolbars all wrap correctly at 375px.
- Tables: 9 `<table>` elements, 21 `overflow-x-auto` wrappers.

## What already landed, and what this adds

The September design pass — `app/DESIGN.md`, the preview shell, the status tokens — is on `main` now. Its *Known gaps* section is a real, honest list and it overlaps this review deliberately. What follows is only the part that list does not already carry, so the two documents can sit beside each other without contradicting.

| Item | State on main | What this review adds |
| --- | --- | --- |
| `--success` / `--warning` + foregrounds, both themes | landed | Measured: 4.54:1 and 4.93:1 light, 8.55:1 and 9.92:1 dark. The values are good. Adoption is 2 uses, both in `preview/TokenSheet.jsx`. |
| `.dark --destructive-foreground` → `oklch(0.14 0.03 22)` | landed | 6.91:1, and unreachable. See the next row, which is the finding. |
| `--color-*-foreground` mappings for destructive, success, warning | missing, all three | **Not on the gaps list.** Without them the three utilities are never generated, so the two rows above are cosmetic. This is the one defect that makes the others unfixable by the intended means. |
| `check:type` guard on CSS font sizes, in `check:parity` | landed | Covers the CSS partials. The 228 JSX `text-[Npx]` arbitraries are outside it, as the gaps list notes; 179 of them are 11px or below. |
| Four forked destructive AlertDialog call sites | fixed | Four of what is now 121 raw buttons. The pattern is unchanged. |
| Contrast numbers for the new tokens | cited on `--card` | This review measures against `--background`, so the figures differ slightly from DESIGN.md's and neither is wrong. The full matrix in §What I measured is new. |
| Responsive behaviour | not covered | §Responsiveness is entirely new: the grids that never collapse, the viewport prefixes inside container regions, the iOS zoom on the audit form, the banner that covers content. |

The practical consequence: the mapping fix is three lines and it unblocks the migration the gaps list is already asking for. Do it before the per-file colour work, not after.

## Recommended order

Smallest change with the widest blast radius first. Each phase is independently shippable.

01

### Close the exits in the theme

One PR, tokens only, no component edits.

- Map `--color-destructive-foreground`, `--color-success-foreground` and `--color-warning-foreground` in `theme.css`'s `@theme inline` block. Three lines. The values are already correct in both themes; nothing else in this list works until the utilities exist.
- Give `.dark` a brand-tinted neutral ramp (hue 265, low chroma) so it is the same product as light (T1).
- Raise light `--border`/`--input` to 3:1 or give `Input` a fill (C5). Replace the select chevron hex with `currentColor`.
- Decide the accent: orange `--primary` or violet. Whichever, it should be one (H8).
02

### Fix the visible failures

Now that the tokens exist, the four things a user notices.

- Stop button: `<Button variant="destructive">` in both inputs (or the merged `ChatInput`). Decide solid versus tint once, in `button.tsx`.
- PostCard status badges and every `bg-x-500 text-white` chip: tinted background, 700-weight text, via `Badge` variants `success`/`warning`.
- `text-green-500`/`text-amber-500` as text: swap to `text-success`/`text-warning`. Twelve and five sites.
- `AuditReportV1` and `ExecutionOffer`: replace the hex and `bg-white` with tokens, or wrap in `color-scheme: light` and own it.
03

### Type floor and primitive adoption

- Add `text-2xs` (11px) as the only sub-`xs` size; sweep the 228 arbitraries to `xs` or `2xs`. Nothing interactive below `xs`. Ban opacity on `text-muted-foreground`.
- Three heading sizes bound to `h1`–`h3` in `typography.css`.
- Replace `Loader2` with `Spinner`, `window.confirm` with `AlertDialog`, the three hand-rolled switches with `Switch`, raw inputs on the audit form with `Input` (which also fixes S3).
- Radius scale to three steps; chat bubbles onto it.
04

### Responsive and motion

- Container variants on the three fixed grids (S1); `@sm:` instead of `sm:` in `DeskLists` and the six smaller leaks (S2).
- Reserve space for `ConnectionBanner` (S5); `dvh` in `.app-shell`; drop the body overflow guard (S6).
- `motion-reduce:` on the pulse dots and spinners, or a single global rule in `base.css` (T3).
- Focus: `focus-visible` everywhere `focus:` or bare `outline-none` appears (H7).
05

### Keep it closed

Every one of these findings had been fixed once before somewhere in the tree. What was missing was a check.

- An ESLint rule (or a test over the source, like `test_harness_boundaries.py` on the backend) that fails on `text-[Npx]`, raw palette colour classes outside an allowlist, `Loader2`, `window.confirm`, hex in JSX, `sm:`/`md:` outside the allowlisted files.
- The contrast script from this review, run in CI over `tokens.css` and `theme.css`, so a token edit that drops a pair below 4.5:1 fails the build.
- Move `ads-report.css`'s hex to tokens or mark the file `color-scheme: light` so the exception is declared rather than accidental.

## Sources

- WCAG 2.2: 1.4.3 Contrast (Minimum), 1.4.11 Non-text Contrast, 2.3.3 Animation from Interactions, 2.4.7 Focus Visible, 2.5.8 Target Size (Minimum). [w3.org/TR/WCAG22](https://www.w3.org/TR/WCAG22/)
- WCAG relative luminance and contrast ratio definitions, used verbatim in the measurement script.
- Tailwind CSS v4 theme variables and the `@theme inline` namespace rules; the shipped oklch palette in `tailwindcss/theme.css`.
- Apple Human Interface Guidelines, Typography (11pt minimum); Material Design 3, Type scale (11sp label small).
- Material Design dark theme guidance on desaturating and lifting status colours for dark surfaces.
- [2026-09-01-desktop-adaptive-ui-review.html](2026-09-01-desktop-adaptive-ui-review.html) in this folder, for the container-query convention this review checks against.
- `app/DESIGN.md` on `main`, in particular its *Known gaps — close on touch* list, which this review complements rather than restates.
Measured 2026-09-06 against `main` at db4f295 with the dev server on :3003 and no backend. Contrast values come from a small Node script that parses the token files and Tailwind's palette; it lives with the session, and the recommendation in phase 05 is to make it a CI step. Screenshots from the live probe are in the gitignored `.playwright-mcp/` folder and are described rather than embedded, so this file stays text.
