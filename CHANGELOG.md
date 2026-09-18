# Changelog

Notable changes to Duct. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version numbers here are the **desktop shell's** (`desktop/src-tauri/tauri.conf.json`),
which is what the updater and the GitHub releases are cut against. The backend
and app deploy continuously from `main` and are not versioned separately.

So `[Unreleased]` means *not in a desktop release yet*, not *not shipped*: a
backend or app entry can sit here while users have been running it in production
for weeks. `site/changelog/` is the user-facing record and dates each entry by
when it shipped, which is why the two can disagree about timing without either
being wrong.

`.github/scripts/release-notes.mjs` reads the section matching the version being
released and puts it at the top of the GitHub release, so an entry written here
is the entry users see. **Write the section in the pull request that bumps the
version**, not after: `desktop-release.yml` runs
`python3 scripts/check_changelog_sync.py --version X.Y.Z` before any platform
builds and refuses a version with no section, because 0.5.0 and 0.7.0 were both
published without one. The same script, with no arguments, holds
`site/changelog/` to the newest section here and runs in `make check-site`.

## [Unreleased]

### Changed

- **The site is product-led.** The home page opens on a 30-second film of a real
  session, `/seo-audit` sells the report with a sample of the real thing, and
  the tools, blog and for-\* pages speak the product's current voice. Every page
  carries its own Open Graph card; `assets/og-image.png`, the one shared card,
  is gone.
- **Pages weigh what they should.** Every product shot is published at 768 and
  1536 px beside the 2x capture and listed in `srcset`, a phone plays a 720 px
  cut of the film, and media, art and icons carry a week of cache: the home page
  on a phone went from 3.0 MB to about 1.1 MB.

### Fixed

- A phone no longer scrolls sideways past the privacy cookie table or the
  download page's file locations, footer links are a thumb's height apart, no
  label sits under 11 px, and revealed sections show without JavaScript.

## [0.7.0] — 2026-09-15

A profile every agent reads, a front door that opens with the audit, and the
design system the app had been approximating in hand-rolled CSS.

### Added

- **A profile on a page, in a row every agent can read.** Role, business, voice
  and depth lived in one browser's `localStorage` and rode on each request, so
  two devices disagreed and the scheduled brief — the run whose owner is
  definitely not watching — could read none of it. It is a row per user now,
  rendered once and read by the audit, insights and content agents; the audit
  runner had been accepting preferences it never passed to the prompt.
- **The time zone a week starts in**, so "last week" means the same thing to the
  agent as to the person reading the brief.
- **A signed-out page that is a front door**, continuous with `/start`: the
  audit is what a stranger meets, not a login form.
- **"Keep me signed in"** — a 30-day option on Google sign-in.
- **Image generation is a choice, not a default.** OpenAI's GPT Image 2.5 pair,
  Flare as the default, and drawing on an OpenRouter key instead of declining
  every picture. xAI and OpenRouter are one click in the tier map.
- **Tokens and state primitives** for the jobs the palette had been standing in
  for, documented in `/preview`; the app moved onto them and a generated report
  declares itself a light-scheme document.

### Changed

- **Copy across the app says one thing per surface.** Panel and option blurbs
  cut to a single idea, second sentences deleted on ten surfaces, and the UI
  stopped narrating what the reader is already looking at.
- **Empty states activate** rather than reporting that nothing is there.
- **Insights opens a run knowing what it can reach**, on the tier the job
  deserves; the dials follow the conversation instead of staying on the desk,
  and a connection asked for mid-conversation comes back to that conversation.
- **Google Ads no longer needs a developer token.** Google sunset them on
  2026-09-09; the bring-your-own path is gone and Ads is OAuth-only.

### Fixed

- A reload restores the thread instead of re-asking the question, and the
  insights desk no longer blanks itself when the window comes back.
- Memory is not primed again on a resumed thread.
- GA4 pulls ask for key events rather than the alias Google deprecated, and
  landing-page reports use the nested string filter — they returned nothing at
  all before.
- A dead request is reported as a failure instead of rendered as an empty list;
  a 402 on a provider key routes through the shared error UI; a provider card
  that is still loading no longer reports a verdict; a disabled button reads as
  disabled.
- Desktop: a ChatGPT sign-in can be cancelled and replaced, the browser gets its
  callback response before the socket closes, local secrets are held where the
  OS can protect them, and a notification row acts instead of only reporting.
- Session ids come from the CSPRNG, and a session is bound to the backend that
  minted it.

## [0.5.0] — 2026-09-09

The audit becomes the way in, and a run finally spends the key and the tier the
user chose.

### Added

- **The audit is the onboarding.** `/start` asks for a URL and begins crawling
  the moment it validates, instead of eleven questions before any evidence the
  work is worth it. The project it drafts carries provenance per field ("From
  your site" / "Duct's guess"), and an account is asked for when there is a
  report worth keeping — sharing it is membership, so the link is a 404 for a
  stranger.
- **A guest account before the sign-in.** A real `users` row keyed on the
  install id owns what the audit writes, so no auth boundary loosens and no
  owner column becomes nullable; signing in links that row or merges it by
  walking the schema for owner columns rather than a hand-kept list.
- **The saved tier map reaches the run.** The model tiers page had been writing
  to `localStorage` that no run ever read: a user could set Heavy to Opus, watch
  a run choose Gemini, and have no way to tell which setting was lying. It is a
  row per user now, resolved by `resolve_job_run` — including the scheduled
  brief, which no browser storage could ever reach.
- **Quota routes around itself.** A 429 the retry loop gave up on is remembered
  for a few minutes, keyed by credential identity and provider, so the next run
  resolves to a model that will answer instead of spending four more attempts
  dying the same way.
- **Runs spend the key the caller actually holds**, including a ChatGPT plan,
  and `POST /providers/{id}/verify` makes one real call on the Light model to
  tell an invalid key from an unbilled account from a model the account cannot
  see.
- **What a run cost, on the key that paid for it.** Token and dollar figures per
  agent, per model and per provider — three breakdowns, because which agent is
  expensive, which model is, and which provider is are three different
  decisions. Duct computed these already and threw them away.
- **Pictures draw on whichever image-capable key you brought**, rather than one
  vendor's.
- **Analytics ask first.** Consent Mode defaults are declared denied on the
  page, region comes from Cloudflare's trace with every failure path failing
  closed to "ask", and a decline stops the container loading at all. The desktop
  shell never asks: it runs with storage permanently denied, so nothing is
  stored to consent to.
- `site/changelog/` — a public changelog with an RSS feed, written for someone
  deciding whether to install rather than someone reading a diff. `CHANGELOG.md`
  stays the engineering record; the two must not disagree about what shipped.
- Platform cards on the download page — macOS, Windows, Linux, Debian/Ubuntu —
  each on a version-independent URL. The visitor's platform is marked with a
  badge, a heavier border and a shadow, never colour alone.

### Changed

- **A connector's numbers reach the agent whole.** Anything over the response
  budget used to be cut mid-structure — on a 900-row search-terms pull that is
  two thirds of the numbers gone, with the agent unable to tell which, writing
  the brief confidently off a third of the data. Rows fold to typed CSV first:
  every row survives, byte-identical, at 45-55% of the tokens.
- The site says plainly that the app you download runs against Duct's servers,
  rather than leaving a reader to infer it from the desktop bundle.
- The desktop Help menu has something in it, and an About panel says what this
  is; the account drawer answers "it broke" and "it should do X".

### Fixed

- **A failed key check no longer echoes the key** back in its error detail, and
  quota is keyed to the credential's identity rather than its value, so a leaked
  key confirms nothing about who is using it.
- An audit no longer rewrites a project it was never about.
- A tab running last week's build is offered a reload instead of failing against
  an API it no longer matches.
- **Server-side request forgery in the shared crawler.** `validate_public_url`
  judged the URL a caller passed in and nothing after it, so a public URL
  answering `302 -> http://169.254.169.254/` was fetched and its body handed to
  a model — on the lead-magnet audit path, which runs behind Turnstile with no
  account. Every redirect hop and every resolved address is checked now.
- **Path traversal at the storage sink.** Five call sites joined a key onto the
  uploads directory and opened the result. No live caller could traverse, but
  that was a property of the callers and one refactor from being false, so
  `_local_path` resolves and checks containment and all five go through it.
- **The chat error frame streamed the provider's exception text to the
  browser** — request URLs, model configuration, and the API key itself from a
  provider that echoes the failing request back. The browser gets a short
  reference that also appears in the log line, which is what a support
  conversation needs.
- **Quadratic backtracking in memory's relative-date pattern.** "last " plus
  20k spaces took 18.2s of one worker, from one request; the same input now
  takes 3ms.
- A desktop shell that cannot complete sign-in says so, instead of silently
  signing the user into the hosted web app and leaving nothing on screen to
  explain it. A desktop PR now fails when a command is not actually registered,
  which is what let that ship.
- An expired or unrecognised session signs you out instead of rendering the
  backend's 401 detail where a page's empty state belongs. Executions, Memory,
  Artifacts and Activity each showed a bare "User not found"; every user-scoped
  route was failing, and it only looked local because the rest swallowed it.
- `404.html` rendered unstyled on every path below the site root. Cloudflare
  Pages serves it at the URL that missed, so its relative `assets/duct.css`
  resolved to `/blog/assets/duct.css`; every path in the file is root-absolute
  now.

## [0.4.1] — 2026-09-07

Three release-pipeline defects that 0.4.0 made visible. A published release is
immutable, so a corrected build needs a version.

### Fixed

- **Windows was never offered a self-update.** `latest.json` for 0.4.0 carried
  darwin and linux targets and no `windows-x86_64`, so every Windows install
  polled forever. Tauri signs the installer directly now, so the upload's
  `*-setup.nsis.zip.sig` glob matched nothing — and `if-no-files-found: error`
  stayed quiet, because it asks whether *any* pattern matched and the `.exe`
  did. The signature uploads under either name and the job fails loudly when
  neither exists.
- **The site had no download URL it could hold on to.** Tauri puts the version
  in every filename, so `releases/latest/download/<name>` had nothing stable to
  redirect to and the page resolved the release through the GitHub API at
  runtime — an API call subject to CORS, rate limits and JavaScript, to answer
  a question that does not change between releases. Each installer is published
  a second time under a version-independent name.
- **The site served a build from before September while every workflow stayed
  green.** Cloudflare Pages' git integration decided whether to build from
  "Build watch paths", a dashboard-only setting that is not in this repository
  and had stopped matching `site/**`; a build it skips reports as *skipped*,
  which reads like "nothing to do". The site deploys from Actions now, gated on
  the checks in the same file.

## [0.4.0] — 2026-09-07

First version cut after the desktop shell became self-contained.

### Added

- **Local sidecar.** The desktop bundle ships the FastAPI backend frozen by
  PyInstaller and runs it on loopback, so the app works with no server and no
  account. SQLite lives in the per-user data directory.
- **Credential encryption on desktop.** The shell mints a Fernet key into the OS
  keychain and passes it to the sidecar, so linking a data source can persist.
  Before this, connecting Google Ads completed OAuth and then failed to save.
- **Sign-in that survives a frozen bundle.** `JWT_SECRET` is generated once into
  a `0600` file in the data directory and reused across restarts.
- **Browser-based OAuth for desktop**, for both sign-in and connectors, over
  `ai.getduct.desktop://` deep links carrying single-use codes rather than
  credentials.
- **Model tiers.** Heavy / Standard / Light, assigned per job in
  `/settings/models`.
- **Connectors:** Mixpanel, Microsoft Clarity, GrowthBook, Apple Search Ads,
  Meta Ads, OpenAI Ads, Stripe, RevenueCat, Google Tag Manager.
- **Staged execution.** Agents propose change sets against Google Ads and GA4;
  a human previews, approves and can roll back. No approve or apply tool exists
  in either harness.
- **Agent memory.** Bi-temporal, provenance-linked project memory with a
  timeline view.
- `scripts/build_blog.py` — pre-renders blog posts to static HTML. Measured
  against production, GPTBot received 49 characters of body text for a
  6,000-word post, the title "Duct Insights", an empty description and the
  canonical `/blog/post` shared by every post. Now 5,105 characters, a unique
  canonical, and `Article` JSON-LD in the served bytes.
- `site/blog/feed.xml` — the blog's first RSS feed.

- `site/doctrine.html` — the seven positions this project is built on, each
  linked to the file that enforces it. Written because the reasoning already
  existed in `STYLE.md`, `agents/core/ports/__init__.py` and
  `service/execution/policy.py`, where nobody evaluating the project reads it.
- `.github/FUNDING.yml` — GitHub Sponsors. Not a revenue plan at this stage; a
  public signal that the project is maintained.
- A Community section in `README.md` pointing at Discussions rather than a chat
  server. An empty Discord is a worse signal than no Discord, and a Discussions
  answer is findable later.

- Open-source project files: `LICENSE` (MIT), `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, issue forms, a pull-request template, `CODEOWNERS` and
  grouped Dependabot configuration.
- `make check` — one entry point running exactly what CI runs, per area.
- `test_route_auth_boundaries.py` — every project-scoped route must resolve a
  signed-in user, and every ungated `/api` route must be declared with a reason.
- Social preview cards, generated from `scripts/social/template.html`. The site's
  `og:image` had been referenced by 23 pages without the file ever existing.
- `STYLE.md` — what good code looks like here, separate from the `AGENTS.md`
  rules about what must not break. Every convention in it was measured against
  the tree rather than asserted.
- PR triage (`.github/workflows/pr-triage.yml`) — an agent summary of inbound
  pull requests, posted as one sticky comment saying what a PR does and where to
  look first. It never approves or blocks, and stays inert until the repository
  has an `ANTHROPIC_API_KEY` secret.

### Changed

- One agent instruction file per directory: `AGENTS.md` is canonical and
  `CLAUDE.md` is a symlink to it, replacing two files per area that had drifted.
- READMEs rewritten. The root one named four connectors that do not exist and
  described the app as a no-auth shell.

### Fixed

- A project with no `project_members` row disappeared from the owner's project
  list; migration `a4d18e5c26bf` backfills owner membership.
- A token that fails to resolve is rejected rather than treated as an anonymous
  caller.
- One source of truth for `site/` conventions. `.claude/rules/landing-pages.md`
  and `.claude/skills/add-blog-post.md` both told agents to write a blog
  canonical and sitemap entry as `/blog/post.html?slug=…`, while the site uses
  the extensionless `/blog/post?slug=…` everywhere and CI rejects a canonical
  containing `.html`. The skill is corrected, the rules file is now a pointer to
  `site/AGENTS.md`, and the canonical form is stated outright there instead of
  being implied by a table.
- The app's typecheck actually runs. `npm run typecheck --if-present` had been
  pointed at a script that did not exist, and `--if-present` exits 0, so both
  `make check-app` and App CI reported a green typecheck without ever invoking
  `tsc`. The script now exists and is invoked by name.
- Two npm advisories (`browserslist` high, `postcss-selector-parser` low).
- Three false-positive CRITICAL findings that had the security audit failing on
  every pull request.

[Unreleased]: https://github.com/5hirish/duct/compare/desktop-v0.7.0...HEAD
[0.7.0]: https://github.com/5hirish/duct/releases/tag/desktop-v0.7.0
[0.5.0]: https://github.com/5hirish/duct/releases/tag/desktop-v0.5.0
[0.4.1]: https://github.com/5hirish/duct/releases/tag/desktop-v0.4.1
[0.4.0]: https://github.com/5hirish/duct/releases/tag/desktop-v0.4.0
