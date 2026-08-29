# Duct Desktop — Claude Code instructions

Thin Tauri v2 shell around the hosted Duct web app, plus an OS-keychain store
for bring-your-own provider API keys. Design:
`docs/engineering/tauri-desktop-byo-keys-plan.md`.

## Stack

- **Tauri v2** (Rust core) + the system webview. No bundled frontend in the
  alpha — the window loads the hosted URL (`app.getduct.ai`, set in
  `src-tauri/tauri.conf.json`). GA may switch to a bundled static export.
- **Keychain** via the `keyring` crate; commands in `src-tauri/src/lib.rs`
  (`get_provider_key` / `set_provider_key` / `delete_provider_key`). The web app
  calls them through `window.__TAURI__.core.invoke` (`app/src/lib/providerKeys.js`).
- **Browser-based Google sign-in**: the web app probes `get_shell_info` (version +
  `capabilities.browserAuth`) and calls `open_external` (http/https only) to run
  OAuth in the system browser; the backend redirects back via the
  `ai.getduct.desktop://auth?auth_code=...` deep link (tauri-plugin-deep-link),
  which the shell forwards to the webview as `/?auth_code=`. New shell-dependent
  web flows must be gated on a `get_shell_info` capability flag, never on version
  sniffing — old shells keep the legacy path.
- macOS registers the custom scheme from the built bundle's Info.plist, so the
  deep-link leg only works from a bundled app (`tauri build`), not `tauri dev`.
- **Local backend ("sidecar")**: the bundle ships the FastAPI backend frozen by
  PyInstaller (`backend/duct_sidecar.spec`), supervised by
  `src-tauri/src/sidecar.rs`. It binds a loopback port the OS picks, persists to
  SQLite in the per-user data dir, and prints one JSON handshake line the shell
  reads. The web app gets it via `get_sidecar_info` and repoints its API base
  (`app/src/lib/localBackend.js`), gated on the `localSidecar` capability.
  Build it before bundling — `cd backend && poetry run pyinstaller
  duct_sidecar.spec --noconfirm` — because `bundle.resources` copies
  `backend/dist/duct-sidecar/` verbatim and a stale or missing build ships a
  broken app. It is **onedir, never onefile**: a onefile binary unpacks to a
  temp dir at startup and does not survive signing + notarization.
- **Windows and Linux** ship from the same pipeline: NSIS on Windows, deb +
  AppImage on Linux, each with its own PyInstaller sidecar (a frozen CPython
  tree is per-OS, never cross-compiled). Two platform differences are load
  bearing and easy to regress:
  `tauri-plugin-single-instance` (registered **first**, before every other
  plugin) — macOS hands a deep link to the running app, but Windows and Linux
  start a *second* process with the URL in argv, which for this app means a
  second window and a second sidecar with the auth code in the wrong one; and
  `CREATE_NO_WINDOW` in `sidecar.rs`, without which every Windows launch pops a
  console window (the sidecar must stay a console binary — its stdout is the
  handshake). Windows builds are **not** Authenticode-signed yet, so SmartScreen
  warns on first run.
- **Self-update** is wired: `tauri-plugin-updater` behind a default-on `updater`
  cargo feature, driven from the web app through `check_for_update` /
  `install_update` (not the plugin's JS bindings — the window loads a remote
  origin and cannot import them, which is also why no `updater:*` permission is
  needed: those gate the plugin's JS API, and our commands reach it from Rust).
  The manifest is `latest.json` on the GitHub release, assembled by
  `.github/scripts/build-updater-manifest.mjs`. The App Store build drops it with
  `--no-default-features`, which removes the plugin and flips `get_shell_info`'s
  `autoUpdate` to false; the two commands stay compiled as inert stubs so the
  capability files are identical across builds. **The minisign private key is not
  recoverable** — losing it means no installed copy will ever accept another
  update.
- **macOS distribution** is Developer ID + a notarized DMG, *not* the App Store.
  The sandbox cannot host a PyInstaller sidecar and embedded interpreters draw
  rejections — see the engine consolidation review (duct-cloud, private) §8.2.
  Config is `src-tauri/tauri.conf.json` (`bundle.macOS`) +
  `src-tauri/Entitlements.developerid.plist`. The App Store variant
  (`tauri.appstore.conf.json`, `Entitlements.appstore.plist`,
  `.github/workflows/desktop-testflight.yml`) is retained only for the thin
  client that predates the sidecar; do not add the sidecar to it. That workflow
  is **manual-only** — `bundle.resources` now always declares the sidecar, which
  an App Store build cannot host, so it fails on every desktop change until the
  appstore overlay overrides `bundle.resources`.

## Rules

- Keep this shell thin: no agent code, prompts, or secrets ever ship here.
- Provider keys live only in the OS keychain — never write them to disk or logs.
- Any origin the webview loads must be listed under `remote.urls` in
  `src-tauri/capabilities/default.json` for `invoke` to work.
- **A new `#[tauri::command]` needs three edits, not one.** Add it to
  `generate_handler!` in `src/lib.rs`, to `AppManifest::commands` in `build.rs`,
  and as `allow-<kebab-command>` in every capability that needs it. App commands
  are allowed by default only for *local* content — this window loads a remote
  origin, and a capability can only grant permissions that exist, so skipping
  `build.rs` makes the command unreachable with
  `<command> not allowed. Plugin not found`. The JS side swallows that
  (`getShellInfo()` returns null, `providerKeys.js` degrades), so it fails
  silently rather than loudly.
- Local dev origins live in `capabilities/dev-localhost.json`, kept out of
  release builds by `app.security.capabilities` in `tauri.conf.json` (unset
  means *all* capability files ship). Only `tauri.dev.conf.json` opts it in.
- `app.security.capabilities` selects which files are *loaded*, but `tauri-build`
  **validates every file in `capabilities/`** regardless. So a capability naming
  a permission from a conditionally-compiled plugin fails the build for
  configurations that never load that file — which is what a separate `updater`
  capability did to the `--no-default-features` App Store build. Keep permissions
  from optional plugins out of `capabilities/` entirely.
- Building needs platform webview libraries (see `README.md`); it does not build
  in the Claude-on-the-web container — build, sign, and release locally or in CI.
- `Cargo.lock` is committed; refresh it with `cargo generate-lockfile` (or a
  build) when dependencies change, and commit the result.
- The desktop sidecar runs **Alembic**, not `create_all` (`backend/db/migrate.py`).
  Every new migration must therefore be SQLite-safe — JSON columns via
  `sa.JSON().with_variant(JSONB, 'postgresql')`, `alter_column` inside
  `op.batch_alter_table`. The pre-baseline revisions are Postgres-only and are
  never replayed; `backend/tests/test_desktop_migrations.py` guards the path
  that is.
- Changes to `src-tauri/Entitlements.appstore.plist` alter what the sandbox
  allows. Adding an entitlement without a real need invites App Review questions;
  removing `app-sandbox` breaks the upload outright (CI checks for it).
- `src-tauri/Entitlements.developerid.plist` is the opposite case: every key in
  it is load-bearing for the embedded CPython interpreter under the hardened
  runtime. Removing one does not harden the app, it makes the sidecar crash at
  launch. It deliberately carries no `app-sandbox` key.
- `bundle.macOS` config uses `deny_unknown_fields` — a mistyped key fails the
  build rather than being ignored. Key names are camelCase
  (`minimumSystemVersion`, `hardenedRuntime`, `entitlements`).

## Versioning

The shell is the monorepo's only versioned installable — `app/` and `backend/`
deploy continuously and have no version ritual. The shell version is
`MAJOR.MINOR.PATCH`, digits and dots only (Apple rejects suffixes like
`-beta`), and lives in **two files that must always match**:
`src-tauri/tauri.conf.json` `version` and `src-tauri/Cargo.toml` `version`.
Refresh `Cargo.lock` after changing Cargo.toml; `get_shell_info` reports the
Cargo value to the web app.

SemVer here is measured against the **shell↔web contract**: the invoke
commands, the `get_shell_info` capability flags, the `ai.getduct.desktop://`
deep-link scheme, the keychain service/format, and the origins allowed to
invoke. Bump in the same PR as the change, at most one bump per PR:

- **MAJOR** — a capable web app or existing user data breaks against the new
  shell: removing or renaming an invoke command or capability flag, changing
  the deep-link scheme or keychain service name, raising
  `minimumSystemVersion`. `1.0.0` itself is reserved for the first public
  (non-TestFlight) release.
- **MINOR** — new capability, backwards compatible: a new invoke command, a
  new capability flag, a new deep-link route, a new entitlement.
- **PATCH** — behaviour fixes with no contract change: bug fixes, security
  fixes, UI/icon polish, dependency bumps.
- **No bump** — nothing that ships in the bundle changed: CI workflow edits,
  docs, comments. Markdown-only changes under `desktop/` are excluded from the
  TestFlight workflow's path filter for the same reason. Rebuilds of the same
  version are already distinguished by the CI-stamped build number.

While the version is `0.y.z` (pre-GA), contract-breaking changes bump MINOR
instead of MAJOR — but must still be called out in the PR description.

Never set the build number by hand — CI stamps the GitHub run number as
`CFBundleVersion`, which App Store Connect requires to keep increasing — and
never gate web-app behaviour on the version string; probe
`get_shell_info().capabilities` instead.
