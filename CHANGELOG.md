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
is the entry users see. A version with no section still releases — it just gets
the commit list and the install instructions, which is worse.

## [Unreleased]

### Added

- `site/changelog/` — a public changelog with an RSS feed, written for someone
  deciding whether to install rather than someone reading a diff. `CHANGELOG.md`
  stays the engineering record; the two must not disagree about what shipped.
- Platform cards on the download page — macOS, Windows, Linux, Debian/Ubuntu —
  each on a version-independent URL. The visitor's platform is marked with a
  badge, a heavier border and a shadow, never colour alone.

### Changed

- The site says plainly that the app you download runs against Duct's servers,
  rather than leaving a reader to infer it from the desktop bundle.

### Fixed

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

[Unreleased]: https://github.com/5hirish/duct/compare/desktop-v0.4.1...HEAD
[0.4.1]: https://github.com/5hirish/duct/releases/tag/desktop-v0.4.1
[0.4.0]: https://github.com/5hirish/duct/releases/tag/desktop-v0.4.0
