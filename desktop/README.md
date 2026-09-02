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
- Python 3.12 + Poetry, to build the sidecar (below).
- Platform libraries for Tauri — see <https://tauri.app/start/prerequisites/>.
  On Debian/Ubuntu: `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `librsvg2-dev`,
  `libsoup-3.0-dev`, and `libdbus-1-dev` (Linux keychain / Secret Service).

## The sidecar

The bundle ships the Duct backend and runs it locally — no Railway round trip.
Build it before any `tauri dev`/`tauri build`, because `bundle.resources` copies
the output directory verbatim and a missing build produces an app that opens
straight to an error screen:

```bash
cd backend
poetry install --with dev
poetry run pyinstaller duct_sidecar.spec --noconfirm   # ~3 min, ~390 MB on arm64
```

That writes `backend/dist/duct-sidecar/`. The shell spawns the binary inside it,
reads one JSON handshake line (loopback URL, port, per-install API key, data
dir) and hands it to the web app, which points its API base there. Rebuild it
whenever backend code changes — the frozen copy does not pick up edits.

Runtime state lives in the per-user data dir — `~/Library/Application Support/ai.getduct.desktop/`
on macOS, `%APPDATA%\Duct` on Windows, `~/.local/share/duct` on Linux
(`duct.db`, `local-api-key`, `uploads/`). Deleting that directory resets the
install. Set `DUCT_SIDECAR_BIN` to run the shell against a sidecar built
elsewhere.

The schema is owned by **Alembic**, the same migrations the Railway deployment
runs (`backend/db/migrate.py`). A first launch builds the schema and stamps it;
later launches migrate forward. This replaced `create_all`, which created
missing *tables* only and so silently skipped every migration that added a
column to an existing one — an upgraded install would then fail at query time
with `no such column`. Consequence for anyone writing a migration: **it has to
run on SQLite too.**

## Develop

```bash
cd desktop
npm install
npm run dev        # tauri dev — window loads the hosted app.getduct.ai
npm run dev:local  # tauri dev against a local app + API (see below)
```

`dev:local` applies `src-tauri/tauri.local.conf.json`, which starts the Next dev
server for you (`npm --prefix ../app run dev`, port 3003) and points the window
at it. With a sidecar built (above), the shell spawns its own backend on a
loopback port and the web app repoints at it — nothing else to start. Without
one, start the API yourself: with `NEXT_PUBLIC_API_BASE` unset, the web app
falls back to `http://localhost:8002` outside production:

```bash
cd backend && poetry run uvicorn server:app --port 8002 --reload
```

From VS Code, **`Duct: Desktop (local sidecar)`** runs the sidecar shape, and
**`Duct: Desktop (tauri dev — no sign-in) + API`** runs uvicorn on 8002 plus
`dev:local` in one go, stopping uvicorn on exit — both in `.vscode/launch.json`.

Keychain `invoke` works from the dev server because `http://localhost:3003` is
already listed under `remote.urls` in `src-tauri/capabilities/default.json`.

### Testing browser-based OAuth locally

Both flows that leave the app for the system browser — signing in
(`routes/signin.py`) and connecting a data source (`routes/auth.py`) — work
against a local stack. The backend redirects to `{frontend_origin}/desktop-auth`,
which defaults to `http://localhost:3003`, and that relay page fires the deep
link: `//auth?auth_code=` for sign-in, `//connector?connector=&auth_code=` for a
connector. The one leg that needs more than `tauri dev` is the final
browser → app hop: macOS registers `ai.getduct.desktop://` from a bundle's
Info.plist, and `tauri dev` runs a bare binary out of `target/debug/`, not a
`.app`.

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

`bundle.createUpdaterArtifacts` is on, so a release build also produces the
update archive and its signature — which means **it needs the updater signing
key**. Without it the build stops with *"A public key has been found, but no
private key"*. Point it at your local copy:

```bash
export TAURI_SIGNING_PRIVATE_KEY_PATH=~/.tauri/duct-updater.key
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=      # empty if the key has none
```

`npm run build:dev` needs no key: `tauri.dev.conf.json` sets
`createUpdaterArtifacts: false`. Passing `--bundles app` is *not* enough on its
own — on macOS the updater archive is produced for the `app` target too, so a
dev build would otherwise fail at the very last step, after the `.app` was
already written.

## Releasing

### macOS — Developer ID + notarized DMG (current channel)

Pushes to `main` touching `desktop/**` or `backend/**` build the sidecar, sign
it and the app with a Developer ID Application certificate, notarize, staple and
produce a DMG — [`.github/workflows/desktop-release.yml`](../.github/workflows/desktop-release.yml).

This is the channel for the local-first product. The Mac App Store is not an
option for it: its sandbox cannot host a PyInstaller sidecar and embedded
interpreters draw rejections
(review §8.2 (duct-cloud, private)). The
practical consequences, all in our favour here:

- **Auto-update is allowed** (`tauri-plugin-updater`), unlike the App Store, and
  is wired up — see [Auto-update](#auto-update).
- **Windows and Linux** ship from the same pipeline — see below.
- **Unsandboxed keychain**, so provider keys saved by this build are not shared
  with any App Store build.

Signing order is the fragile part and is handled explicitly in the workflow: the
sidecar's hundreds of nested Mach-O files are signed *before* the enclosing
`.app` is re-sealed. `codesign --deep` is deprecated and does not do this
reliably.

### macOS — TestFlight (legacy thin client)

Retained for the pre-sidecar thin client only. **Do not add the sidecar to this
build** — it cannot work under the sandbox.

**This workflow is manual-only (`workflow_dispatch`).** Now that
`bundle.resources` always declares the sidecar, an App Store build fails with
`resource path ../../backend/dist/duct-sidecar doesn't exist` — the sandbox
cannot host it, so the two are structurally incompatible. Reviving the channel
means first making `tauri.appstore.conf.json` override `bundle.resources`, and
verifying the merged config really drops it. Run it from the Actions tab:
[`.github/workflows/desktop-testflight.yml`](../.github/workflows/desktop-testflight.yml).
Full setup — Apple prerequisites, the GitHub secrets, and troubleshooting — is in
the TestFlight runbook (duct-cloud, private).

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

### Windows and Linux

Built by the same workflow, each on its own runner because the PyInstaller
sidecar is per-OS and cannot be cross-compiled:

| Platform | Bundles | Signing |
|---|---|---|
| Windows | NSIS `-setup.exe` | **None yet** — needs an Authenticode certificate; SmartScreen warns on first run until then |
| Linux | `.deb`, `.AppImage` | N/A (AppImage is unsigned by convention) |

Linux runtime note: provider keys go to the freedesktop **Secret Service**, so a
keyring daemon (gnome-keyring, KWallet, KeePassXC) must be running. Without one
the shell now returns a message saying so rather than failing silently.

The Linux job pins `ubuntu-22.04` rather than `-latest` on purpose: the runner's
glibc sets the oldest distro the AppImage will start on.

## Auto-update

Every channel except the Mac App Store self-updates via `tauri-plugin-updater`.
The web app polls through the shell (`check_for_update` / `install_update` in
`src-tauri/src/lib.rs`) rather than the plugin's JS bindings, because the window
loads a remote origin that cannot import them — the same reason `providerKeys.js`
goes through `invoke`. A useful side effect: the page needs no `updater:*`
permission, since those gate the plugin's JS API and these commands reach it from
Rust. The UI is a toast in the corner
(`app/src/components/UpdateToast.jsx`), never a forced restart: agent sessions
here are long, and losing one to a surprise relaunch is worse than a stale build.

Releases are published as `desktop-v<version>` GitHub Releases carrying every
platform's bundle plus `latest.json`, the manifest the updater polls. That
manifest is assembled by
[`.github/scripts/build-updater-manifest.mjs`](../.github/scripts/build-updater-manifest.mjs),
which refuses to publish an archive with no signature beside it.

Two things to know:

- **The minisign private key is not recoverable.** Lose it and no installed copy
  will accept another update — every user would have to reinstall by hand. It
  lives in `TAURI_SIGNING_PRIVATE_KEY`; keep a backup outside CI.
- **macOS updates are arm64-only.** A universal2 sidecar roughly doubles its
  native libraries (~600 MB — see the size notes in `backend/duct_sidecar.spec`),
  so Intel Macs are offered no update rather than a broken one.

## Not in this bundle

No agent code, no prompts, no API keys. The keychain holds only the user's own
provider keys; everything proprietary stays on the Railway backend.
