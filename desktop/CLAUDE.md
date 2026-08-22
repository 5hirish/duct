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
- **macOS distribution** is TestFlight (internal testers) via a sandboxed Mac App
  Store build — `src-tauri/tauri.appstore.conf.json` +
  `src-tauri/Entitlements.appstore.plist`, shipped by
  `.github/workflows/desktop-testflight.yml`. Runbook:
  `docs/engineering/desktop-testflight-release.md`.

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
- Building needs platform webview libraries (see `README.md`); it does not build
  in the Claude-on-the-web container — build, sign, and release locally or in CI.
- `Cargo.lock` is committed; refresh it with `cargo generate-lockfile` (or a
  build) when dependencies change, and commit the result.
- **Never enable `tauri-plugin-updater` for the macOS build.** App Store apps may
  not self-update; it would be rejected. Auto-update is only an option if macOS
  moves to Developer ID / DMG distribution.
- Changes to `src-tauri/Entitlements.appstore.plist` alter what the sandbox
  allows. Adding an entitlement without a real need invites App Review questions;
  removing `app-sandbox` breaks the upload outright (CI checks for it).
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
