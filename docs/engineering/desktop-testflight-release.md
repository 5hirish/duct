# Desktop → TestFlight (macOS) — runbook

How the Tauri desktop shell in [`desktop/`](../../desktop/) reaches macOS testers
through TestFlight, what has to exist in Apple's systems first, and the
constraints this distribution channel imposes.

Pipeline: [`.github/workflows/desktop-testflight.yml`](../../.github/workflows/desktop-testflight.yml).
App design: [`tauri-desktop-byo-keys-plan.md`](tauri-desktop-byo-keys-plan.md).

## What the pipeline does

On every push to `main` that touches `desktop/**` (and on manual dispatch):

1. Builds a **universal** (Apple Silicon + Intel) `.app` with the App Store
   config overlay — App Sandbox on, hardened runtime off.
2. Stamps `CFBundleVersion` with the workflow run number so each upload is
   unique, and embeds the Mac App Store provisioning profile.
3. Re-signs the bundle with the sandbox entitlements and **verifies** the
   signature carries `com.apple.security.app-sandbox` before going further.
4. Wraps the app in a signed `.pkg` via `productbuild`.
5. Uploads it with `asc builds upload --pkg`, then optionally assigns the build
   to an internal tester group.

Pull requests touching `desktop/**` get an unsigned build only, as a compile
gate. macOS runners bill at roughly 10× Linux, so nothing else runs there.

## Internal testers only — and why

The desktop window loads the hosted web app (`https://app.getduct.ai`) rather
than bundling a frontend. A macOS app whose entire interface is a remote website
is a well-known **App Review Guideline 4.2 ("minimum functionality")** rejection
risk.

Internal TestFlight testing — up to 100 members of your own App Store Connect
team — does **not** go through beta review, so this risk never materialises.
Adding an *external* group would submit the build for beta review and expose it.
Before considering external testing, the app needs genuine native functionality
beyond the web wrapper (the keychain provider-key store is a start, but on its
own is unlikely to satisfy a reviewer).

## Two consequences of using the App Store pipeline

**No auto-update.** Mac App Store apps may not update themselves; Apple requires
updates to ship through the store. `tauri-plugin-updater` must never be enabled
for this build. This directly supersedes the auto-update half of Phase 3 in the
desktop plan *for the App Store channel* — if auto-update matters more than
TestFlight's tester management, a notarized Developer ID DMG is the better fit.

**Sandboxed keychain.** Under App Sandbox the `keyring` crate's entries live in
the app's own keychain access group. Provider keys saved by an unsandboxed DMG
build are **not** visible to the App Store build, and vice versa. A tester who
moves between the two channels re-enters their provider keys once. This is
expected behaviour, not a bug.

## One-time Apple setup (human, not CI)

1. **Bundle ID** — register `ai.getduct.desktop` for **macOS** in the Apple
   Developer portal. It must match `identifier` in `desktop/src-tauri/tauri.conf.json`.
2. **App record** — create the macOS app in App Store Connect
   (`asc web apps create --name "Duct" --bundle-id "ai.getduct.desktop" --sku "DUCT-DESKTOP"`),
   then note the numeric app id from `asc apps`.
3. **Certificates** — two are needed, exported as `.p12`:
   - *Apple Distribution* — signs the `.app`
   - *Mac Installer Distribution* (a.k.a. "3rd Party Mac Developer Installer") —
     signs the `.pkg`
4. **Provisioning profile** — a **Mac App Store** profile for the bundle id,
   downloaded as `.provisionprofile`.
5. **App Store Connect API key** — an `AuthKey_XXXX.p8` with at least App Manager
   access, plus its key id and issuer id.
6. **Internal tester group** — create one in TestFlight and grab its id with
   `asc testflight groups list --app "APP_ID" --internal`.

Encode each file for GitHub Secrets with `base64 -i <file> | pbcopy`.

## GitHub secrets

| Secret | What it is |
|---|---|
| `DUCT_ASC_API_KEY_ID` | App Store Connect API key id |
| `DUCT_ASC_API_ISSUER_ID` | App Store Connect issuer id |
| `DUCT_ASC_API_KEY_P8` | base64 of `AuthKey_XXXX.p8` |
| `DUCT_APP_STORE_APP_ID` | numeric App Store Connect app id |
| `DUCT_APPLE_TEAM_ID` | 10-character Apple Team ID |
| `DUCT_MAS_APP_CERT_P12` | base64 of the Apple Distribution `.p12` |
| `DUCT_MAS_APP_CERT_PASSWORD` | password for that `.p12` |
| `DUCT_MAS_APP_IDENTITY` | e.g. `Apple Distribution: Duct (ABCDE12345)` |
| `DUCT_MAS_INSTALLER_CERT_P12` | base64 of the Mac Installer Distribution `.p12` |
| `DUCT_MAS_INSTALLER_CERT_PASSWORD` | password for that `.p12` |
| `DUCT_MAS_INSTALLER_IDENTITY` | e.g. `3rd Party Mac Developer Installer: Duct (ABCDE12345)` |
| `DUCT_MAS_PROVISIONING_PROFILE` | base64 of the Mac App Store `.provisionprofile` |
| `DUCT_TESTFLIGHT_INTERNAL_GROUP_ID` | *optional* — auto-assign the build to this internal group |

The Apple Team ID is deliberately not committed. CI injects the three
team-scoped entitlements (`com.apple.application-identifier`,
`com.apple.developer.team-identifier`, `keychain-access-groups`) into
`desktop/src-tauri/Entitlements.appstore.plist` at build time.

## Versioning

Marketing version comes from `version` in `desktop/src-tauri/tauri.conf.json`
(currently `0.1.0`) — bump it in a normal commit when you want a new version
string. The build number is the GitHub Actions run number, so it always
increases and never collides. Both are passed explicitly to
`asc builds upload`, which cannot read them out of a `.pkg` the way it can from
an IPA.

## Troubleshooting

**"missing the app-sandbox entitlement"** — the workflow fails on this before
uploading. Usually the entitlements injection step did not run, or
`DUCT_APPLE_TEAM_ID` is unset.

**Invalid signature / profile mismatch at upload** — the provisioning profile
must be a *Mac App Store* profile for `ai.getduct.desktop`, issued to the same
team as the signing certificates. A Developer ID or developer profile fails here.

**Build never appears in TestFlight** — App Store Connect processing can lag a
few minutes after `--wait` returns. Check `asc builds list --app "APP_ID"`.

**Config key rejected by Tauri** — `bundle.macOS` uses `deny_unknown_fields`, so
a mistyped key is a hard build error rather than a silent no-op.
