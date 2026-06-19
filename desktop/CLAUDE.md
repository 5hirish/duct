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

## Rules

- Keep this shell thin: no agent code, prompts, or secrets ever ship here.
- Provider keys live only in the OS keychain — never write them to disk or logs.
- Any origin the webview loads must be listed under `remote.urls` in
  `src-tauri/capabilities/default.json` for `invoke` to work.
- Building needs platform webview libraries (see `README.md`); it does not build
  in the Claude-on-the-web container — build, sign, and release locally or in CI.
- `Cargo.lock` is generated on the first local build; commit it once produced.
