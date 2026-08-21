#!/usr/bin/env python3
"""Refuse to commit things that must never become public.

Once `duct` is a public repo there is no staging area between a push and the
internet, so the check has to happen before the commit rather than before a
release. This runs as a pre-commit hook on staged content and in CI over every
tracked file.

    python3 scripts/security/leak_scan.py            # staged files (the hook)
    python3 scripts/security/leak_scan.py --all      # every tracked file (CI)
    python3 scripts/security/leak_scan.py FILE...    # explicit paths

Install the hook once per clone:

    git config core.hooksPath .githooks

Patterns are deliberately narrow. A scanner that fires on `api_key = ""` gets
bypassed within a week, and a bypassed scanner is worse than none — so this
matches credential *shapes* and known-private hostnames, not variable names.
A full-history scan of all 434 revisions in Aug 2026 found no live credentials;
the job here is to keep that true.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PATTERNS: list[tuple[str, str]] = [
    # Live credential shapes.
    (r"sk-ant-(api|oat)[0-9]{2}-[A-Za-z0-9_-]{20}", "Anthropic API key or OAuth token"),
    (r"sk-proj-[A-Za-z0-9_-]{20}", "OpenAI project key"),
    (r"GOCSPX-[A-Za-z0-9_-]{15}", "Google OAuth client secret"),
    (r"AIza[A-Za-z0-9_-]{30}", "Google API key"),
    (r"apify_api_[A-Za-z0-9]{20}", "Apify token"),
    (r"pb_live_[A-Za-z0-9]{15}", "PostBridge live key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"\bghp_[A-Za-z0-9]{36}\b", "GitHub personal access token"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    # A populated Bearer/token field in an MCP config. These files ship as
    # templates with empty values; a filled one is a credential.
    (r"\"Authorization\"\s*:\s*\"Bearer\s+\S+\"", "populated Authorization header"),
    (r"\"(SENTRY_AUTH_TOKEN|CLOUDFLARE_API_TOKEN)\"\s*:\s*\"\S+\"", "populated MCP credential"),
    # Connection strings with an inline password.
    (r"postgres(ql)?://[^\s:'\"]+:[^\s@'\"]+@", "Postgres URL with credentials"),
    # Hosts that only exist in the private deployment.
    (r"\brlwy\.net\b", "Railway proxy hostname"),
    (r"\brailway\.internal\b", "Railway internal hostname"),
    # Private links that leak session history.
    (r"claude\.ai/code/session_", "private Claude session URL"),
]

# Placeholders that legitimately look like the real thing.
ALLOW = re.compile(
    r"user:pw@|user:pass|USER:PASS|<[^>]*>|\bEXAMPLE\b|xxx+|\.\.\.|"
    r"your[-_]?(key|token|secret)|placeholder|changeme|REDACTED",
    re.I,
)

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".webp", ".svg",
                 ".pdf", ".docx", ".zip", ".woff", ".woff2", ".ttf", ".lock"}
# Lockfiles carry base64 hashes that trip entropy-shaped patterns.
SKIP_NAMES = {"poetry.lock", "package-lock.json", "Cargo.lock",
              ".security-audit-baseline.json"}


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    ).stdout
    return [f for f in out.splitlines() if f]


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         cwd=REPO_ROOT).stdout
    return [f for f in out.splitlines() if f]


def scan(paths: list[str]) -> list[tuple[str, int, str, str]]:
    compiled = [(re.compile(p), why) for p, why in PATTERNS]
    findings = []
    for rel in paths:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES or path.name in SKIP_NAMES:
            continue
        # This file is a list of credential patterns; it would match itself.
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if ALLOW.search(line):
                continue
            for rx, why in compiled:
                if rx.search(line):
                    findings.append((rel, n, why, line.strip()[:110]))
                    break
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="Scan every tracked file.")
    ap.add_argument("paths", nargs="*", help="Explicit paths to scan.")
    args = ap.parse_args()

    paths = args.paths or (tracked_files() if args.all else staged_files())
    if not paths:
        return 0

    findings = scan(paths)
    if not findings:
        return 0

    print(f"\nLeak scan: {len(findings)} finding(s) — commit refused\n", file=sys.stderr)
    for rel, n, why, excerpt in findings:
        print(f"  {rel}:{n}  [{why}]", file=sys.stderr)
        print(f"      {excerpt}", file=sys.stderr)
    print(
        "\nIf this is a false positive, make the placeholder obviously fake "
        "(<your-token>, EXAMPLE) rather than bypassing the hook.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
