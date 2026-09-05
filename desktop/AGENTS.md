# Duct Desktop — agent instructions

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
- **Browser-based OAuth**: *every* OAuth flow runs in the system browser, because
  Google refuses it inside an embedded webview and a user in one has none of
  their browser's sessions, passwords or passkeys. The web app probes
  `get_shell_info` and calls `open_external` (http/https only) to launch the
  authorize URL; the backend redirects back via a
  `ai.getduct.desktop://` deep link (tauri-plugin-deep-link) that the shell
  forwards into the webview. Two routes, same shape:
  - `//auth?auth_code=` → `/?auth_code=` — signing in to Duct
    (`capabilities.browserAuth`, `backend/routes/signin.py`).
  - `//connector?connector=&auth_code=` → `/connections?connector=&auth_code=`
    — connecting a data source (`capabilities.browserConnectors`,
    `backend/routes/auth.py`, started by `app/src/lib/connectorAuth.js`).

  **No credential ever rides in a deep link.** Any app on the machine can claim
  the scheme, so both routes carry only a single-use 60-second code that the
  webview redeems against the backend (`/auth/exchange`,
  `/auth/connectors/exchange`). This matters more for connectors than for
  sign-in: their payload is a *long-lived* Google refresh token, where the
  in-browser flow can still use a URL fragment (never sent to a server) because
  it never leaves the app's own window.

  Both flows also route their failures to the app's `/desktop-auth` relay page
  rather than raising. The system browser renders whatever the loopback sidecar
  returns, so an `HTTPException` there is a bare `{"detail": ...}` on a white
  page — a dead end reached *after* the user already approved at Google.

  New shell-dependent web flows must be gated on a `get_shell_info` capability
  flag, never on version sniffing — old shells keep the legacy path.
- **`target="_blank"` links are dead in the webview** (no tabs, no window
  opening) and are rerouted to the system browser by
  `installExternalLinkHandler` in `app/src/lib/shell.js`, mounted once by
  `LocalBackendGate`. It deliberately only touches anchors that already asked
  for a new tab; a link meant to navigate this window still does.
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
- **System notifications** go through the `notify` command
  (`tauri-plugin-notification`, registered unconditionally, so no
  `notification:*` permission is needed — the same "our command reaches the
  plugin from Rust" shape as the updater, for the same remote-origin reason).
  The web app decides *when* (`app/src/lib/notify.js`: only while the window is
  not focused) and gates on the `notifications` flag from `get_shell_info`; the
  shell only decides *how*.
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

## Crash reporting

Three processes, one consent decision (`src/telemetry.rs`):

- **The shell** initialises `sentry` in-process. Before this, a Rust panic or a
  sidecar that would not start left no trace anywhere — the webview's Sentry
  only ever sees JavaScript.
- **The sidecar** stays silent by default. `local_server.py` blanks
  `SENTRY_DSN` on purpose ("a user's laptop is not a deployment"), and
  `sidecar.rs` passes a real DSN through *only* when the user has opted in. It
  also has to pass `SENTRY_ENABLE_LOCALHOST=1`, because the sidecar binds
  127.0.0.1 and `server.py` otherwise treats that as "not deployed" and drops
  every event.
- **The webview** already reported, but was indistinguishable from a browser
  session; `instrumentation-client.ts` now tags `shell`, `shell.version` and
  `shell.localSidecar`.

Consent is opt-IN, stored as `telemetry.json` in the per-user data dir — a
preference, not a secret, so not the keychain. A missing, unreadable, or
malformed file all mean *off*: consent is never inferred from a failed read.
The DSN is compiled in via `SENTRY_DSN` — the same name the backend reads and
`backend/.env.local` already defines, so there is one spelling across all three
processes. With no DSN the whole path is inert and the settings card hides
itself rather than offering a switch that changes nothing.

The data-dir path is duplicated between `telemetry.rs` and `utils/appdirs.py`
by necessity — the shell must resolve it *before* the sidecar exists to ask.
Change one, change the other.

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
- The whole `bundle` config uses `deny_unknown_fields`, not just `bundle.macOS`
  — a mistyped key fails the build rather than being ignored, and JSON has no
  comments, so there is nowhere to explain a setting *in* the config. An
  explanatory `"comment"` key fails with `Additional properties are not allowed`.
  Explain overlay settings here or in `README.md` instead. Key names are
  camelCase (`minimumSystemVersion`, `hardenedRuntime`, `entitlements`).
- `bundle.createUpdaterArtifacts` applies to the macOS `app` target too, so
  `--bundles app` does not opt out of it. Both overlays that must not produce a
  signed archive turn it off explicitly: `tauri.dev.conf.json` (a dev build has
  no signing key, and would otherwise fail *after* writing the `.app`) and
  `tauri.appstore.conf.json`. On this app that archive is a ~160 MB gzip of the
  470 MB bundle — about 85 seconds per build.

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
