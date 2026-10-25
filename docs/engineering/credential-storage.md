# Credential storage

**Author:** Shirish Kadam · **Updated:** 2026-10-25

Where every secret Duct holds lives, what protects it, and what breaks it. Read
this before touching anything that stores a secret, the bundle identifier, the
signing identity or a keychain service name: compiling cannot check those.

## At a glance

- **Eight kinds of secret, seven protected properly.** The desktop session
  token is still too weak.
- **The keychain checks who is asking.** An update keeps access, a new
  signature loses it, and a signed release never prompts.
- **Only the shell touches the keychain.** The sidecar gets secrets through
  its environment.
- **Three changes orphan every install:** bundle identifier, Apple Team ID,
  keychain service name. CI pins them.

## Where each secret lives

| Secret | Where it lives | Status |
|---|---|---|
| Provider keys, desktop | Keychain (shell) | sound |
| Provider keys, browser | Tab storage, or server-side encrypted | sound |
| ChatGPT sign-in | Keychain (shell) | sound |
| Connector credentials | Local database, encrypted | sound |
| Encryption key | Keychain (shell) | sound |
| Local API key | Keychain since 2026-09-12; file fallback | sound (fallback weaker) |
| Local JWT secret | Same | sound (fallback weaker) |
| Session token | Webview on-disk storage | **weaker than it should be** |

Exact names and paths: Reference.

> **Why the last row matters:** an owner-only file or browser store keeps out
> other accounts, not a process running as you, the realistic attacker. The
> keychain checks which app asks.

## A signed release never prompts

macOS ties each keychain item to the code-signing identity of the app that
wrote it. A Developer ID build's identity, bundle identifier plus team, is
stable, so real users are never asked.

A debug build is ad-hoc signed: its identity changes every rebuild, so
yesterday's items belong to a stranger. A production dialog is a bug.

When macOS asks, the key card says what to do:

1. **Choose Try again.** The read retries and the password prompt appears.
2. **Pick Always Allow.** It adds this build to the item for good; plain Allow
   asks every launch.
3. **Or paste the key again.** The write deletes and recreates the unreadable
   item under this identity.

> **Rule:** only the Tauri shell touches the keychain. A second signed binary
> doubles what can drift and the prompt surface; the shell hands each secret
> down the process environment ([lib.rs](../../desktop/src-tauri/src/lib.rs),
> [sidecar.rs](../../desktop/src-tauri/src/sidecar.rs)).

## Three changes orphan every install

Keychain items, the database and the webview store survive updates and
reinstalls while the identity holds. Three changes break every install
permanently, with no migration and no actionable error:

1. **Changing the bundle identifier** in the Tauri config: the identity is
   built from it.
2. **Changing the Apple Team ID** the release is signed under, as a
   company-account move does.
3. **Renaming a keychain service constant.** The old items stay, under a name
   nothing looks up.

[check-shell-contract.py](../../.github/scripts/check-shell-contract.py) pins
these four strings across three languages, plus the data-directory name. A
deliberate change edits the pin and ships a migration for the old name.

## Build flavours share everything

Release, dev and self-host builds have different bundle identifiers but share
the release's keychain services and data directory: the service names are
hardcoded. So a dev build reads the release database and fights it for
differently signed keychain items.

Deriving both from the identifier at runtime would spare real users any
migration; it waits because getting it wrong orphans every saved key.

## Multi-user Macs are isolated

Every layer is per-user: the login keychain, unlocked by that account's
password; the owner-only data directory with the database, uploads and any
fallback file; the app's WebKit store. Windows and Linux stores are per-user
too.

Nothing goes to `/Library`, `/usr/local` or a predictable temporary path. Keep
it that way: on a shared Mac that is a real disclosure.

## The session token is the last weak secret

The local API key gates the loopback API; the local JWT secret signs session
tokens, so its holder can mint one for any user. Until 2026-09-12 both were
owner-only files, the weakest link. Now:

1. **The shell mints both** on first run and keeps them in its keychain
   service.
2. **The sidecar reads them from its environment** and deletes the old file:
   the whole migration.
3. **Without a shell or keychain it falls back to the file:** a headless run
   still boots, weaker.

The session token is the one left: webview on-disk storage, readable by
anything that reads that store or runs a script in the app's origin. It
belongs in the keychain.

It touches sign-in, the 30-day "keep me signed in" path, every authenticated
fetch and what "sign out" means across a reinstall: a product decision,
undesigned beyond this, for
[prioritize](../../.agents/skills/prioritize/SKILL.md).

## A refused read is not an absence

This doc exists because a stored ChatGPT sign-in read back as "not signed in":
a refusal collapsed into an absence. Three behaviours keep that legible
(code: Reference):

- **A refused read carries its reason.** The key card says "Can't read your
  key", not "No key set"; the sign-in card offers Sign in again.
- **Keychain errors name the cause on macOS:** access is per signature;
  saving again fixes it.
- **A write repairs an unwritable item** by deleting and retrying, in shell and
  page, reaching installed shells.

## Checklist before touching a secret

1. **Writes outside the data directory or the login keychain?** Stop.
2. **A second binary reads the keychain?** Stop.
3. **Renames a service, account, identifier or data directory?** Migration
   plus pin update.
4. **Could the failure path say "absent" for "refused"?** Return the error.
5. **Logged, in the handshake or a crash report?** Only the handshake carries
   the local API key, by design.

> **Remember:** the keychain protects a secret from other apps; a file only
> from other accounts. The session token is still on the wrong side. Threat
> model: Reference.

## Reference

### Keychain items and their fallbacks

| Secret | Service | Account | Minted by | Pin |
|---|---|---|---|---|
| Provider keys | `ai.getduct.desktop.provider-keys` | provider id | `set_provider_key` in `desktop/src-tauri/src/lib.rs`, called from `app/src/lib/providerKeys.js` | `check-shell-contract.py` |
| ChatGPT bundle | `ai.getduct.desktop.chatgpt` | `session` | `store()` in `desktop/src-tauri/src/chatgpt.rs` | same |
| Encryption key (Fernet) | `ai.getduct.desktop.sidecar` | `credentials-encryption-key` | `credentials_encryption_key()` in `lib.rs` | same |
| Local API key | same | `local-api-key` | `local_api_key()` in `lib.rs`; fallback file `local-api-key` | same (service) |
| Local JWT secret | same | `local-jwt-secret` | `local_jwt_secret()` in `lib.rs`; fallback file `local-jwt-secret` | same (service) |
| Browser provider keys | `sessionStorage`, or `connector_credentials` rows Fernet-encrypted by `backend/service/provider_keys.py` | | `app/src/lib/providerKeys.js`; `PUT /providers/{provider_id}/key` | none |
| Session token | webview `localStorage` | `duct_auth_token__desktop` | `app/src/lib/authFetch.js` | none |

### Data directory, by platform

| Platform | Path | Mode | Defined in |
|---|---|---|---|
| macOS | `~/Library/Application Support/ai.getduct.desktop` | `0700` | `APP_IDENTIFIER` in `backend/utils/appdirs.py`, pinned by `check-shell-contract.py` |
| Windows | `%APPDATA%\Duct` | default | same file |
| Linux | `$XDG_DATA_HOME/duct` | `0700` | same file |

### Build flavours

| Build | Identifier | Keychain services | Data directory |
|---|---|---|---|
| Release | `ai.getduct.desktop` (`tauri.conf.json`) | `ai.getduct.desktop.*` | `…/ai.getduct.desktop` |
| Dev | `ai.getduct.desktop.dev` (`tauri.dev.conf.json`) | the same | the same |
| Self-host | `example.getduct.selfhost` (`tauri.selfhost.conf.json`) | the same | the same |

### What the shell hands the sidecar

| Variable | Read from | Sidecar behaviour (`backend/local_server.py`) |
|---|---|---|
| `DUCT_LOCAL_API_KEY` | keychain | Prefers it and deletes the `local-api-key` file; else mints `secrets.token_urlsafe(32)` into a `0600` file |
| `DUCT_LOCAL_JWT_SECRET` | keychain | Same, for `local-jwt-secret` |
| `CREDENTIALS_ENCRYPTION_KEY` | keychain, unless an env file is pinned or the variable is already set | Fernet key for `backend/service/credentials.py` |
| stdout handshake | sidecar | Carries `api_key` by design; nothing else joins it |

### When macOS prompts

| Situation | Prompt? |
|---|---|
| The app writes an item for the first time | No |
| The same app, matching designated requirement, reads its own item | No |
| The app is updated, or reinstalled from a fresh download, with the same identifier and team | No |
| The machine rebooted and the user logged in normally | No: the login keychain unlocks with the login password |
| A different app, or the same app with a changed signature, reads the item | Yes: "Duct wants to access key …", asking for the login password |
| The login keychain is locked (password changed without updating it, or set to lock on sleep) | Yes, once, to unlock |
| The user clicked Deny earlier | Refused, with no prompt |
| Duct warns about the dialog up front | Never: a signed release does not show it; the key card explains it only after a refused read |

### Where a failure gets named

| Behaviour | Code |
|---|---|
| Refused sign-in read returns `{ connected: false, error }`; card says the sign-in is saved but this build cannot read it | `chatgptStatus()` in `app/src/lib/chatgpt.js`; `app/src/components/connections/ProviderCard.jsx` |
| Refused key read returns `{ key: "", error }`; keys read are held for the page's lifetime, so plain Allow asks once per launch, not per message | `readProviderKey()` and `getProviderKey()` in `app/src/lib/providerKeys.js` |
| Card copy "Can't read your key"; on a Mac, Try again then Always Allow, or paste the key again | `ProviderCard.jsx` |
| macOS keyring error names the signature cause | `describe_keyring_error()` in `desktop/src-tauri/src/lib.rs` |
| Delete-and-retry on a refused write | `store()` in `chatgpt.rs`; `setProviderKey()` in `providerKeys.js` |
| Failed decrypt treated as absent; the user reconnects | `_stored_credentials()` in `backend/service/connector_access.py`; `backend/service/provider_keys.py` |
| ChatGPT sign-in token refused at rest on Duct's server | `PUT /providers/{provider_id}/key` in `backend/routes/providers.py` |
| Refuses to install over a running copy: the on-disk signature changes under the live process | `desktop/scripts/install-dev-app.mjs` |

### Keychain mechanics, verified in the crate

| Fact | Where |
|---|---|
| `keyring` 3.6.3 with the `apple-native` feature | `desktop/src-tauri/Cargo.toml`, `Cargo.lock` |
| Legacy file-keychain API: `SecKeychain::set_generic_password` and `find_generic_password`, not `SecItem*` | `keyring-3.6.3/src/macos.rs` |
| `SecPreferencesDomain::User`, which is `~/Library/Keychains/login.keychain-db`: one per account, unlocked by its login password | same |
| Legacy items carry an access list matched by designated requirement; for a Developer ID build that is the bundle identifier plus the team OU | Apple's documented behaviour for this API |
| A debug build's designated requirement is a hash of the binary | same |

### Threat model

| | |
|---|---|
| **Defended** | Another macOS account reading Duct's credentials. A same-user process reading provider keys, the ChatGPT refresh token or connector tokens: all keychain-gated. Someone with the disk but not the login password: the login keychain is encrypted with it. Duct's servers learning a desktop user's provider keys: they never leave the machine, and the server refuses to remember a ChatGPT sign-in token. |
| **Not defended** | A headless sidecar's local API key and JWT secret, which fall back to files any same-user process can read. Malware holding the user's login password. A user who clicks Allow on a keychain prompt raised by something that is not Duct. |
| **Deliberately survivable** | Losing the encryption key makes stored connector credentials undecryptable. Both readers treat a failed decrypt as absent and degrade to reconnecting, so a wiped keychain costs a reconnection, never a corrupt state. |

### History

| Date | Change |
|---|---|
| 2026-09-12 | Doc written after the ChatGPT sign-in false negative; sign-in reports a refused read; local API key and JWT secret moved to the keychain |
| 2026-09-27 | Provider key cards report a refused read; delete-and-retry on writes |
| 2026-10-25 | Rewritten for scanning; inventory corrected for the two moved secrets |
