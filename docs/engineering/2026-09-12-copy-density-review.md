# Nobody reads the second sentence

**Author:** Shirish Kadam · **Date:** 2026-09-12

Every string in the app, measured. The app is not badly written — it is
*over*-written in a specific, repeating way: the sentence that explains the design sits
next to the sentence that describes the choice, and both ship. Here is where, and which ones are
a layout problem rather than a writing one.

Method: every JSX text node and string literal in `app/src` of eight words or
more, comments and class strings stripped, deduplicated per file. Agent prompts were excluded by
hand after inspection — `AuditWorkspace.jsx:33` is a message sent *to* the model,
where length is a feature, not copy shown to a person.

**308**prose strings ≥ 8 words**98**≥ 15 words**53**≥ 20 words**22**≥ 25 wordsdesktop-auth281ProviderStep133start126connections111UsagePanel73execute67ProviderCard62project memory59activity55TelemetryCard50

Words held in strings of 15+ words, by file. The tall bar is one screen
almost nobody sees twice, and the short bar is a privacy disclosure everybody reads once.

## 01Paragraphs that should be a layout

These are not writing problems. Each one is prose doing a job that a list, a table, a chip row or
a button does better — and in every case the component underneath already has the shape available.

#### A privacy claim is scanned, not read

components/TelemetryCard.jsx:70–74 — 72 words (on-by-default build) / 50 (off) + a trailing sentence

The longest single string in the app argues for crash reporting, then lists what is sent, then
lists what is never sent, then says when it takes effect — in one paragraph, under a switch. The
reader's actual question is binary and comparative: *what leaves my machine?* Prose is the
worst possible shape for a comparison.

now"On by default, so a crash tells us something without you having to report it, and we can see which parts of Duct actually get used. Crash reports carry the error and the stack trace that caused it; usage is which screens and features you open. Never your provider API keys, your data, or anything you generate — and nothing is stored on this machine. Turn it off here and it stays off." 72 wproposed"Crashes and which screens you open. Nothing else." 8 w — plus the two columns below, and the "takes effect next launch" line demoted to the switch's own hint.Sends / Never sends✓The error and stack trace of a crash✓Which screens and features you open✕Your provider API keys✕Your data, or anything you generate

Two columns of four short rows, lucide `Check` / `X` at
`size-3.5`. Same facts, read in about a second, and the "never" half becomes a promise
you can point at rather than a clause at the end of a paragraph.

#### Thirteen tiles, thirteen paragraphs, in a component whose docstring says "one line"

app/(app)/connections/page.jsx — tile descriptions run 9–25 words; ConnectorTile.jsx's own contract is "logo, name, one line of what it's for, and its live state"

The grid is the page's scannability, and it is carrying 111 words of description in its long
entries alone. The lengths are also inconsistent in kind: some are metric lists, some end in
filler (*"…data for SEO reporting"*), and three make an editorial claim
(*"the money truth"*) that the tile has no room to support.

now"Cross-platform event truth — signups, logins, and upgrades under one name across web and app, the reference your ad platforms and GA4 get reconciled against." 25 wproposed"Signups, logins and upgrades, one name across web and app." 10 w

Rule for the grid: **metric nouns, ≤ 10 words, no trailing purpose clause.** The
tile already shows the connector's state and storage; the description only has to answer "what
data is this".

#### Eleven error bodies that restate their own titles, and one instruction that should be a button

app/(auth)/desktop-auth/page.js:35–100 — 281 words across 12 strings

The catalogue is well-intentioned: each reason code gets a title and a body, and the file's
comment correctly argues that "try again" is useless advice for a misconfigured install. But the
titles are already doing the work — *"Sign-in isn't configured"* followed by "This build of
Duct is missing its Google sign-in credentials, so it can't sign anyone in" is one fact, twice.

The sharper finding: **"please report this with the version number from the app's About
screen" appears in three bodies.** That is a UI asking the reader to go somewhere else,
read a string, and transcribe it. A `Copy diagnostics` button that puts version, reason
code and timestamp on the clipboard deletes the sentence from all three *and* produces a
better bug report than a human transcription would.

nowTitle: "This connector isn't configured" · Body: "This build of Duct is missing the credentials for that connector. Trying again won't help — please report this with the version number from the app's About screen." 27 wproposedTitle unchanged · Body: "Trying again won't help — this build shipped without that connector's credentials." 12 w · Action: `[ Copy diagnostics ]`

#### A caption narrating the picture directly beneath it

components/models/UsagePanel.jsx:285 — 37 words, over a rendered example month

The empty state is otherwise the best pattern in the app: icon, title, a real sample report, two
actions. Then the caption spends 37 words explaining what the sample shows, including the punchline
("2% of the calls and 40% of the bill") that the sample's own rows state numerically.

now"The first agent run fills this in: what it cost, which agent spent it, which model. Below is a normal month — and the thing worth noticing is the deep model, 2% of the calls and 40% of the bill." 37 wproposed"Your first agent run fills this in. Below is a normal month." 11 w — and mark the Heavy row in the sample itself, where the claim is already true on screen.

#### Two memory pages introducing a list that introduces itself

app/(app)/memory/page.jsx:60 (47 w) · app/(app)/project/[projectId]/memory/page.jsx:76 (34 w)

"What Duct knows about this project, and *where each fact came from*" — every row below it
already carries a source badge (`SOURCE_BADGES`) and evidence chips
(`MemoryTimeline.jsx:44`). The lede is narrating a UI the reader can see. Cut both to the
one thing the rows cannot say for themselves: what this page is for, and that agents read it before
every run.

now"How you like to be worked with — the depth and tone you want, the methods you insist on, the tools you trust. This follows you across every project and is private to you. Your preferences land here automatically; add anything else you want every agent to know." 47 wproposed"How you like to be worked with. Every agent reads this, on every project, and only you can see it." 19 w

## 02Trim in place

No structural change, no new component — the same surface with the second and third sentence gone.
Ranked by how visible the surface is, not by word count.

| Where | Words | What to cut | Kind |
| --- | --- | --- | --- |
| `content/AnalyticsView.jsx:165` | 31 | Two facts fused: where numbers come from, and which ones are manual. The second belongs beside the manual fields, not in the panel lede. | trim |
| `(app)/projects/page.jsx:110` | 31 | "Everything else hangs off it, so this is the first step" — the page has one button; it is visibly the first step. | trim |
| `content/DiscoverPage.jsx:124` | 29 | Explains the sub-agent's citation mechanics to someone deciding whether to press Scrape. | trim |
| `(app)/activity/page.jsx:190, :220` | 28 + 27 | Two empty states explaining the same ledger. The signed-out one can be one line; the signed-in one keeps the "nothing is written until something runs" clause and drops the inventory. | trim |
| `(app)/audit/seo/page.jsx:248` | 25 | A memory switch described in prose, when `AutoFallbackCard` and `ContextCompressionCard` already set the two-state switch pattern for exactly this. | pattern |
| `insights/InsightsWorkspace.jsx:357, :396` | 24 + 19 | Both empty states end by explaining versioning to a reader who has never seen a version. | trim |
| `content/FormatLibrary.jsx:193` | 23 | "A format is a reusable recipe — …" then a second sentence on which agent reads it. Keep the definition. | trim |
| `(start)/start/page.jsx:428, :436` | 20 + 24 | Crawl warnings that explain the crawler's limitations mid-onboarding. One clause each: what was found, what it costs the audit. | trim |
| `content/BrandContextForm.jsx:143, :163` | 20 + 20 | Two adjacent sections each explaining what is inherited from project setup. Say it once, at the boundary between them. | trim |
| `(app)/projects/page.jsx:224` | 21 | Delete dialog. "This cannot be undone" stays; "Saved reports are not removed automatically" is a separate fact that belongs in the dialog's own list, not in the warning. | trim |

## 03The opposite failure

The sweep found the mirror image too, and it is the more serious of the two: twenty-three error
strings that are short, passive, and say nothing a person can act on.

#### "Failed to …" ×15, "Something went wrong" ×8

execute/page.jsx:488,518,529,752 · content/AccountsTab.jsx:51,77 · content/PlanBoard.jsx:44,68 · content/FormatLibrary.jsx:128 · content/StyleGallery.jsx:99 · content/PostViewport.jsx:109 · content/PublishModal.jsx:274 · audit/ExecutionOffer.jsx:312 · lib/agentSession.js:693,715 · AppErrorPanel.jsx:101 · and more

`DESIGN.md:567` already rules on this: *"Own the failure and give the next step.
'We couldn't reach GA4 — retrying in 30s', never 'An error occurred' / 'Request failed (500)'."*
These are the banned form, shipped fifteen times as a fallback behind `err.message ||`
— which means they appear precisely when the server said nothing useful, i.e. when the reader needs
the most help.

now"Failed to load guardrails." · "Something went wrong. Please try again."proposed"Couldn't load your guardrails — the queue below is still accurate. Retry." · with the retry as a button, the way `LoadError` already does it.

Cheapest fix in the report: `LoadError` exists, takes
`what` / `detail` / `onRetry`, and is already used on this very
page for one of its four failures. The other three hand-roll a red `<p>`.

## 04Leave alone

Measured, read in context, and correct as they stand — listed so a later pass does not "fix" them:

- **`DeskDayOne`** — three steps, a done-count, a sample card each side.
  Short blurbs because the layout carries the meaning. This is the model the rest of the app should
  copy.
- **Tier taglines, thinking rungs, `SOURCE_*` and `STORAGE_*` labels**
  — one line each, already at the floor.
- **`ProviderStep`'s error hints** (16–22 words) — long, but every one
  names a cause and a next step. Length is earned when the alternative is a dead end.
- **`ConnectionBanner`, `ReloadToast`, `agentSession`'s
  error map** — the voice rule's own cited examples.
- **Agent prompts** (`AuditWorkspace.jsx:33`,
  `PostViewport.jsx:364`) — written for a model, not a person. Excluded from every count
  in this document.

## 05One unrelated visual defect, found on the way

`components/execution/ChangeSetCard.jsx:108,134,144,147,192` draws its icons with
emoji — ⚡ for the card, ✓ ✕ ↺ • for change status, ⚠ and ⛔ for warnings, and a ↺ inside the
Roll back button's own label. `DESIGN.md`'s
anti-slop table names "emoji as icons" as a tell, and the app is lucide-only everywhere else. Same
four glyphs exist as `Zap`, `Check`, `X`, `RotateCcw`,
`TriangleAlert`, `Ban`. Roughly a fifteen-minute change, and it is the one
card an agent's proposed change appears inside.

## 06The rule, and the order to do it in

**One idea per string. The second sentence has to earn its place against deleting it.**
When it survives because it is genuinely needed, ask the next question: is it a sentence, or is it a
list, a chip, a column, or a button that the reader would rather have?

Written into `app/DESIGN.md` under Voice & microcopy as the one-line-per-option
rule, which this sweep extends from pickers to panels.

Done in this order — cheapest and most-seen first, one commit each:

| # | What shipped | Commit |
| --- | --- | --- |
| 1 | Fifteen `Failed to …` fallbacks and eight `Something went wrong` strings rewritten to name what did not happen and what is still true; four section failures moved to `LoadError`; `AccountsTab`'s failed load stopped rendering as an empty list; `PublishModal`'s duplicate error translator deleted | a89d111 |
| 2 | Thirteen connector tiles cut to metric nouns, ten words or fewer | 0ef0f76 |
| 3 | `TelemetryCard` is a Sends / Never-sends list; the panel split out so `/preview` can render it, with a scene in both build states | 9daeca0 |
| 4 | desktop-auth bodies to one sentence each; `Copy details` button with the reason code, replacing "report this with the version number from the About screen" ×3 | a5a83c6 |
| 5 | The trim table, plus the usage caption and both memory ledes | c14d964 |
| 6 | `ChangeSetCard`'s six emoji → lucide on semantic tokens, and the card gets its first `/preview` scene | b5e7b49 |

One thing changed shape in the doing. The audit's *Remember this session* switch was
listed as a trim; it became a pattern fix instead, because the sentence only described the OFF
state and the two switches on the Models page already describe whichever state they are in. It
now does the same — which is also the only version that is true while the switch is on.

Companion to [app/DESIGN.md](../../app/DESIGN.md) (Voice & microcopy, Not AI slop)
and [STYLE.md](../../STYLE.md). Counts are reproducible: prose strings of eight words or
more in `app/src`, comments and class strings stripped, `app/preview`, tests
and `ui/` primitives excluded.
