# Performance review: the findings

**Author:** Shirish Kadam · **Date:** 2026-10-28

The rows behind [`2026-10-28-performance-review.md`](2026-10-28-performance-review.md). Read that first; open this when fixing something. Paths are relative to `app/src/` or `desktop/` as the section says, at `a116370b` on `main`.

**Status:** *Fixed* landed on `perf/client-load-and-shell-review`. *Open* is the backlog, ranked within each table.

## Web: first load

| # | Finding | Evidence | Fix | Effort | Status |
|---|---|---|---|---|---|
| W1 | Every route server-renders "Starting Duct…" and nothing else; the first real pixel waits for all the JavaScript | `components/LocalBackendGate.jsx` renders a placeholder until an effect runs; all six route groups wrap it | Make each request await the backend base instead of gating the tree, so routes render on the server. Front door and `/start` first | M | Open |
| W2 | The whole English (or Japanese) catalogue, about 120 KB, is inlined into every HTML response | `app/layout.js` passes `initialMessages={i18n.messages}` | Load the catalogue as a cached per-locale chunk, read with `use()` in the provider | M | Open |
| W3 | Recharts loaded with every artifact card, brief and content hub | `components/artifacts/ArtifactRenderer.jsx`, `app/(app)/content/page.jsx`, `components/audit/AuditReport.jsx` | Lazy chart and report views; lazy Analytics and Discover tabs | S | Fixed |
| W4 | All ~45 Prism themes shipped with every chat route, eagerly | `components/workspace/CodeBlock.jsx` imported `dist/cjs/styles/prism` (the index) | One theme by path; highlighter in `HighlightedCode.jsx`, loaded on the first code block | S | Fixed |
| W5 | `modern-screenshot` in every content workspace's first load | `lib/slideCapture.js` | Imported inside the capture | S | Fixed |
| W6 | The code font is preloaded on every first visit | `app/layout.js` | `preload: false` | S | Fixed |
| W7 | Sentry traced 50% of sessions and profiled every traced one | `instrumentation-client.ts`, both server configs | `TRACES_SAMPLE_RATE` in `sentry.sampling.ts`: 10% in production, all three runtimes | S | Fixed |
| W8 | One 260 KB stylesheet (41 KB compressed, render-blocking) carries every page's partials on every route, the `/preview` lenses included | `app/globals.css` imports 22 partials | Move page-only partials (connector tiles, model tiers, ads report, onboarding) beside their pages | M | Open |

## Web: long sessions

| # | Finding | Evidence | Fix | Effort | Status |
|---|---|---|---|---|---|
| L1 | Each streamed token re-rendered and re-parsed every settled reply; a 1 Hz clock did the same | `components/workspace/AgentChat.jsx` rows were not memoised | `memo` on `TranscriptRow` and `ActivityGroup`, stable retry handle, grouping memoised | M | Fixed |
| L2 | A brief open beside the chat was re-parsed on every chat token | `MarkdownView` in `ArtifactRenderer.jsx` | `memo`, plugin list hoisted | S | Fixed |
| L3 | A streaming brief repainted per chunk, re-parsing all text so far | `components/insights/InsightsWorkspace.jsx` | Throttled to 10 repaints a second | S | Fixed |
| L4 | The audit report stream was debounced, so it froze until the stream paused | `components/audit/AuditWorkspace.jsx` | Throttle, not debounce | S | Fixed |
| L5 | The artifact library fetched and mounted up to 50 documents at once, each its own iframe | `components/artifacts/ArtifactCards.jsx` | Fetch when near the screen (`hooks/useNearViewport.js`) | S | Fixed |
| L6 | Health, live-run and desk polling ran in hidden windows | `lib/connection.js`, `hooks/useLiveRuns.js`, `components/insights/Desk.jsx` | `lib/visibility.js`: skip hidden ticks, re-check on return | S | Fixed |
| L7 | Every SSE frame is its own React render | `hooks/useAgentSession.js` | Coalesce text chunks per animation frame; flush before any other event | M | Open |
| L8 | Transcript has no windowing; history loads whole | `hooks/useAgentSession.js`, `AgentChat.jsx` | `content-visibility: auto` on settled rows, then paginated history | S, then M | Open |
| L9 | Slide preview reloads its iframe on every resize frame | `components/content/SlidesCarousel.jsx` | Fixed 1080 px document, scaled with a transform | S | Open |
| L10 | Split drag writes `localStorage` on every pointer move | `components/workspace/SplitWorkspace.jsx` | Write on pointer up | S | Open |
| L11 | A sidebar badge animates forever; the skeleton shimmer animates `background-position` | `components/AppSidebar.jsx`, `app/styles/skeleton.css` | Bounded iterations; animate a transform | S | Open |

## Desktop shell

Paths under `desktop/src-tauri/`. Shell version 0.7.1 to 0.7.2 (patch: no contract change).

| # | Finding | Evidence | Fix | Effort | Status |
|---|---|---|---|---|---|
| D1 | 1200×800 window overflows 1366×768 and 1280×800 screens, and is not centred | `tauri*.conf.json` | `center` and `preventOverflow` in all four configs | S | Fixed |
| D2 | No zoom anywhere; a 4K screen at 100% scaling draws 14 px text at 3840 CSS px | `src/lib.rs` View menu | Zoom In, Zoom Out, Actual Size on the browser ladder | S | Fixed |
| D3 | WebKitGTK's DMA-BUF renderer gives a blank window on NVIDIA | `src/lib.rs` `run()` | Turn it off when the NVIDIA driver is loaded, unless the user set it | S | Fixed |
| D4 | Deep-link registration ran two subprocesses on the UI thread before the Linux splash painted | `src/lib.rs` setup | Moved to a thread | S | Fixed |
| D5 | Windows and Linux had no About item, and the app menu bar landed on the splash | `src/lib.rs` `install_app_menu`, setup | About under Help off macOS; menu removed from the splash | S | Fixed |
| D6 | Splash font stack skipped `system-ui`, and a long remark could wrap out of its row | `desktop/src/index.html` | `system-ui` first, one line with an ellipsis | S | Fixed |
| D7 | The `.deb` depends on a tray library nothing uses | `tauri.conf.json` | Dropped from `depends` | S | Fixed |
| D8 | WebView2 is never told the window is minimised, so it keeps its full memory | wry skips `SIZE_MINIMIZED` | On minimise, hide the controller and set a low memory target; reverse on restore | M | Open |
| D9 | Per-machine NSIS install asks for admin on every self-update | `tauri.conf.json` `installMode` | `currentUser`; `windows/installer-hooks.nsh` retires an old per-machine copy at its first update (one last prompt). Needs a 0.7.1 → 0.7.2 update tested on Windows | M | Fixed |
| D10 | Offline launch: 30 s of splash then a blank window on macOS; an engine error page elsewhere | `SPLASH_DEADLINE` reveal | Keep the splash and offer Retry and Quit on it | M | Open |
| D11 | The window is revealed on the page `load` event, onto the "Starting Duct…" placeholder (W1) | `on_page_load` | Reveal when the app says it has drawn (new command, minor bump), after W1 | M | Open |
| D12 | Self-host builds read three keychain items on the UI thread at launch | `src/sidecar.rs` via `setup` | Spawn the sidecar from a thread | S | Open |

Already right, and worth keeping: one webview at steady state (the splash is destroyed, not hidden); WebKit's own background suspension; blocking commands off the main thread; one WebView2 browser process for both windows; no OpenSSL; Sentry inert unless enabled.

## Phones to 4K, and platform fit

| # | Finding | Evidence | Fix | Effort | Status |
|---|---|---|---|---|---|
| R1 | Enter sent a message mid-composition in Japanese, Chinese and Korean input | `components/workspace/ChatInput.jsx`, `insights/desk/DeskComposer.jsx`, `content/PostViewport.jsx` | `isComposing()` in `lib/shortcuts.js` | S | Fixed |
| R2 | Replies ran 200+ characters a line on wide panes; one long URL scrolled the transcript sideways | `AgentChat.jsx`, `ChatInput.jsx` | `max-w-3xl` measure, `wrap-break-word`, stable scrollbar gutter | S | Fixed |
| R3 | Content Studio's seven tabs widened the page on phones | `app/(app)/content/page.jsx` | Scroll in place | S | Fixed |
| R4 | Post and Discover grids stopped at four columns, so cards ballooned at 2560 and 3840 | same, `content/DiscoverPage.jsx` | Auto-fill columns past the widest container step | S | Fixed |
| R5 | Pin, edit and delete controls existed only on hover | `insights/desk/DeskLists.jsx`, `content/FormatLibrary.jsx` | Shown where there is no hover | S | Fixed |
| R6 | Windows High Contrast showed no focus ring anywhere | primitives use a box-shadow ring | Forced-colours outline in `app/styles/base.css` | S | Fixed |
| R7 | Panes and the transcript kept full-width classic scrollbars on Windows and Linux | `scrollbar-width` does not inherit | Applied to every element at zero specificity | S | Fixed |
| R8 | Ctrl+B was taken from macOS text fields by the sidebar shortcut | `components/ui/sidebar.tsx` | `matchesCombo("mod+b")` | S | Fixed |
| R9 | No platform hook for CSS; blur behind the sticky header is the slow path on WebKitGTK | `app/layout.js` | `data-platform`, `data-shell` set before paint; Linux drops blur, desktop stops rubber-banding | S | Fixed |
| R10 | Safe-area insets applied twice on notched iPhones; full-bleed workspaces overflowed and the composer sat below the fold | `app/styles/theme.css`, `(app)/layout.js`, `ChatInput.jsx` | Body pads the sides only; the header, sidebar, sheets and corner notices take their own edge. Left and right kept separate for iPhone Duo | M | Fixed |
| R11 | Split panes clipped between 768 and ~830 px (iPad portrait, iPhone landscape); sidebar state cookie is written, never read | `components/workspace/SplitWorkspace.jsx`, `components/ui/sidebar.tsx` | Split on the split's own width (`@xl/split`), fixed; reading the cookie is open | S–M | Part fixed |
| R12 | About 20 hand-rolled fields at 14 px make iOS zoom on focus | project, brand, memory, execute pages | A `ui/textarea` primitive with the input's sizing, plus a `check:design` rule | M | Open |
| R13 | Audit report explanations live only in hover tooltips | `components/audit/AuditReportV1.jsx` | Print them inline | S | Open |
| R14 | Plan calendar is seven 44 px columns on a phone | `components/content/PlanCalendar.jsx` | A list below `@xl` | M | Open |

## How R10 and R11 were checked

| Where | How |
|---|---|
| Chromium | Safe-area insets emulated, on the insights workspace |
| WebKit | The same sizes, without insets |
| iPhone 17 Pro simulator | Safari on iOS 26.5, real insets |

Sizes: iPhone 17 Pro portrait and landscape, iPad Air portrait, the desktop window's 900×600 minimum, and iPhone Duo's Safari viewports from WebKit's Safari 27.1 notes. Those are the outer display (382 wide), the inner one (669 and 951), and two windows side by side (385 each), plus an outer display with a one-sided inset.

- **Before:** the iPhone page overflowed by 96 px, and the composer sat 62 px below the fold.
- **After:** no size scrolls the page, and the composer meets the bottom edge above the home indicator.
- **The split** shows both panes only where both fit: the Duo's inner display yes, two windows no.
- **Not covered:** iPhone Duo's own simulator needs Xcode 27.1; this machine has 27.0. Viewport segments (the fold as a hinge) sit behind a Safari flag and are not used.
