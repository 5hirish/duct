# Release the desktop app

A push to main that changes the desktop folder produces one GitHub Release:
signed installers for three platforms and the manifest installed apps poll.
Nothing is released from a branch or a laptop.

**Before you start:** the shell version must match in the Tauri config and
the Cargo manifest, and the release secrets must already be in GitHub
([versioning and secrets staging](AGENTS.md)).

1. **Merge to main.** The workflow skips Markdown-only changes in the desktop
   folder and runs for everything else there
   ([release workflow](../.github/workflows/desktop-release.yml)). Pull
   requests only compile-check
   ([compile check](../.github/workflows/desktop-check.yml)).
2. **Wait for three runners.** Each OS builds on its own, because Tauri
   bundles are not cross-compiled. macOS signs and notarizes in one Tauri
   pass, now that the bundle holds no nested binaries.
3. **Open the release.** It is tagged `desktop-v<version>` and carries every
   bundle plus `latest.json`. The manifest builder leaves out any archive
   without a signature beside it
   ([script](../.github/scripts/build-updater-manifest.mjs)).

**Check it worked:** the manifest lists macOS under both Mac platform keys.
The build is universal, but the updater matches an exact key, so a missing
second key leaves every Intel Mac polling forever.

## Developer ID is the only macOS channel

The Mac App Store sandbox cannot host the sidecar, and embedded interpreters
draw rejections, so that channel was retired on 2026-09-06
([why not to revive it](AGENTS.md)). Developer ID buys three things, all
load-bearing:

- **Self-update is allowed**, which App Store rules forbid.
- **Windows and Linux ship from the same pipeline.**
- **The keychain is unsandboxed**, so a sidecar can reach the user's keys and
  data folder.

Updates reach users as a corner toast, never a forced restart. Agent sessions
are long, and losing one to a surprise relaunch is worse than a stale build.

> **Gotcha:** the updater's minisign private key cannot be regenerated. Lose
> it and no installed copy accepts another update; every user reinstalls by
> hand. Keep a backup outside CI.

## A release build on your own machine needs the updater key

Updater archives are signed at build time, so `npm run build` stops with
"A public key has been found, but no private key" until it finds the key:

```bash
export TAURI_SIGNING_PRIVATE_KEY_PATH=~/.tauri/duct-updater.key
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=      # empty: the key has no passphrase
cd desktop && npm run build
```

`npm run build:dev` needs no key: the dev overlay turns updater archives off,
which `--bundles app` alone does not ([rules](AGENTS.md)).

## A sidecar build changes the release

Both differences come from the size of a frozen Python tree.

| | Thin shell (today) | Sidecar build |
|---|---|---|
| macOS architecture | Universal: Intel and Apple silicon | Apple silicon only; a universal tree is about 600 MB |
| Signing | One Tauri pass | Hundreds of nested binaries, signed innermost-first before the app is sealed |

## If it fails

| You see | Do this |
|---|---|
| SmartScreen warns on Windows | Expected: Windows builds are not Authenticode-signed yet |
| macOS missing from `latest.json` | Keep `app` in `--bundles` next to `dmg`; only `app` emits the update archive ([rules](AGENTS.md)) |
| Windows missing from `latest.json` | The installer's signature is `*-setup.exe.sig`; the job checks for it explicitly |
| "A public key has been found, but no private key" | Export the updater key (above) |

## Reference

### Platforms

| | macOS | Windows | Linux |
|---|---|---|---|
| Runner | `macos-latest`, universal | `windows-latest` | `ubuntu-22.04`: its glibc sets the oldest distro the AppImage runs on |
| Bundles | `.app`, DMG, updater archive | NSIS `-setup.exe` | `.deb`, AppImage |
| Signing | Developer ID + notarization | None: Authenticode needed | Unsigned by convention |
| Build flags | `--features crash-reporting --target universal-apple-darwin --bundles app,dmg,updater` | `--features crash-reporting --bundles nsis,updater` | `--features crash-reporting --bundles deb,appimage,updater` |

### Secrets and build flags

| Variable | Where | Effect |
|---|---|---|
| `TAURI_SIGNING_PRIVATE_KEY`, `_PATH`, `_PASSWORD` | CI secret, or a local build | Signs updater archives; the password is empty by design |
| `DUCT_DEVID_CERT_P12`, `DUCT_DEVID_CERT_PASSWORD`, `DUCT_DEVID_IDENTITY`, `DUCT_APPLE_TEAM_ID` | CI secrets | Developer ID signing |
| `DUCT_ASC_API_KEY_ID`, `DUCT_ASC_API_ISSUER_ID`, `DUCT_ASC_API_KEY_P8` | CI secrets | Notarization, through the App Store Connect API key |
| `DUCT_TELEMETRY_DEFAULT_ON=1` | Release workflow only | Crash reports on unless the user opts out |
| `POSTHOG_PROJECT_TOKEN`, `POSTHOG_HOST` | CI variables, not secrets: the token is public | Crash-report destination for `--features crash-reporting` builds, compiled in; no token means the app never reports. Host defaults to PostHog's US cloud |
| `GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET` | CI secret | Second half of the Google sign-in client; the id has a default in the shell |

### Go deeper

| | |
|---|---|
| [Release workflow](../.github/workflows/desktop-release.yml) | Every step, with its reasoning in comments |
| [Updater manifest builder](../.github/scripts/build-updater-manifest.mjs) | How `latest.json` is assembled |
| [Engineering rules](AGENTS.md) | Signing, notarization, secrets staging, fixed download names, versioning |
| [README](README.md) | What the two builds are and how to develop |
