# Security Policy

## Reporting a vulnerability

**Do not open a public issue.** Report privately, one of two ways:

- **GitHub private vulnerability reporting** — the "Report a vulnerability"
  button under this repository's Security tab. Preferred: it keeps the report,
  the fix and the advisory in one place.
- **Email** — <hello@getduct.ai>, subject line starting `SECURITY:`.

Please include what you can: affected component (`backend/`, `app/`,
`desktop/`, `site/`), version or commit, reproduction steps, and what an
attacker gains. A proof of concept helps; a working exploit is not required.

We aim to acknowledge within 3 working days and to describe a fix or a
timeline within 10. Duct is maintained by one person — if you have not heard
back in a week, please chase, because it means the mail went astray rather
than that the report was dismissed.

Please give us a reasonable window to ship a fix before publishing. We will
credit you in the advisory unless you prefer otherwise.

## Scope

In scope: this repository — the FastAPI backend, the Next.js app, the Tauri
desktop shell, and the static site.

Particularly interesting to us:

- **Cross-tenant access.** Project data is scoped by membership, not by
  `projects.user_id`. `DUCT_API_KEY` ships to the browser as
  `NEXT_PUBLIC_DUCT_API_KEY` and is explicitly *not* an authorization boundary
  — it proves "this is the Duct app", never "this caller owns that row". Any
  route that reads or writes a project-scoped row without a membership check on
  top of `get_current_user` is a bug we want to hear about.
- **Connector credential handling.** OAuth refresh tokens are Fernet-encrypted
  at rest (`backend/service/credentials.py`). Anything that leaks plaintext, or
  that lets one project decrypt another's, is high severity.
- **Agent tool surfaces.** Prompt injection that reaches a write-capable tool.
  Note that approve and apply are deliberately absent from the agent tool
  surface in both harnesses — `backend/service/execution/policy.py` decides what
  may be applied and does not consult the model. A path around that is a finding.
- **The desktop sidecar.** It binds `127.0.0.1` on an OS-assigned port behind a
  generated local API key. Anything that lets another local process or a web
  page drive it counts.

Out of scope: findings against `getduct.ai` marketing pages with no security
impact, missing headers with no demonstrated exploit, automated scanner output
without a reproduction, denial of service by volume, and social engineering.

## What we already run

Every pull request runs a blocking security audit
(`.github/workflows/security-audit.yml`): betterleaks over every tracked file,
plus Opengrep, pip-audit, bandit, checkov, osv-scanner and trivy via
`scripts/security/audit.py`. Contributors can run the same secret scan locally
as a pre-commit hook — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Handling secrets in this repository

This repository is public and its history is public with it. Never commit a
real credential, not even briefly: a force-push does not unpublish it, and the
only correct response is rotation. `.env` files of every shape are gitignored;
`backend/.env.example` is the documented surface and carries no values.
