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
