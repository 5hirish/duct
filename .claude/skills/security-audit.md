---
name: security-audit
description: Run deep local security audits for backend and app changes to catch secrets exposure, DB compromise vectors, and user privacy risks before PRs.
argument-hint: "[changed|deep]"
disable-model-invocation: true
---

# Local Security Audit Skill + Hooks

Performs a local-first security audit focused on `backend/` and `app/` to reduce the chance of database compromise, secret leakage, and user-data/privacy regressions.

## Usage

- `/security-audit` -> run default `changed` audit (fast, scoped to diffs)
- `/security-audit changed` -> run changed-files-focused audit
- `/security-audit deep` -> run full deep audit over `backend/` and `app/`

## Security Policy

- **Block** on `Critical`
- **Warn** on `High` and `Medium`

## Scanner Stack (Open Source)

- `gitleaks` for secrets
- `semgrep` for code-level security patterns
- `pip-audit` for Python dependency vulnerabilities
- `npm audit` for Node dependency vulnerabilities
- Optional: `trivy` for config/IaC/container checks when relevant files exist
- Built-in fallback checks in `scripts/security/audit.py` keep core detection active even if tools are missing

## Phase 1: Confirm Scope

1. Ensure branch is clean enough to audit:
   - `git status`
2. Select mode:
   - If no argument, use `changed`
   - If argument is `deep`, run full scan
3. Resolve scan targets:
   - `changed`: staged/modified files under `backend/` and `app/`
   - `deep`: all files under `backend/` and `app/`

## Phase 2: Run Security Scans

Run through the local runner:

```bash
python3 scripts/security/audit.py --mode changed
python3 scripts/security/audit.py --mode deep
```

The runner executes:

1. Baseline static pattern checks (always-on, local fallback)
2. PostgreSQL model-focused checks for backend SQLModel/SQLAlchemy usage
3. PostgreSQL migration hardening checks (RLS/privilege-drift heuristics)
4. Secrets scanning (`gitleaks`)
5. SAST checks (`semgrep`, optional `bandit`)
6. Dependency risk checks (`pip-audit`, `npm audit`, optional `osv-scanner`)
7. Optional checks (`trivy`, `checkov`) if installed and target files exist

## Phase 3: Triage by Severity

Classify findings into:

- `Critical` (must block)
  - hardcoded secrets
  - obvious SQL injection or unsanitized query construction
  - missing authz in sensitive server paths
  - direct user-data exfiltration risk
- `High` (warn and fix quickly)
  - weak session/cookie/token handling
  - broad PII logging
  - serious dependency CVEs
- `Medium` (warn and track)
  - missing hardening headers/policies
  - weak privacy hygiene in non-critical flows

## Phase 4: Remediation Guidance

For each finding, include:

1. File path and rule/tool source
2. Why it is risky
3. Quick fix recommendation
4. Follow-up test suggestion

## Phase 5: Decision Rubric

1. If any `Critical` findings exist:
   - Fail local audit and stop before PR update
2. If only `High`/`Medium` exist:
   - Continue with warning summary and create follow-up tasks
3. If no findings:
   - Mark audit as passed

## Baseline Workflow (Noise Control)

- Use `.security-audit-baseline.json` to suppress reviewed recurring findings by fingerprint.
- Create/update baseline intentionally:

```bash
python3 scripts/security/audit.py --mode deep --write-baseline
```

## Domain Mapping (What this audit protects)

- **Secrets/credentials leakage** -> OWASP ASVS V8/V9, CWE-798
- **DB compromise vectors** (injection/authz gaps) -> OWASP A01/A03, CWE-89/CWE-285
- **User-data/privacy exposure** -> OWASP A02/A09, CWE-532
- **Supply-chain dependency risk** -> OWASP A06, CWE-1104

## CI Trigger Guidance

Use GitHub Actions for PR-time enforcement and keep local runs manual:

1. CI PR gate on `.github/workflows/security-audit.yml` for PRs targeting `main`
2. Manual local run before opening/updating PR:
   - `python3 scripts/security/audit.py --mode deep`

## Completion Checklist

- [ ] `scripts/security/audit.py --mode changed` executed
- [ ] `scripts/security/audit.py --mode deep` executed (before PR updates)
- [ ] No `Critical` findings remain
- [ ] High/Medium findings reviewed and tracked
