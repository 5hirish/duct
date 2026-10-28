# Performance review: web app and desktop app

**Author:** Shirish Kadam · **Date:** 2026-10-28

Duct's first screen waits for all its JavaScript, and a long agent thread got slower with every reply. This review measured both, fixed the cheap half on `perf/client-load-and-shell-review`, and ranks the rest; [the findings](2026-10-28-performance-review-findings.md) hold the evidence.

| What a person waits on | Before | After this branch |
|---|---|---|
| Front door, first visit | 292 KB of compressed JS before anything but "Starting Duct…" shows | Same JS (W1 is open); a 40 KB font no longer preloaded |
| Insights thread, first load | 593 KB compressed JS, 1.95 MB to parse | About 444 KB and 1.35 MB (−25%) |
| Content Studio, first load | 523 KB compressed JS | About 440 KB (−16%) |
| One token in a 50-reply thread | Re-parses all 50 replies | Re-parses the one being written |
| Desktop window left open all day | Health check every 30 s, hidden or not | Only while visible |

Before: the hosted app on 2026-10-28, every script a route's HTML loads, brotli. After: those routes less the chunks this branch takes out of the first load, confirmed on an esbuild graph of the branch. Re-measure once deployed.

**At a glance**

- **The server renders a placeholder.** The first real pixel waits for 300–600 KB of script. The largest lever, still open.
- **Chat routes shipped charts and 45 code themes** they rarely use. Both now load on first need.
- **Long sessions stopped scaling with their length.** Settled replies no longer redraw per token.
- **The desktop app idles at about 190 MB.** Its gaps were fit, not memory: small screens, no zoom, a Linux blank window.
- **Phones to 4K mostly hold.** Eleven fixes landed, checked at iPhone Duo's sizes too; three remain.

## The first pixel waits for all the JavaScript

Every route group wraps a gate that waits for the desktop shell to name its backend. It decides in an effect, which never runs on the server, so every page arrives saying "Starting Duct…". In a browser that wait buys nothing.

It hurts most on the acquisition path: the front door and `/start` show grey text until 292–311 KB of script has run. Server time adds 0.1–1.5 s, as the locale cookie makes every route dynamic.

**The fix (W1):** make each request wait for the backend, not the whole tree, so pages render on the server. It touches about 120 call sites and the session rules, so it is its own change.

## Chat routes carried code nobody had asked for

- **Recharts, about 85 KB compressed,** came with the artifact renderer, so every artifact card and brief paid for charts. Content Studio loaded it for a tab that is closed by default.
- **Every Prism theme, about 66 KB,** came with the code block, which imported one theme from the package index.

Both now load when first on screen, behind a placeholder of the same size. So does the slide-capture library, and Sentry traces one session in ten, not one in two.

## A long thread made every token slower

The chat redrew every row, re-parsing each reply's markdown, on every streamed token and every tick of its clock. Now only the reply being written redraws. Three neighbours had the same shape:

- **A brief beside the chat** re-parsed on every chat token.
- **A brief being written** re-parsed per chunk; now ten times a second.
- **The artifact library** mounted 50 documents at once; now cards fill as they near the screen.

Polling now skips hidden windows and re-checks on return.

## The desktop shell is lean; the gaps were fit and platform

Measured on this 8 GB laptop, the app settles at **about 190 MB**: 40 MB of shell, 126 MB of page, 27 MB of helpers. The splash is destroyed, and WebKit suspends a hidden window itself. The page is what grows, so the transcript fixes above are the desktop memory fixes too.

Fixed in shell 0.7.2:

- **Small screens:** the window opens centred and on screen, not under a 1366×768 taskbar.
- **Zoom:** View can zoom, so 14 px text on a 4K screen at 100% scaling can grow.
- **Linux:** no blank window on NVIDIA; the splash no longer waits on two subprocesses.
- **Windows and Linux:** About is back, and the menu bar is off the splash.
- **Windows updates stop asking for admin:** Duct installs per user now, and the first update retires an old per-machine copy with one last prompt.

Open: WebView2 memory on minimise (D8), Retry on an offline splash (D10), and revealing the window once the app has drawn (D11).

## Phones to 4K: the system holds, eleven edges did not

The container queries from the [September review](2026-09-01-desktop-adaptive-ui-review.html) hold; what broke sat outside them.

| Fixed | Open |
|---|---|
| Safe areas applied once: full-screen views fit a notched iPhone | iOS zooms into ~20 small fields |
| The split waits until both panes fit (iPad portrait, iPhone landscape) | Audit explanations live only in tooltips |
| Enter no longer sends mid-composition in Japanese, Chinese or Korean | Plan calendar on phones |
| Replies keep a reading width; long URLs wrap; tabs scroll on phones | |
| Grids grow at 2560 and 3840; touch, High Contrast and scrollbar fixes | |

The page now learns its platform before first paint: Linux drops backdrop blur, WebKitGTK's slow path, and the desktop window stops rubber-banding.

## What to do next

1. **W1: render the front door and `/start` on the server.** The biggest perceived-speed win.
2. **D8 and D11** for desktop memory and launch.
3. **R12 to R14** for phones, and a 0.7.1 to 0.7.2 update tried on Windows.

The longest wait is still the agent's own run, about three minutes for a brief: server work, outside this review.

## Go deeper

- [Findings, with evidence](2026-10-28-performance-review-findings.md)
- [`app/AGENTS.md`](../../app/AGENTS.md) "UI conventions" and [`desktop/AGENTS.md`](../../desktop/AGENTS.md)
