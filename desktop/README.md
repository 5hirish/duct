# Duct Desktop

A thin [Tauri v2](https://tauri.app) shell around the hosted Duct web app. Its
job is small and deliberate:

1. Render the existing Duct frontend in a native window — the agent and prompts
   stay server-side on Railway, so nothing proprietary ships in this bundle.
2. Store **bring-your-own provider API keys** in the OS keychain and expose
   read/write to the web app via Tauri commands.

Full design: [`docs/engineering/tauri-desktop-byo-keys-plan.md`](../docs/engineering/tauri-desktop-byo-keys-plan.md).

## Architecture

- **UI** loads from the hosted URL (`app.getduct.ai`), set in
  `src-tauri/tauri.conf.json` (`app.windows[0].url`). Frontend updates ship via
  the normal Cloudflare deploy — no desktop release needed for UI changes. (GA
  upgrade path: bundle a static export instead; it's a config flip.)
- **Keychain:** `src-tauri/src/lib.rs` exposes `get_provider_key`,
  `set_provider_key`, `delete_provider_key`, backed by the `keyring` crate
  (macOS Keychain / Windows Credential Manager / Linux Secret Service). The web
  app calls these through `window.__TAURI__.core.invoke` — see
  `app/src/lib/providerKeys.js`, which auto-detects the desktop shell.
- **Remote access:** `src-tauri/capabilities/default.json` lists the hosted
  origin under `remote.urls` so the loaded page is allowed to invoke commands.

## Prerequisites

- Rust (stable) + Node 22+.
- Platform libraries for Tauri — see <https://tauri.app/start/prerequisites/>.
  On Debian/Ubuntu: `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `librsvg2-dev`,
  `libsoup-3.0-dev`, and `libdbus-1-dev` (Linux keychain / Secret Service).

## Develop

```bash
cd desktop
npm install
npm run dev      # tauri dev — opens the native window
```

To point at a local backend during development, change the window `url` in
`src-tauri/tauri.conf.json` to your local app (e.g. `http://localhost:3003`).

## Build

```bash
cd desktop
npm run build    # tauri build — installers land in src-tauri/target/release/bundle
```

## Releasing (later)

- **Signing:** Apple Developer ID (macOS notarization) and an Authenticode
  certificate (Windows). Until signed, users see OS warnings.
- **Auto-update:** `tauri-plugin-updater` against a manifest (e.g. R2). Not wired
  yet — the alpha is manual distribution.

## Not in this bundle

No agent code, no prompts, no API keys. The keychain holds only the user's own
provider keys; everything proprietary stays on the Railway backend.
