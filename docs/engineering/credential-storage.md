# Credential storage: the local API key and provider auth

**Reference.** Where every secret Duct holds actually lives, what protects it,
and what breaks it. Written 2026-09-12 after a debugging session in which a
ChatGPT sign-in stored correctly and then read back as "not signed in" — the
credential was fine; the report was wrong, and nothing in the tree explained
the mechanism well enough to tell those apart.

Read this before changing anything that stores a secret, and before changing
the app's bundle identifier, its signing identity, or a keychain service name.
Those last three are load-bearing in a way that compiling cannot check.

---

## 1. The inventory

Duct holds seven kinds of secret. They do not all deserve the same treatment,
and today they do not all get it.

| Secret | Where it lives | What protects it | Status |
|---|---|---|---|
| Provider API keys, desktop | OS keychain, service `ai.getduct.desktop.provider-keys`, account = provider id | keychain ACL, per-user login keychain | sound |
| Provider API keys, browser | `sessionStorage`, or the server encrypted with Fernet | tab lifetime, or `CREDENTIALS_ENCRYPTION_KEY` | sound |
| ChatGPT plan OAuth bundle | OS keychain, service `ai.getduct.desktop.chatgpt`, account `session` | keychain ACL | sound |
| Connector credentials (Google Ads refresh tokens, …) | SQLite, Fernet-encrypted | key held in the keychain, below | sound |
| Credentials encryption key (Fernet) | OS keychain, service `ai.getduct.desktop.sidecar`, account `credentials-encryption-key` | keychain ACL | sound |
| **Local API key** | file `local-api-key` in the data dir, `0600` | filesystem only | **weaker than it should be** |
| **Local JWT secret** | file `local-jwt-secret` in the data dir, `0600` | filesystem only | **weaker than it should be** |
| Session token (the signed-in user) | `localStorage`, key `duct_auth_token__desktop` | WebKit store, per user | **weaker than it should be** |

The data directory is `~/Library/Application Support/ai.getduct.desktop`,
created `0700` by `backend/utils/appdirs.py`. Windows uses `%APPDATA%\Duct`,
Linux `$XDG_DATA_HOME/duct`.

**Why the last three are called out.** `0600` protects a file from *other macOS
accounts*. It does not protect it from any other process running as the same
user — which is the realistic attacker for a desktop app. The keychain does,
because macOS gates each item on the identity of the app asking. The local JWT
secret is the sharpest of the three: whoever reads it can mint a valid session
token for any user id and drive the whole local API. Section 6 specifies the
move.

---

## 2. How the keychain is actually used

`keyring` 3.6.3 with the `apple-native` feature. Two facts matter and both were
read out of the crate rather than assumed
(`keyring-3.6.3/src/macos.rs`):

- It calls the **legacy file-keychain API** — `SecKeychain::set_generic_password`
  and `find_generic_password`, not the modern `SecItem*` data-protection
  keychain.
- It asks for `SecPreferencesDomain::User`, which resolves to
  `~/Library/Keychains/login.keychain-db`.

Both consequences are load-bearing.

**Legacy items carry an ACL.** When an app creates a generic password this way,
macOS records the creating app in the item's access-control list, matched later
by the app's code-signing **designated requirement**. This is why access
survives an update, and why it does not survive a change of identity. (The ACL
mechanism is Apple's documented behaviour for this API; what was verified here
is which API the crate calls.)

**The User domain is per-account.** Every macOS user has their own login
keychain, unlocked by their own login password. One logged-in user cannot read
another's items. Section 5 covers the rest of the multi-user story.

Service names are hardcoded constants, not derived from the bundle identifier,
so **all three build flavours share them** — `ai.getduct.desktop` (release),
`ai.getduct.desktop.dev`, `example.getduct.selfhost`. See §7.

---

## 3. When macOS prompts, and when it does not

The short version: **a correctly signed release build never prompts.** If a user
sees a keychain dialog, something in this list is true, and it is a bug worth
chasing rather than normal behaviour.

| Situation | Prompt? |
|---|---|
| App writes an item for the first time | No |
| Same app, matching designated requirement, reads its own item | No |
| App updated to a new version, same identifier and team | No |
| App reinstalled from a fresh download, same identifier and team | No |
| Machine rebooted, user logged in normally | No — the login keychain unlocks with the login password |
| **A different app, or the same app with a changed signature, reads the item** | **Yes** — "Duct wants to access key … in your keychain", asking for the login password |
| The login keychain is locked (user changed their login password without updating it, or set it to lock on sleep) | Yes, once, to unlock |
| The user previously clicked Deny | Denied without a prompt |

Row six is the one that bit this repo. A **debug build is ad-hoc signed**, so its
designated requirement is a hash of the binary itself and changes with every
build. Rebuild the app and yesterday's items belong, as far as macOS is
concerned, to a different application. A **Developer ID build** is signed with a
requirement built from the bundle identifier and the team OU, both stable
across versions, which is exactly why real users are not asked again.

This is also why "Always Allow" exists on that dialog: it adds the asking app to
the item's ACL permanently. We should never rely on a user finding it.

**Design rule that follows.** Only one signed binary should ever touch the
keychain: the Tauri shell. The sidecar is a separate executable with its own
identity, so having it read the keychain doubles the number of identities that
can drift and doubles the prompt surface. The established pattern is the shell
reading the keychain and passing the value down the process environment —
`credentials_encryption_key()` in `desktop/src-tauri/src/lib.rs`, handed over in
`sidecar.rs`. Anything moved into the keychain must follow it.

---

## 4. What survives an update, and the three things that do not

Stable across app updates, self-updates and reinstalls, as long as the identity
holds: every keychain item, the data directory and its SQLite database, and the
WebKit store holding `localStorage`.

Three changes break every installed copy at once, permanently, with no
migration path and no error a user can act on:

1. **Changing `identifier` in `tauri.conf.json`.** The designated requirement is
   built from it.
2. **Changing the Apple Team ID the release is signed under.** Same reason. A
   move from a personal to a company account does this.
3. **Renaming a keychain service constant.** The old items are still there,
   under a name nothing looks up.

These are four string literals across three languages, held together by nothing
but the fact that someone wrote them the same way. They are now pinned in
`.github/scripts/check-shell-contract.py`, which fails the build if any drifts.
Changing one deliberately means editing the pin **and** shipping a migration
that reads the old name and rewrites it under the new one.

The data directory name is the same bargain for the local database:
`APP_IDENTIFIER` in `backend/utils/appdirs.py` is pinned alongside them.

---

## 5. Multi-user machines

Isolated at every layer, by construction rather than by policy:

- **Keychain** — the per-user login keychain, unlocked by that account's
  password. Another logged-in account cannot read it.
- **Data directory** — `~/Library/Application Support/<identifier>`, created
  `0700`, so the SQLite database, uploads and the two secret files are
  owner-only.
- **Webview storage** — the app's per-user WebKit store.
- **Windows and Linux** — Credential Manager and the freedesktop Secret Service
  are per-user in the same way.

Nothing is written to `/Library`, `/usr/local`, or a predictable temporary path.
**Keep it that way.** A credential written anywhere system-wide would be
readable by every account on the machine, and on a shared or family Mac that is
a real disclosure, not a theoretical one.

---

## 6. The three that should move (specified, not yet built)

### 6.1 Local API key and local JWT secret

Today `backend/local_server.py` mints both with `secrets.token_urlsafe(32)` and
persists them as `0600` files, then reports the API key in its stdout handshake.

They should be minted and held by the shell instead:

- Extend the `ai.getduct.desktop.sidecar` service with accounts `local-api-key`
  and `local-jwt-secret`, minted on first run exactly as
  `credentials_encryption_key()` already is.
- `sidecar.rs` passes both down as environment variables when spawning, beside
  `CREDENTIALS_ENCRYPTION_KEY`. The sidecar prefers the environment and falls
  back to its file, so a shell without a keychain still boots.
- On a successful read from the environment, the sidecar deletes the file. That
  is the migration: existing installs move on their next launch, and nothing has
  to detect a version.

No new prompt surface, because the shell is the only identity involved. The
sidecar keeps working headless (`--data-dir` with no shell) via the file path.

### 6.2 The session token

`duct_auth_token__desktop` lives in `localStorage`, which is readable by
anything that can read the WebKit store on disk and by any script running in the
app's origin. On desktop it should live in the keychain and reach the page
through an invoke, the way provider keys already do.

This one is a larger change — it touches the sign-in flow, the 30-day "keep me
signed in" path and every `authFetch` caller — and it is a product decision as
much as a security one, because it changes what "sign out" means across a
reinstall. It has not been designed further than this paragraph. It needs its
own pass through `prioritize`.

---

## 7. Known wart: the build flavours share everything

All three flavours use the same hardcoded keychain services **and** the same
data directory, while having different bundle identifiers:

| Build | Identifier | Keychain services | Data dir |
|---|---|---|---|
| Release | `ai.getduct.desktop` | `ai.getduct.desktop.*` | `…/ai.getduct.desktop` |
| Dev | `ai.getduct.desktop.dev` | the same | the same |
| Self-host | `example.getduct.selfhost` | the same | the same |

So a dev build reads the release build's database and API key, and the two
compete for keychain items they are differently signed for — which is the ACL
collision in §3, reproduced on purpose every time someone runs both.

The fix is to derive both from the bundle identifier at runtime, which leaves
the release values byte-identical (`ai.getduct.desktop.*`, so **no migration for
real users**) and moves only dev and self-host. It is not done, because it
touches credential paths and the failure mode of getting it subtly wrong is
orphaning every user's saved keys.

---

## 8. Threat model, stated plainly

What this design does and does not defend against.

**Defended.** Another macOS account on the same machine reading Duct's
credentials. A process running as the user reading provider keys, the ChatGPT
refresh token, or connector refresh tokens — all keychain-gated. Someone with
the disk but not the login password: the login keychain is encrypted with it.
Duct's servers learning a desktop user's provider keys: they never leave the
machine, and `PUT /providers/openai/key` refuses to store a plan credential at
all.

**Not defended.** A process running as the user reading the local API key or the
JWT secret, until §6.1 lands, and from there driving the loopback API. Malware
with the user's login password. A user who clicks "Allow" on a keychain prompt
raised by something that is not Duct.

**Deliberately survivable.** Losing the Fernet key makes stored connector
credentials undecryptable; `connector_access` and `service/provider_keys.py`
both treat a failed decrypt as absent and degrade to reconnecting, so a wiped
keychain costs reconnection, never a corrupt state.

---

## 9. What happens when it does break

Three behaviours, all added 2026-09-12, exist so that a credential failure is
legible instead of looking like a feature bug:

- **A failed read is never reported as a negative answer.** `chatgptStatus()` in
  `app/src/lib/chatgpt.js` returns `{ connected: false, error }` rather than a
  bare `connected: false`. The card renders "your sign-in is saved but this build
  cannot read it", with the reason, and the button becomes "Sign in again". The
  old code collapsed "the keychain refused" into "you never signed in", which is
  what made this take a session to find.
- **macOS keyring errors name the cause.** `describe_keyring_error()` in
  `desktop/src-tauri/src/lib.rs` explains that access is granted per signature
  and that saving again fixes it, instead of returning a bare OSStatus.
- **A write repairs an unwritable item.** An item this build cannot read often
  cannot be overwritten either, which would break the sign-in that repairs the
  situation. `store()` in `chatgpt.rs` deletes and retries.

And for the developer-facing half: `desktop/scripts/install-dev-app.mjs` refuses
to install over a running copy, because swapping the bundle underneath a live
process changes its on-disk signature and detaches it from its own keychain
items mid-session.

---

## 10. Checklist for a change that touches a secret

- Does it write outside `~/Library/Application Support/<identifier>` or the
  login keychain? If yes, stop — see §5.
- Does a second binary now read the keychain? If yes, stop — see §3.
- Does it rename a service, an account, the identifier, or the data directory?
  Then it needs a migration and a pin update in `check-shell-contract.py`.
- Can the failure path report "absent" when it means "refused"? That is the
  §9 bug; return the error.
- Is the secret logged, echoed into a handshake, or included in a crash report?
  The handshake already carries the local API key by design; nothing else should
  join it.
