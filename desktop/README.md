# Duct Desktop

A [Tauri v2](https://tauri.app) shell that renders the Duct web app in a native
window and runs Duct's backend beside it, on the user's own machine:

1. Render the existing Duct frontend in a native window. The UI is *loaded* from
   a URL (`app.getduct.ai`) rather than bundled — a frontend change ships
   through the normal Cloudflare deploy, with no desktop release.
2. Run the whole FastAPI backend locally as a **sidecar** — SQLite in the
   per-user data dir, loopback-only, no Railway round trip. The web app repoints
   its API base at it during boot.
3. Store **bring-your-own provider API keys** in the OS keychain and expose
   read/write to the web app via Tauri commands.

So the only thing this build needs from Duct's infrastructure is the page it
loads. Projects, connector tokens, insights and every model call stay on the
machine, spent against the user's own provider key.

> Earlier versions of this file said the agent and prompts stayed server-side
> and that nothing proprietary shipped in the bundle. That was true of the thin
> client this replaced. **The sidecar freezes the entire `backend/` package** —
> agents, prompts and all — into every installer. Anything you would not ship to
> a user's disk does not belong in `backend/`.

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

### macOS — Developer ID + notarized DMG

Pushes to `main` touching `desktop/**` or `backend/**` build the sidecar, sign
it and the app with a Developer ID Application certificate, notarize, staple and
produce a DMG — [`.github/workflows/desktop-release.yml`](../.github/workflows/desktop-release.yml).

This is the only macOS channel, and the only one it could be. The Mac App Store
sandbox cannot host a PyInstaller sidecar and embedded interpreters draw
rejections (review §8.2 (duct-cloud, private)), so an App Store build could
only ever have shipped the pre-sidecar thin client — a different, worse product
wearing the same name. **That channel was retired on 2026-09-06** along with its
workflow, its two overlay files and the `ITSAppUsesNonExemptEncryption` key.
Do not reintroduce it without first solving the sandbox problem; nothing about
it has changed.

What Developer ID buys, all of it load-bearing here:

- **Auto-update is allowed** (`tauri-plugin-updater`), which App Store rules
  forbid — see [Auto-update](#auto-update).
- **Windows and Linux ship from the same pipeline** — see below.
- **Unsandboxed keychain**, so the sidecar can reach the user's provider keys
  and their data dir without an entitlement fight.

Signing order is the fragile part and is handled explicitly in the workflow: the
sidecar's hundreds of nested Mach-O files are signed *before* the enclosing
`.app` is re-sealed. `codesign --deep` is deprecated and does not do this
reliably.

The `updater` cargo feature in `Cargo.toml` existed to strip the plugin for
App Store builds via `--no-default-features`. With that channel gone it has no
consumer — a feature flag no build exercises is one that quietly stops
compiling. Either delete it or find it a real use.

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

Every channel self-updates via `tauri-plugin-updater` — there is no longer one
that cannot.
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

## What is and is not in this bundle

**In it:** the whole `backend/` package, frozen by PyInstaller — routes, models,
migrations, agent code and prompts. Treat every file under `backend/` as
shipped, because it is.

**Not in it:** any credential. Not a provider key, not a database URL, not a
Railway token — `duct_sidecar.spec` bundles `alembic/` and `alembic.ini` and
nothing else, and the sidecar generates its own local API key and JWT secret on
first run, 0600 in the user's data dir. Two values *are* compiled in and neither
is a production secret: `SENTRY_DSN` (write-only by design, and inert unless the
user opts in) and the Google **installed-app** OAuth credential, which Google
documents as non-confidential — it names the app, it does not authorise it.

The user's own provider key never reaches Duct either: it goes to the OS
keychain and is spent from the local sidecar. `resolve_provider_key` in
`backend/agents/engines.py` will only fall back to an env key when
`allow_server_provider_keys()` says the env file belongs to whoever is running
the process, which on a desktop install means the user themself.

## Build your own

The repo is MIT and this shell is meant to be forkable — someone should be able
to run Duct end to end without touching Duct's infrastructure. Three things are
Duct-specific, and all three are configuration rather than code:

**1. The page it loads.** `app.getduct.ai` is the default window URL. Point it
at your own deployment of `app/` with a config overlay — the same mechanism
`dev` and `dev:local` already use. Start from the template:

```bash
cp src-tauri/tauri.selfhost.conf.json src-tauri/tauri.mine.conf.json
# replace every getduct.example value, then:
npm run build:selfhost   # tauri build --config src-tauri/tauri.selfhost.conf.json
```

Change the `identifier` and the deep-link scheme too. The OS routes
`ai.getduct.desktop://` to whichever app claimed it, so a fork that keeps the
official scheme will intercept an installed Duct's sign-in callbacks — and hand
it its own.

**2. The origin allowed to call the shell.** A window URL on its own is not
enough: `capabilities/*.json` lists which origins may `invoke`. The overlay
selects `capabilities/selfhost.json`; put your origin in it. Skip this and the
app loads and renders perfectly, then fails every command with *"not allowed.
Plugin not found"* — which looks like a broken keychain rather than a config
gap.

**3. Google sign-in.** Duct's OAuth client is the built-in default, and the
consent screen names whoever owns the client — your users should not be asked to
grant access to "Duct". Create your own **Desktop app** client in Google Cloud
(a *web* client cannot work: the sidecar's redirect URI is
`http://127.0.0.1:<random>/…` and only desktop clients accept a loopback address
on any port), then put both halves in `backend/.env.local`:

```
GOOGLE_DESKTOP_OAUTH_CLIENT_ID=…apps.googleusercontent.com
GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET=…
```

`build.rs` bakes them in from there, so the same file configures the sidecar at
runtime and the shell at compile time. Override them together — an id from one
Google project beside a secret from another fails at the token exchange, several
screens after the user last had a chance to notice.

Not configuration, and not shareable: **code signing**. The Developer ID
certificate, notarization password and updater signing key in
`.github/workflows/desktop-release.yml` are Duct's identity, issued by Apple to
a legal entity. A fork builds unsigned (macOS Gatekeeper will need a
right-click → Open on first launch) or signs with its own. This is how every
open-source desktop project works — the source is shared, the signature is not.
