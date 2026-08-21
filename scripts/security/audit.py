#!/usr/bin/env python3
"""Local security audit runner for backend/ and app/."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
APP_DIR = REPO_ROOT / "app"
DEFAULT_BASELINE_FILE = REPO_ROOT / ".security-audit-baseline.json"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"


@dataclass
class Finding:
    severity: str
    title: str
    detail: str


def run_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd or REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def git_changed_files() -> list[str]:
    results = []
    for args in (["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"]):
        proc = run_command(args)
        if proc.returncode == 0 and proc.stdout.strip():
            results.extend(line.strip() for line in proc.stdout.splitlines() if line.strip())
    untracked = run_command(["git", "ls-files", "--others", "--exclude-standard"])
    if untracked.returncode == 0 and untracked.stdout.strip():
        results.extend(line.strip() for line in untracked.stdout.splitlines() if line.strip())
    # Keep order stable while deduplicating.
    seen: set[str] = set()
    unique: list[str] = []
    for path in results:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def in_scope(path: str) -> bool:
    return path.startswith("backend/") or path.startswith("app/")


def collect_targets(mode: str) -> list[str]:
    if mode == "deep":
        return ["backend", "app"]
    return [path for path in git_changed_files() if in_scope(path)]


def iter_source_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    allowed_suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".sql", ".env", ".yml", ".yaml", ".json"}
    ignored_dir_names = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".next",
        ".open-next",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
    }
    for target in targets:
        path = REPO_ROOT / target
        if path.is_file():
            if path.suffix in allowed_suffixes:
                files.append(path)
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob("*"):
            if not candidate.is_file():
                continue
            if any(part in ignored_dir_names for part in candidate.parts):
                continue
            if candidate.suffix in allowed_suffixes:
                files.append(candidate)
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local security audit checks.")
    parser.add_argument(
        "--mode",
        choices=("changed", "deep"),
        default="changed",
        help="changed scans only modified files; deep scans full backend/app trees.",
    )
    parser.add_argument(
        "--baseline-file",
        default=str(DEFAULT_BASELINE_FILE),
        help="Path to baseline file for suppressing known-safe findings.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write current findings to baseline file and exit successfully.",
    )
    return parser.parse_args()


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def gitleaks_scan(targets: list[str]) -> list[Finding]:
    """Deliberately a no-op — secret scanning lives in scripts/security/leak_scan.py.

    This used to shell out to gitleaks over the target *directories*, which meant
    it also read gitignored files: `.env.local`, `.env.prod`, `.venv/`, build
    output and the VS Code `.history/` cache. Those hold real credentials by
    design, so the scan reported 163 CRITICAL findings for files that can never
    be committed — the kind of result that gets a gate switched off.

    leak_scan.py scans *tracked* files only, with Duct's own betterleaks config.
    A committed `.env` is therefore still caught, while an ignored one is not,
    which is the behaviour that was wanted here all along. It runs as its own CI
    step and as the pre-commit hook.
    """
    return []


def semgrep_scan(targets: list[str]) -> list[Finding]:
    if not command_exists("semgrep"):
        return [Finding(SEVERITY_MEDIUM, "semgrep missing", "Install semgrep to enable SAST checks.")]
    cmd = ["semgrep", "--config", "auto", "--json"]
    cmd.extend(targets)
    proc = run_command(cmd)
    findings: list[Finding] = []
    if proc.returncode not in (0, 1):
        findings.append(Finding(SEVERITY_MEDIUM, "semgrep execution issue", proc.stderr.strip() or proc.stdout.strip()))
        return findings
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [Finding(SEVERITY_MEDIUM, "semgrep parse issue", "Could not parse semgrep JSON output.")]
    for result in payload.get("results", []):
        sev_raw = (result.get("extra", {}).get("severity") or "").lower()
        severity = SEVERITY_HIGH if sev_raw in {"error", "warning"} else SEVERITY_MEDIUM
        if "sql" in (result.get("check_id", "").lower() + result.get("extra", {}).get("message", "").lower()):
            severity = SEVERITY_CRITICAL
        findings.append(
            Finding(
                severity,
                f"Semgrep: {result.get('check_id', 'rule')}",
                f"{result.get('path', 'unknown-file')}:{result.get('start', {}).get('line', '?')} {result.get('extra', {}).get('message', '').strip()}",
            )
        )
    return findings


def pip_audit_scan() -> list[Finding]:
    if not command_exists("pip-audit") or not (BACKEND_DIR / "pyproject.toml").exists():
        return []
    proc = run_command(["pip-audit", "-f", "json"], cwd=BACKEND_DIR)
    findings: list[Finding] = []
    if proc.returncode not in (0, 1):
        findings.append(Finding(SEVERITY_MEDIUM, "pip-audit execution issue", proc.stderr.strip() or proc.stdout.strip()))
        return findings
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return [Finding(SEVERITY_MEDIUM, "pip-audit parse issue", "Could not parse pip-audit JSON output.")]
    for pkg in data.get("dependencies", []) if isinstance(data, dict) else data:
        vulns = pkg.get("vulns", [])
        for vuln in vulns:
            findings.append(
                Finding(
                    SEVERITY_HIGH,
                    f"Python dependency vulnerability: {pkg.get('name', 'unknown')}",
                    vuln.get("id", "unknown-vuln"),
                )
            )
    return findings


def npm_audit_scan() -> list[Finding]:
    if not (APP_DIR / "package.json").exists():
        return []
    proc = run_command(["npm", "audit", "--json"], cwd=APP_DIR)
    findings: list[Finding] = []
    if proc.returncode not in (0, 1):
        findings.append(Finding(SEVERITY_MEDIUM, "npm audit execution issue", proc.stderr.strip() or proc.stdout.strip()))
        return findings
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [Finding(SEVERITY_MEDIUM, "npm audit parse issue", "Could not parse npm audit JSON output.")]
    vulnerabilities = data.get("vulnerabilities", {})
    for name, entry in vulnerabilities.items():
        sev = str(entry.get("severity", "moderate")).lower()
        severity = SEVERITY_HIGH if sev in {"critical", "high"} else SEVERITY_MEDIUM
        findings.append(
            Finding(
                severity,
                f"Node dependency vulnerability: {name}",
                f"Severity reported by npm audit: {sev}",
            )
        )
    return findings


def trivy_scan(targets: list[str]) -> list[Finding]:
    if not command_exists("trivy"):
        return []
    findings: list[Finding] = []
    for target in targets:
        path = REPO_ROOT / target
        if not path.exists():
            continue
        proc = run_command(["trivy", "fs", "--severity", "CRITICAL,HIGH", "--quiet", str(path)])
        if proc.returncode != 0 and proc.stdout.strip():
            findings.append(Finding(SEVERITY_HIGH, f"Trivy findings in {target}", "Run `trivy fs` for detailed output."))
    return findings


def bandit_scan() -> list[Finding]:
    if not command_exists("bandit") or not BACKEND_DIR.exists():
        return []
    proc = run_command(["bandit", "-r", "backend", "-f", "json"])
    findings: list[Finding] = []
    if proc.returncode not in (0, 1):
        findings.append(Finding(SEVERITY_MEDIUM, "bandit execution issue", proc.stderr.strip() or proc.stdout.strip()))
        return findings
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [Finding(SEVERITY_MEDIUM, "bandit parse issue", "Could not parse bandit JSON output.")]
    for issue in payload.get("results", []):
        sev = str(issue.get("issue_severity", "")).upper()
        mapped = SEVERITY_HIGH if sev == "HIGH" else SEVERITY_MEDIUM
        findings.append(
            Finding(
                mapped,
                f"Bandit: {issue.get('test_name', 'issue')}",
                f"{issue.get('filename', 'backend')}:{issue.get('line_number', '?')} {issue.get('issue_text', '').strip()}",
            )
        )
    return findings


def checkov_scan() -> list[Finding]:
    if not command_exists("checkov"):
        return []
    infra_targets = [
        REPO_ROOT / "terraform",
        REPO_ROOT / "infrastructure",
        REPO_ROOT / "infra",
    ]
    target = next((path for path in infra_targets if path.exists() and path.is_dir()), None)
    if target is None:
        return []
    proc = run_command(["checkov", "-d", str(target), "--output", "json"])
    findings: list[Finding] = []
    if proc.returncode not in (0, 1):
        findings.append(Finding(SEVERITY_MEDIUM, "checkov execution issue", proc.stderr.strip() or proc.stdout.strip()))
        return findings
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [Finding(SEVERITY_MEDIUM, "checkov parse issue", "Could not parse checkov JSON output.")]
    for entry in payload.get("results", {}).get("failed_checks", []):
        findings.append(
            Finding(
                SEVERITY_HIGH,
                f"Checkov: {entry.get('check_id', 'policy')}",
                f"{entry.get('file_path', 'infra')} {entry.get('check_name', '').strip()}",
            )
        )
    return findings


def osv_scan() -> list[Finding]:
    if not command_exists("osv-scanner"):
        return []
    proc = run_command(["osv-scanner", "scan", "source", ".", "--format", "json"])
    findings: list[Finding] = []
    if proc.returncode not in (0, 1):
        findings.append(Finding(SEVERITY_MEDIUM, "osv-scanner execution issue", proc.stderr.strip() or proc.stdout.strip()))
        return findings
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [Finding(SEVERITY_MEDIUM, "osv-scanner parse issue", "Could not parse osv-scanner JSON output.")]
    for result in payload.get("results", []):
        for pkg in result.get("packages", []):
            for vuln in pkg.get("vulnerabilities", []):
                findings.append(
                    Finding(
                        SEVERITY_HIGH,
                        f"OSV vulnerability: {pkg.get('package', {}).get('name', 'dependency')}",
                        vuln.get("id", "unknown-vuln"),
                    )
                )
    return findings


def static_pattern_scan(targets: list[str]) -> list[Finding]:
    """Fallback checks to keep core protections active without external scanners."""
    findings: list[Finding] = []
    secret_pattern = re.compile(
        r"(api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"'\n]{8,}[\"']",
        re.IGNORECASE,
    )
    sql_pattern = re.compile(
        # \b anchors the verb as a whole word — without it "set_context(" matches
        # via its "...text(", "draw(" matches "raw(", etc. (false positives). Real
        # execute()/text()/raw() calls still match (preceded by ., space, or line start).
        r"\b(execute|raw|text)\s*\(\s*(f[\"'].*\{.+\}.*[\"']|[\"'].*(SELECT|INSERT|UPDATE|DELETE).*[\"']\s*\+)",
        re.IGNORECASE,
    )
    pii_log_pattern = re.compile(r"(log|print)\s*\(.*(email|phone|ssn|token|password)", re.IGNORECASE)

    for file_path in iter_source_files(targets):
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if secret_pattern.search(content):
            rel_path = str(file_path.relative_to(REPO_ROOT))
            severity = SEVERITY_HIGH if "/tests/" in rel_path or rel_path.startswith("backend/tests/") else SEVERITY_CRITICAL
            findings.append(
                Finding(
                    severity,
                    "Potential hardcoded secret",
                    rel_path,
                )
            )
        if sql_pattern.search(content):
            findings.append(
                Finding(
                    SEVERITY_CRITICAL,
                    "Potential SQL injection construction",
                    str(file_path.relative_to(REPO_ROOT)),
                )
            )
        if pii_log_pattern.search(content):
            findings.append(
                Finding(
                    SEVERITY_HIGH,
                    "Potential PII logging exposure",
                    str(file_path.relative_to(REPO_ROOT)),
                )
            )
    return findings


def postgres_model_scan(targets: list[str]) -> list[Finding]:
    """PostgreSQL model-specific checks for SQLModel/SQLAlchemy usage."""
    findings: list[Finding] = []
    sensitive_field_pattern = re.compile(
        r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*.*=\s*Field\(",
        re.MULTILINE,
    )
    risky_field_names = {"password", "secret", "token", "api_key", "access_token", "refresh_token"}
    string_column_pattern = re.compile(r"sa_column\s*=\s*Column\(\s*String", re.IGNORECASE)
    raw_sql_pattern = re.compile(r"\b(text|execute)\s*\(\s*f[\"']", re.IGNORECASE)
    weak_engine_pattern = re.compile(r"create_engine\(([^)]*)\)", re.IGNORECASE | re.DOTALL)

    postgres_paths = [target for target in targets if target.startswith("backend/") or target == "backend"]
    for file_path in iter_source_files(postgres_paths):
        rel = str(file_path.relative_to(REPO_ROOT))
        if not rel.startswith("backend/"):
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if "/models/" in rel or rel.startswith("backend/models/"):
            for match in sensitive_field_pattern.finditer(content):
                field_name = match.group(1).lower()
                if field_name not in risky_field_names:
                    continue
                # Flag likely plaintext secret storage in model definitions.
                chunk_start = max(match.start() - 200, 0)
                chunk_end = min(match.end() + 300, len(content))
                chunk = content[chunk_start:chunk_end]
                if string_column_pattern.search(chunk) and "hash" not in chunk.lower() and "encrypt" not in chunk.lower():
                    findings.append(
                        Finding(
                            SEVERITY_HIGH,
                            "Potential plaintext sensitive DB field",
                            f"{rel} field `{field_name}` appears to store sensitive values as plain String.",
                        )
                    )
                if "nullable=True" in chunk:
                    findings.append(
                        Finding(
                            SEVERITY_HIGH,
                            "Sensitive DB field is nullable",
                            f"{rel} field `{field_name}` is nullable and may weaken credential handling guarantees.",
                        )
                    )

        if raw_sql_pattern.search(content):
            findings.append(
                Finding(
                    SEVERITY_CRITICAL,
                    "Potential f-string raw SQL in backend",
                    f"{rel} appears to use f-string SQL via text()/execute().",
                )
            )

        if rel == "backend/db/session.py":
            engine_match = weak_engine_pattern.search(content)
            if engine_match and "sslmode" not in engine_match.group(1).lower():
                findings.append(
                    Finding(
                        SEVERITY_MEDIUM,
                        "Engine creation does not explicitly enforce sslmode",
                        "backend/db/session.py create_engine() call has no explicit sslmode signal.",
                    )
                )

    return findings


def postgres_migration_scan(targets: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    migration_dir = REPO_ROOT / "backend" / "alembic" / "versions"
    if not migration_dir.exists():
        return findings
    if not any(target == "backend" or target.startswith("backend/") for target in targets):
        return findings

    sensitive_markers = ("email", "token", "secret", "password", "profile", "identity", "users")
    for migration in migration_dir.glob("*.py"):
        try:
            content = migration.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lower = content.lower()
        created_sensitive_table = "create_table(" in lower and any(marker in lower for marker in sensitive_markers)
        has_rls = "enable row level security" in lower or "create policy" in lower
        if created_sensitive_table and not has_rls:
            findings.append(
                Finding(
                    SEVERITY_MEDIUM,
                    "Migration creates sensitive table without explicit RLS policy",
                    f"backend/alembic/versions/{migration.name}",
                )
            )
        if re.search(r"grant\s+.+\s+to\s+public", lower):
            findings.append(
                Finding(
                    SEVERITY_CRITICAL,
                    "Migration grants privileges to PUBLIC",
                    f"backend/alembic/versions/{migration.name}",
                )
            )
        if "superuser" in lower and "alter role" in lower:
            findings.append(
                Finding(
                    SEVERITY_CRITICAL,
                    "Migration modifies SUPERUSER role privileges",
                    f"backend/alembic/versions/{migration.name}",
                )
            )
    return findings


def finding_fingerprint(finding: Finding) -> str:
    payload = f"{finding.severity}|{finding.title}|{finding.detail}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if not isinstance(payload, dict):
        return set()
    fingerprints = payload.get("fingerprints", [])
    if not isinstance(fingerprints, list):
        return set()
    return {str(item) for item in fingerprints}


def write_baseline(path: Path, findings: list[Finding]) -> None:
    payload = {
        "version": 1,
        "fingerprints": sorted({finding_fingerprint(item) for item in findings}),
        "generated_by": "scripts/security/audit.py",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def apply_baseline(findings: list[Finding], baseline: set[str]) -> list[Finding]:
    if not baseline:
        return findings
    return [item for item in findings if finding_fingerprint(item) not in baseline]


def print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("Security audit passed: no findings.")
        return
    grouped: dict[str, list[Finding]] = {
        SEVERITY_CRITICAL: [],
        SEVERITY_HIGH: [],
        SEVERITY_MEDIUM: [],
    }
    for item in findings:
        grouped.setdefault(item.severity, []).append(item)
    for severity in (SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM):
        items = grouped.get(severity, [])
        if not items:
            continue
        print(f"\n[{severity.upper()}] {len(items)} finding(s)")
        for finding in items:
            print(f"- {finding.title}")
            print(f"  {finding.detail} [{finding_fingerprint(finding)}]")


def main() -> int:
    args = parse_args()
    targets = collect_targets(args.mode)
    if not targets:
        print("No backend/app targets found for this mode. Skipping security audit.")
        return 0

    print(f"Running security audit in {args.mode} mode...")
    print("Targets:", ", ".join(targets))

    findings: list[Finding] = []
    findings.extend(static_pattern_scan(targets))
    findings.extend(postgres_model_scan(targets))
    findings.extend(postgres_migration_scan(targets))
    findings.extend(gitleaks_scan(targets))
    findings.extend(semgrep_scan(targets))
    findings.extend(pip_audit_scan())
    findings.extend(npm_audit_scan())
    findings.extend(trivy_scan(targets))
    findings.extend(bandit_scan())
    findings.extend(osv_scan())
    findings.extend(checkov_scan())

    baseline_file = Path(args.baseline_file)
    if args.write_baseline:
        write_baseline(baseline_file, findings)
        print(f"Wrote baseline with {len(findings)} finding(s) to {baseline_file}.")
        return 0
    findings = apply_baseline(findings, load_baseline(baseline_file))

    print_findings(findings)

    critical_count = sum(1 for item in findings if item.severity == SEVERITY_CRITICAL)
    if critical_count > 0:
        print(f"\nAudit failed: {critical_count} critical finding(s).")
        return 1

    print("\nAudit completed with no critical findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
