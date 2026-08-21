# Open-source readiness — going public as Duct Local

**Status:** plan, not yet executed · **Target:** September 2026
**Decision context:** [`the-10x-question.html`](../strategy/the-10x-question.html) §05, §06, §10.3

> §10.3 is explicit that open-sourcing is a one-way door and should not be walked
> through until Operator is proven. Nothing here changes that. This is the
> preparation, so that when the decision is made the execution is mechanical.

---

## 1 · Shape of the split

**One public repo.** `duct` goes public as-is, minus a small set of private
documents. Duct Cloud is not a separate codebase — it is this codebase deployed
by us, which is what the sidecar work established ("the same FastAPI app runs
either on Railway or as a loopback process"). Splitting a Cloud repo out later
would undo that.

The genuinely proprietary Cloud/Operator pieces do not exist yet: billing,
cross-tenant outcome aggregation, operator grading by measured lift. Those go in
a private service when they are built, which is also where §03 locates the moat.
Publishing `membership.py` costs nothing — nobody out-competes us by reading
project-member CRUD.

**Private companion repo (`duct-docs`)** holds six paths:

| Path | Why |
|---|---|
| `docs/strategy/` | Pricing thesis, margins, kill criteria, and a third party's live ad-account data |
| `docs/gtm/` | Real CAC targets, ad budgets, tier economics |
| `docs/mvp/` | Roadmap and internal scope |
| `docs/engineering/deployment-cloudflare-railway.md` | No secret values, but a map of the deploy topology and exact secret names |
| `docs/engineering/agent-engine-consolidation-review.md` | §1–6 is publishable engine analysis; §7–8 is the commercial channel decision |
| `docs/engineering/desktop-testflight-release.md` | Release runbook for the legacy App Store channel |
| *this file* | Enumerates what is withheld and why |

Everything else ships, including `.claude/`, `.cursor/`, `site/`,
`security-audit-skill-and-hooks.md`, and the attributed `docs/guides/`. That is
most of `docs/` — the architecture writing is the part that makes an
open-source repo credible to the technical buyer §06 wants to reach.

## 2 · History is already clean

Verified across all 434 revisions (August 2026):

- No live secrets — no `sk-ant-`, `sk-proj-`, `GOCSPX-`, `AIza`, `apify_api_`, `pb_live_`
- No Postgres URLs, no `rlwy.net`, no `railway.internal`
- Only `.env.example` files were ever committed, never a real `.env`
- No personal emails in tracked files

This is the one property that could not have been fixed later. A leaked key in
history means rewriting history under time pressure and rotating everything.

## 3 · Execution — two `git filter-repo` runs

Same tool, same path list, opposite directions, on two throwaway clones. Both
were rehearsed in August 2026 and produced the results below.

```bash
PATHS="--path docs/strategy --path docs/gtm --path docs/mvp \
  --path docs/engineering/deployment-cloudflare-railway.md \
  --path docs/engineering/agent-engine-consolidation-review.md \
  --path docs/engineering/desktop-testflight-release.md \
  --path docs/engineering/open-source-readiness.md"

# Clone A → duct-docs (private). Keep only those paths; history preserved.
git clone --no-local . cloneA && cd cloneA && git filter-repo --force $PATHS

# Clone B → duct (public). Remove them, and strip the session trailers.
git clone --no-local . cloneB && cd cloneB && git filter-repo --force --invert-paths $PATHS \
  --message-callback '
lines = [l for l in message.split(b"\n") if not l.strip().startswith(b"Claude-Session:")]
return b"\n".join(lines).rstrip() + b"\n"
'
```

Rehearsal results: clone A came out at 13 files / 29 commits with history intact.
Clone B at 421 commits (from 428 — seven pure-docs commits became empty and were
dropped, which is why both `Gads` commit *messages* disappeared without needing
to be scrubbed). Verified zero traces of the client doc, the `$792` figure, the
`2,800 paid sessions` figure, the Gads commit subjects, and the 25 session
trailers.

Only PR #41 and existing clones break, since every SHA changes.

## 4 · Blockers — the actual work

Neither is on the roadmap and both gate publishing.

**Local identity.** Duct Local is specified as "no account required", but the
backend is built around users, projects and JWTs. `jwt_secret` is empty in a
frozen bundle and `service/auth.py` correctly fails *closed*, so every
authenticated route 401s. Four import sites are where this has to be resolved:
`models/__init__.py:16`, `routes/user_projects.py:15,18`, `routes/namespace.py:9,70`.

**Credential encryption.** `credentials_encryption_key` defaults to `""` and
local mode never fills it, so `encrypt_credentials` raises 500 the moment anyone
links Google Ads, GA4 or GSC. Connectors are listed as a Duct Local feature and
currently cannot store one. The key should be per-install, and for a desktop app
its home is the OS keychain the shell already uses — not a file beside the
SQLite database.

## 5 · Pre-publish checklist

- [ ] Both blockers in §4 resolved; the export builds and its tests pass standalone
- [ ] **TruffleHog sweep over full history.** Its live-credential verification
      pings the provider to check whether a token is still active, which is what
      separates "expired key from 2025" from "active key". Slower than a pattern
      scan, which is why it is a one-time gate rather than a hook:
      `trufflehog git file://. --only-verified`
- [ ] **GitHub push protection enabled** (Settings → Code security). Server-side
      and unskippable — the only gate a contributor cannot bypass locally, and
      the most valuable single control once the repo is public
- [ ] Secret scanning + Dependabot alerts enabled
- [ ] Branch protection on `main`, with the security audit as a required check
- [ ] `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md` (with a disclosure address),
      `CODE_OF_CONDUCT.md` — none currently exist
- [ ] Public `README.md` — the private one describes a monorepo, including areas
      that will not ship
- [ ] Strip ~24 references to the now-private docs (mechanical; nearly every
      citation already states its reason inline, so the path can just be dropped).
      Includes 8 Python files, `backend/CLAUDE.md`, `desktop/CLAUDE.md`,
      `desktop/README.md`, `AGENTS.md`, `app/README.md`, `backend/README.md`,
      `Entitlements.developerid.plist`, and two workflows
- [ ] Resolve the three high-severity npm advisories: `brace-expansion`,
      `fast-uri`, `form-data`
- [ ] Decide whether `desktop-testflight.yml` and its App Store config ship at
      all, given the sidecar cannot run under the sandbox

## 6 · After publishing — the model inverts

Today nothing can leak because nothing is published. Once the repo is public,
every push is public the instant it lands: an allowlist becomes a denylist, and
a mistake is permanent.

Controls already in place:

- `.betterleaks.toml` + `scripts/security/leak_scan.py`, run as a pre-commit hook
  (`git config core.hooksPath .githooks`) and in CI over every tracked file
- Custom rules for the three things no vendor ruleset knows: the managed
  database's proxy hostname, `Claude-Session:` trailers, and a *populated*
  credential in `.cursor/mcp.json`, which ships as a blank template
- `security-audit.yml` blocking, running Opengrep, betterleaks, pip-audit,
  bandit, checkov, osv-scanner and trivy

Worth knowing: `.cursor/mcp.json` publishes seven secret-shaped empty fields.
They are exactly the fields a contributor fills in locally and commits without
thinking, which is the case the pre-commit hook exists for.

## 7 · Open decisions

- **The Gads doc.** Stays private either way. Anonymising it — dropping the
  client identity and turning `~$792/mo` into a range — only pays if access to
  `duct-docs` widens beyond the founders, e.g. to the §07 contractor bench. The
  figures have real internal value, so this is a judgement call, not a default.
- **Splitting the engine review** so §1–6 can ship. It is the strongest public
  engineering writing available, but the code cites it across §2–§9.6, so a
  split rescues only some of the references.
- **`site/`** goes public, meaning positioning changes are visible commit by
  commit. Low stakes since the rendered site is already public.
