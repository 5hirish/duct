# Google Tag Manager

- **Workspace edits are invisible to production.** Nothing changes on the live
  site until a container **version is created and published** — and a publish
  changes the site for every visitor, so treat it exactly like a deploy:
  record the outgoing live version id FIRST (that is the rollback target),
  publish, then verify. Rollback = republish the prior version.
- **"Tag fires" ≠ "tag works".** A tag can fire on every page and still fail at
  runtime — e.g. a dataLayer variable feeding a bare string where the vendor
  SDK expects an object, or an undefined variable pasted as the literal text
  "undefined". Verify the network call / vendor debugger, not the fire status.
- **`workspaces:quick_preview` compiles a workspace** and returns compiler
  errors — always run it before creating a version.
- **Renaming a variable via the API does not rewrite references.** Tags point
  at the literal `{{Variable Name}}` string; only the UI rewrites referrers.
  Rename via API only if every referring tag is patched in the same change.
- **User-Provided Data (`awec`) modes:** CODE mode takes a variable returning
  the user-data OBJECT (`{sha256_email_address: "<hex>"}`); MANUAL mode's
  `email` key is the plain-text slot. Pre-hashed data in MANUAL's email key
  silently sends nothing usable.
- GTM validates parameter keys per tag/variable type — a wrong key returns
  INVALID_ARGUMENT naming the right one, which is a cheap way to discover an
  undocumented schema.
- **API quota is tight (~0.25 QPS).** Serialize calls and back off on 429s;
  parallel GTM calls fail in ways that look like flaky infrastructure.
- Custom HTML tags receive `{{var}}` as pasted text — quote every reference
  and normalize "undefined"/"null" strings to empty.
- Vendor pixels usually expect **integer minor units** for money (cents), and
  validate types client-side — a decimal dollar amount is silently dropped, so
  conversion values vanish without an error anywhere.
