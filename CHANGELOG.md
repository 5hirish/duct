# Changelog

Notable changes to Duct. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version numbers here are the **desktop shell's** (`desktop/src-tauri/tauri.conf.json`),
which is what the updater and the GitHub releases are cut against. The backend
and app deploy continuously from `main` and are not versioned separately.

`.github/scripts/release-notes.mjs` reads the section matching the version being
released and puts it at the top of the GitHub release, so an entry written here
is the entry users see. A version with no section still releases — it just gets
the commit list and the install instructions, which is worse.

## [Unreleased]

### Added

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

### Changed

- One agent instruction file per directory: `AGENTS.md` is canonical and
  `CLAUDE.md` is a symlink to it, replacing two files per area that had drifted.
- READMEs rewritten. The root one named four connectors that do not exist and
  described the app as a no-auth shell.

### Fixed

- The app's typecheck actually runs. `npm run typecheck --if-present` had been
  pointed at a script that did not exist, and `--if-present` exits 0, so both
  `make check-app` and App CI reported a green typecheck without ever invoking
  `tsc`. The script now exists and is invoked by name.
- Two npm advisories (`browserslist` high, `postcss-selector-parser` low).
- Three false-positive CRITICAL findings that had the security audit failing on
  every pull request.

## [0.4.0] — unreleased

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

### Fixed

- A project with no `project_members` row disappeared from the owner's project
  list; migration `a4d18e5c26bf` backfills owner membership.
- A token that fails to resolve is rejected rather than treated as an anonymous
  caller.

[Unreleased]: https://github.com/5hirish/duct/compare/desktop-v0.4.0...HEAD
[0.4.0]: https://github.com/5hirish/duct/releases/tag/desktop-v0.4.0
