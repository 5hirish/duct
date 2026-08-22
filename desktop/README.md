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
npm run dev        # tauri dev — window loads the hosted app.getduct.ai
npm run dev:local  # tauri dev against a local app + API (see below)
```

`dev:local` applies `src-tauri/tauri.local.conf.json`, which starts the Next dev
server for you (`npm --prefix ../app run dev`, port 3003) and points the window
at it. Start the API yourself first — with `NEXT_PUBLIC_API_BASE` unset, the web
app falls back to `http://localhost:8002` outside production:

```bash
cd backend && poetry run uvicorn server:app --port 8002 --reload
```

From VS Code, the **`Duct: API + Desktop`** compound in `.vscode/launch.json`
runs both in one go (uvicorn on 8002 + `dev:local`) and stops uvicorn on exit.

Keychain `invoke` works from the dev server because `http://localhost:3003` is
already listed under `remote.urls` in `src-tauri/capabilities/default.json`.

### Testing Google sign-in locally

Every leg of the desktop sign-in flow works against a local stack — the backend
redirects to `{frontend_origin}/desktop-auth` (`routes/signin.py`), which
defaults to `http://localhost:3003`, and that relay page fires the deep link.
The one leg that needs more than `tauri dev` is the final browser → app hop:
macOS registers `ai.getduct.desktop://` from a bundle's Info.plist, and
`tauri dev` runs a bare binary out of `target/debug/`, not a `.app`.

Build the **dev variant** instead. `src-tauri/tauri.dev.conf.json` gives it its
own product name, bundle identifier (`ai.getduct.desktop.dev`), and deep-link
scheme, so it coexists with an installed TestFlight build instead of fighting it
for the same scheme:

```bash
npm run build:dev   # tauri build --debug --bundles app --config src-tauri/tauri.dev.conf.json
open src-tauri/target/debug/bundle/macos/"Duct Dev.app"
```

Set the matching scheme in `app/.env.local` so the relay page hands the code to
the dev shell rather than the production one:

```
NEXT_PUBLIC_SHELL_SCHEME=ai.getduct.desktop.dev
```

Deployed builds leave that unset and fall back to `ai.getduct.desktop`. The
window URL still points at the dev server, so the web app keeps hot-reloading —
only Rust changes need a rebuild.

`--debug` keeps the compile fast while still producing a real `.app` (an
Info.plist is what registers the scheme); `--bundles app` skips DMG packaging,
which needs signing config that isn't set up locally.

## Build

```bash
cd desktop
npm run build    # tauri build — installers land in src-tauri/target/release/bundle
```

## Releasing

### macOS — TestFlight (internal testers)

Pushes to `main` touching `desktop/**` build a sandboxed, universal Mac App
Store package and upload it to TestFlight via
[`.github/workflows/desktop-testflight.yml`](../.github/workflows/desktop-testflight.yml).
Full setup — Apple prerequisites, the GitHub secrets, and troubleshooting — is in
[`docs/engineering/desktop-testflight-release.md`](../docs/engineering/desktop-testflight-release.md).

The App Store build uses three extra files alongside the normal config:

| File | Purpose |
|---|---|
| `src-tauri/tauri.appstore.conf.json` | Overlay: `app` bundle target, sandbox entitlements, `hardenedRuntime: false` (it defaults to **true**, which is for Developer ID, not the App Store), `minimumSystemVersion: 12.0` |
| `src-tauri/Entitlements.appstore.plist` | App Sandbox + network client + file access. CI injects the three team-scoped keys so the Apple Team ID stays out of git |
| `src-tauri/Info.plist` | Merged into the bundle: `LSApplicationCategoryType` (required for the App Store) and `ITSAppUsesNonExemptEncryption` |

Two constraints come with this channel, both deliberate:

- **No auto-update.** App Store apps may not self-update, so
  `tauri-plugin-updater` must stay out of this build.
- **Sandboxed keychain.** Provider keys saved by an unsandboxed DMG build are not
  visible to the App Store build, and vice versa — testers moving between
  channels re-enter their keys once.

Testing stays **internal-only**: the window loads a remote URL, which is a common
App Review Guideline 4.2 rejection. Internal testing skips beta review; an
external group would not.

### Windows / Linux (later)

- **Signing:** an Authenticode certificate (Windows). Until signed, users see OS
  warnings.
- **Auto-update:** `tauri-plugin-updater` against a manifest (e.g. R2). Not wired
  yet — and it must remain disabled for the macOS App Store build.

## Not in this bundle

No agent code, no prompts, no API keys. The keychain holds only the user's own
provider keys; everything proprietary stays on the Railway backend.
