# Local Security Audit Skill

This setup provides a local-first security gate for `backend/` and `app/` focused on:

- secrets leakage
- database compromise paths
- user-data and privacy exposure
- dependency vulnerabilities

Policy:

- Block on `Critical`
- Warn on `High` and `Medium`

## Files

- Skill source: `.claude/skills/security-audit.md`
- Cursor skill entrypoint: `.cursor/skills/security-audit/SKILL.md`
- Audit runner: `scripts/security/audit.py`
- Baseline file: `.security-audit-baseline.json`
- CI advisory parity workflow: `.github/workflows/security-audit.yml`

## Open Source Tooling Prerequisites

Required for full coverage:

- `gitleaks`
- `semgrep`
- `pip-audit`
- `npm` (for `npm audit` in `app/`)

Optional:

- `trivy`
- `bandit` (Python-focused security lint)
- `osv-scanner` (cross-ecosystem vuln scan)
- `checkov` (IaC misconfiguration scan when Terraform manifests are added)

Install examples (macOS with Homebrew + pip):

```bash
brew install gitleaks semgrep trivy osv-scanner
python3 -m pip install pip-audit bandit checkov
```

Ensure executable scripts are set:

```bash
chmod +x scripts/security/audit.py
```

## Manual Runs

Changed-scope scan (fast):

```bash
python3 scripts/security/audit.py --mode changed
```

Deep scan across backend + app:

```bash
python3 scripts/security/audit.py --mode deep
```

Write/update a baseline file for known-safe recurring findings:

```bash
python3 scripts/security/audit.py --mode deep --write-baseline
```

## Trigger Behavior

- GitHub Action trigger: PRs targeting `main` only (`.github/workflows/security-audit.yml`)
- Local trigger: manual command execution (`changed` / `deep`)

If a `Critical` finding is detected, the audit command exits non-zero and the CI job reports failure.
If only `High`/`Medium` findings are present, audit exits successfully after warning output.

## PostgreSQL Model-Specific Checks

The audit runner includes backend-focused checks for SQLModel/SQLAlchemy patterns:

- Sensitive DB fields (`password`, `secret`, `token`, `api_key`, etc.) stored as plain `String` columns
- f-string raw SQL construction via `text()`/`execute()`
- Engine creation hardening signal in `backend/db/session.py` (warn if no explicit `sslmode` signal)
- Alembic migration lint for RLS signals (`ENABLE ROW LEVEL SECURITY` / `CREATE POLICY`) when sensitive tables are created
- Migration privilege-drift checks (`GRANT ... TO PUBLIC`, `ALTER ROLE ... SUPERUSER`)
- Sensitive model field nullability checks for credential-like fields

These checks are heuristic by design and complement Semgrep/Gitleaks, not replace deeper review.

## Do We Need a Custom Script?

Short answer: yes, but keep it thin.

- Open-source tools (`gitleaks`, `semgrep`, `pip-audit`, `npm audit`, optional `trivy`) provide best-of-breed scanning.
- The custom script adds project-specific policy and severity gating (`Critical` blocks, `High/Medium` warn).
- GitHub Actions enforcement provides consistent checks on PRs.

Without the script, you lose consistent policy orchestration and local context-specific checks.

## Baseline and Signal Tuning

- Findings include stable fingerprints in output.
- Add approved recurring findings to `.security-audit-baseline.json` to suppress known-safe alerts.
- Keep baseline small and review it in PRs like code.
- Re-generate only when policy/rules materially change.

## Verification Procedure

1. Run `python3 scripts/security/audit.py --mode changed` on a normal code state.
2. Add a temporary synthetic secret to a local test file (do not commit it), then re-run and confirm critical block behavior.
3. Remove temporary synthetic data and re-run to confirm pass.

For a faster local loop, use the skill command:

- `/security-audit`
- `/security-audit deep`
