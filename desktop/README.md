# Duct Desktop

The Duct web app in a native window: model keys stay in your computer's
keychain and sign-in happens in your own browser. For anyone deciding to
download, build or self-host it, and for contributors who develop or release it.

## Start here

| I want to… | Read |
|---|---|
| Know what I download and where my keys go | [Two builds, one shell](#two-builds-one-shell) |
| Run Duct with no Duct servers | [Build your own](#build-your-own) |
| Work on the shell | [Develop](#develop-against-the-hosted-or-a-local-stack) |
| Test sign-in on my machine | [Test browser sign-in](#test-browser-sign-in-with-a-dev-bundle) |
| Ship or sign a release | [RELEASING.md](RELEASING.md) |
| Know what it reports | [Telemetry](#if-you-built-it-it-reports-nothing) |

## Run it

```bash
cd desktop
npm install
npm run dev          # the window loads the hosted app
npm run dev:local    # the window loads a local app and API (see Develop)
npm run build        # installers land in src-tauri/target/release/bundle
```

## Two builds, one shell

The shell shows the web app in a native window, keeps bring-your-own model
keys in the OS keychain, and runs sign-in in the system browser
([why](AGENTS.md)). The web app loads from the hosted URL, so a frontend
change needs no desktop release.

| | Official download | Self-host build |
|---|---|---|
| Inside | The Rust shell only, tens of megabytes | The shell plus the whole backend frozen by PyInstaller, 400 to 500 MB |
| Backend | Duct's hosted API | A local "sidecar" process: SQLite in your data folder, loopback only |
| Code on your disk | No Python, no prompts | Everything under `backend/`, prompts included |
| Your model key | Sent to the hosted API for one request; stored only if you save it | Spent on your own machine |

One config entry, `bundle.resources`, decides which you get; the Rust is
identical and probes at start-up ([why](AGENTS.md)). Key routes and safe
claims: [table](#where-your-model-key-goes).

> **Rule:** if a build ships the sidecar, treat every file under `backend/` as
> being on the user's disk, because it is.

## Develop against the hosted or a local stack

`npm run dev` loads the hosted web app and is enough for most shell work. For
a local stack:

1. **Start the API.** Skip this if you built the sidecar (below): the shell
   starts its own.
   ```bash
   cd backend && poetry run uvicorn server:app --port 8002 --reload
   ```
2. **Start the shell against the local app.** It also starts the Next dev
   server.
   ```bash
   cd desktop && npm run dev:local   # the web app falls back to the local API while NEXT_PUBLIC_API_BASE is unset
   ```
3. **Edit.** Web changes hot-reload; only Rust changes need a restart.

**Check it worked:** the window shows sign-in and saving a model key succeeds.
Editor launches: [table](#editor-launches).

### Add the local backend (sidecar)

For a local backend, or any build that runs without Duct's servers. Freeze it
once by hand; the `pre*` hooks then refreeze it whenever the backend moves
ahead, about three minutes extra.

```bash
cd backend && poetry install --with dev
npm --prefix desktop run sidecar   # ~3 min, writes backend/dist/duct-sidecar/; the hooks stay silent until this exists
```

The shell starts it on a loopback port and the web app repoints at it
([how](AGENTS.md)). Alembic owns its schema, so every migration must also run
on SQLite ([rules](AGENTS.md)).

> **Gotcha:** never run PyInstaller yourself; it empties the folder a running
> dev app executes from. The script stages and swaps ([why](AGENTS.md)).

## Test browser sign-in with a dev bundle

Signing in and connecting a data source return from the system browser by
deep link, which needs a real bundle: macOS registers the scheme from a
bundle's Info.plist, and `tauri dev` runs a bare binary.

1. **Build the dev variant.** Its own name, identifier and link scheme let it
   coexist with an installed Duct; on macOS it also installs itself into
   `/Applications`.
   ```bash
   cd desktop && npm run build:dev    # debug: fast, a real .app, no DMG (which would need signing)
   open "src-tauri/target/debug/bundle/macos/Duct Dev.app"
   ```
2. **Point the relay page at it.** Set `NEXT_PUBLIC_SHELL_SCHEME` in
   `app/.env.local` to the dev identifier from `tauri.dev.conf.json`.
   Deployed builds leave it unset.
3. **Sign in.** Web changes still hot-reload; only Rust changes need a rebuild.

**Check it worked:** the browser returns you to the dev window, signed in. The
link carries a single-use code, never a credential ([why](AGENTS.md)).

## Releases build themselves on main

A push to `main` that changes `desktop/` (Markdown excluded) builds, signs,
notarizes and publishes every platform; installed apps update through a corner
toast, never a forced restart. Details: [RELEASING.md](RELEASING.md).

## If you built it, it reports nothing

| | App downloaded from getduct.ai | Anything you build yourself |
|---|---|---|
| Crash reporting compiled in | Yes | No, not even linked |
| Analytics | PostHog, in memory only, from the web view and the shell | None unless your web app sets one |
| Default | On | Off |
| Switch in the app | Yes | Yes, with nothing to switch |

Crash reporting is an opt-in Cargo feature and the on-by-default flag is set
only in the release workflow: absent, not disabled. **Check it:** in
`src-tauri`, `cargo tree -e features -i reqwest | grep -c blocking` prints 0
without the feature; the sending code needs that and is not compiled. Sent and
never sent: [table](#what-the-downloaded-app-sends).

**Turning it off:** account menu, *Models & providers*, *Crash reports &
usage*. One switch covers shell, bundled backend, web view and analytics; your
answer sticks, and an unreadable preference file counts as off.

**Swapping the vendor:** one Rust file behind four functions, one web file per
analytics provider ([crash reporting](AGENTS.md),
[analytics seam](../app/src/lib/analytics/index.js)); a self-hosted collector
needs no code change.

## Build your own

The repository is MIT and the shell is meant to be forked. Five things
identify Duct's build, and all of them are configuration.

1. **Ship a backend.** Freeze the sidecar first
   ([above](#add-the-local-backend-sidecar)); the overlay restores the
   resource entry.
2. **Load your page.** Replace every `example` value in
   `tauri.selfhost.conf.json`: window URL, product name, update endpoint,
   identifier and link scheme. Keeping the official scheme intercepts an
   installed Duct's sign-in callbacks.
3. **Allow your origin to call the shell** in `capabilities/selfhost.json`.
4. **Use your own Google sign-in.** Create a **Desktop app** client and put
   both halves in `backend/.env.local`; the build bakes them in.
   ```
   GOOGLE_DESKTOP_OAUTH_CLIENT_ID=…
   GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET=…
   ```
5. **Build.**
   ```bash
   cd desktop && npm run build:selfhost
   ```

The consent screen names the client's owner, so your users should not be asked
to trust "Duct". Telemetry needs no step; nothing reports unless compiled in.
Failures: [If a fork fails](#if-a-fork-fails).

Code signing is the one thing you cannot copy: the certificates and updater
key are Duct's legal identity, so a fork builds unsigned or signs with its own.

## Reference

### Prerequisites

| Need | For |
|---|---|
| Rust (stable), Node 22+ | The shell |
| Python 3.12 + Poetry | The sidecar only |
| [Tauri platform libraries](https://tauri.app/start/prerequisites/) | Building anywhere |
| Debian/Ubuntu: `libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev libsoup-3.0-dev libdbus-1-dev` | Linux builds; D-Bus talks to the keychain |
| A running keyring daemon (gnome-keyring, KWallet, KeePassXC) | Linux at runtime; the shell says so when none is found |

### Scripts

| Command | Does |
|---|---|
| `npm run dev` | `tauri dev` against the hosted app |
| `npm run dev:local` | `tauri dev` with `tauri.local.conf.json`: starts the Next dev server and loads it |
| `npm run build` | Release build; needs the updater key ([RELEASING.md](RELEASING.md)) |
| `npm run build:dev` | Debug `.app` with `tauri.dev.conf.json`; no key; installs to `/Applications` on macOS |
| `npm run build:selfhost` | Release build with `tauri.selfhost.conf.json`; ships the sidecar |
| `npm run sidecar` | Freeze the backend into `backend/dist/duct-sidecar/` |
| `npm run install:dev-app` | Copy the dev bundle to `/Applications` again |
| `pre*` hooks | `scripts/ensure-sidecar-fresh.mjs` refreezes a stale sidecar before every sidecar-shipping script |

### Config overlays

| File | Sets |
|---|---|
| `src-tauri/tauri.conf.json` | Base: hosted window URL, identifier, updater endpoint, empty `bundle.resources` |
| `src-tauri/tauri.local.conf.json` | Dev URL, and the command that starts the Next dev server |
| `src-tauri/tauri.dev.conf.json` | Dev product name, identifier and scheme; updater archives off; adds `capabilities/dev-localhost.json` |
| `src-tauri/tauri.selfhost.conf.json` | Fork template: sidecar resource, self-host entitlements, `capabilities/selfhost.json` |
| `src-tauri/capabilities/default.json` | The hosted origin may call shell commands ([rules](AGENTS.md)) |
| `src-tauri/capabilities/dev-localhost.json` | A dev bundle may be called from the local dev server. `tauri dev` needs no entry: it treats the dev URL as the app's own origin |
| `src-tauri/capabilities/selfhost.json` | A fork's origin; template |

### Environment variables

| Variable | Where | Effect |
|---|---|---|
| `DUCT_SKIP_SIDECAR_CHECK=1` | Any sidecar build | Bundle a known-stale freeze anyway |
| `DUCT_SIDECAR_BIN` | Running the shell | Use a sidecar built elsewhere |
| `GOOGLE_DESKTOP_OAUTH_CLIENT_ID`, `_SECRET` | `backend/.env.local`, baked by `build.rs` | Google installed-app sign-in client |
| `NEXT_PUBLIC_SHELL_SCHEME` | `app/.env.local` | Which shell the relay page hands the sign-in code to |
| `NEXT_PUBLIC_ANALYTICS_PROVIDER` | Web app build | `posthog`, `gtm`, both (comma-separated) or `none`; unset runs whichever has its key |
| Signing and telemetry flags | Release builds | [RELEASING.md](RELEASING.md) |

### Platforms at runtime

| | macOS | Windows | Linux |
|---|---|---|---|
| Keychain | Keychain | Credential Manager | Secret Service, needs a keyring daemon |
| Sidecar data folder | `~/Library/Application Support/<bundle identifier>/` | `%APPDATA%\Duct` | `~/.local/share/duct` |
| In the folder | `duct.db`, `uploads/`, the telemetry preference. The local API key and session secret live in the keychain while the shell runs, with a file fallback for a headless sidecar | same | same |
| Reset the install | Delete the folder | same | same |

### Where your model key goes

| | Official download | Self-host build |
|---|---|---|
| Credentials inside | None | None: the sidecar mints its own local secrets on first run |
| Route | From the keychain to the hosted API, in a request header | From the keychain to a process on the same machine |
| Held by Duct's servers | For the life of one request, then discarded | Never |
| Stored by Duct's servers | Only if you save it yourself, encrypted ([service](../backend/service/provider_keys.py)) | No |
| Duct's own key | Never spent for you: the fallback is allowed only where the env file belongs to whoever runs the process ([the rule](../backend/agents/engines.py)) | The env file's key counts as yours |
| Compiled in, not secret | A crash-report address (crash-reporting builds only) and Google's installed-app sign-in client, which names the app and does not authorise it | Your own Google client |
| Safe to say | "Never stored unless you save it" | "Never leaves your machine" |

### What the downloaded app sends

Only while the switch is on.

| | |
|---|---|
| Crashes | From the shell: the panic message and stack, with your home folder replaced by `~`, under a random install id rather than your account. From the web view: the error and stack trace, page path without its query, and your account id if signed in ([web view reporter](../app/src/lib/analytics/posthog.js)) |
| Usage | Which screens and features you open, page views and clicks (the element, never its text), under your account id if signed in. Held in memory, so nothing is stored on your machine and there is no consent bar; never a session replay. No tag container either: the keychain bridge trusts every script on the page, so only bundled code measures |
| Never | Your model keys, connected-tool data, uploads, or anything an agent writes for you |

### If a fork fails

| You see | Do this |
|---|---|
| The build fails on a missing resource path | Freeze the sidecar first: `npm --prefix desktop run sidecar` |
| The app renders, then every command fails with "not allowed. Plugin not found" | Add your origin to `capabilities/selfhost.json`; it looks like a broken keychain and is not |
| Sign-in fails at the token exchange, several screens in | The client id and secret come from different Google projects; change both together |
| A Google *web* client never completes | Only a *Desktop app* client accepts a loopback redirect on any port |
| macOS refuses to open an unsigned fork | Right-click, then Open, on first launch |

### Editor launches

| Editor | Entry | Runs |
|---|---|---|
| VS Code | Desktop: Tauri dev (sidecar backend) | `dev:local` with the frozen sidecar; no sign-in needed |
| VS Code | Duct: Desktop + API | Local API, Next dev server and the registered dev bundle |
| VS Code | Duct: Desktop + API + Phoenix | The same, with every agent turn traced into Phoenix; the sidecar learns the collector from a second `open --env`, since launchd inherits nothing |
| Zed | Desktop: Tauri dev (sidecar backend), Duct: Desktop + API | The same two, as tasks (Zed has no compounds) |
| Both | Duct: stop everything | Quits what a session started; a launched dev app outlives its debug session |

### Go deeper

| | |
|---|---|
| [Engineering rules for this folder](AGENTS.md) | Splash, keychain, deep links, notifications, menu, signing, versioning |
| [Design plan](../docs/engineering/2026-06-18-tauri-desktop-byo-keys-plan.md) | Why a Tauri shell and BYO keys |
| [RELEASING.md](RELEASING.md) | CI release, signing keys, updater, platform table |
| [Sidecar spec](../backend/duct_sidecar.spec) | What the freeze includes and how big it is |
| [Schema management](../backend/db/migrate.py) | Alembic on SQLite |
