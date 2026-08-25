#!/usr/bin/env python3
"""Run betterleaks over staged or tracked files.

Detection lives in betterleaks and `.betterleaks.toml`, not here. This wrapper
only decides *what* to scan and how to behave when the binary is missing:

    python3 scripts/security/leak_scan.py             # staged files (pre-commit)
    python3 scripts/security/leak_scan.py --all       # every tracked file (CI)
    python3 scripts/security/leak_scan.py --require   # fail if betterleaks absent

Scanning tracked files rather than the working tree is deliberate: a directory
walk also reads `.env*`, which legitimately contains live credentials and is
gitignored. Those must never be a commit failure, and they are exactly what the
scanner would shout about.

Locally a missing binary warns and passes, so a contributor without it is not
blocked; CI passes --require so the gate cannot silently disappear. Install:

    brew install betterleaks     # or: go install github.com/betterleaks/betterleaks@latest
    git config core.hooksPath .githooks
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = REPO_ROOT / ".betterleaks.toml"

INSTALL_HINT = (
    "betterleaks is not installed — secret scanning was skipped.\n"
    "  brew install betterleaks\n"
    "  go install github.com/betterleaks/betterleaks@latest\n"
    "CI still enforces this, so a leak will be caught there instead."
)


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True,
                         cwd=REPO_ROOT).stdout
    return [line for line in out.splitlines() if line]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="Scan every tracked file.")
    ap.add_argument("--require", action="store_true",
                    help="Fail if betterleaks is not installed (use in CI).")
    args = ap.parse_args()

    binary = shutil.which("betterleaks") or shutil.which("gitleaks")
    if not binary:
        if args.require:
            print("betterleaks/gitleaks not installed and --require was set.",
                  file=sys.stderr)
            return 1
        print(INSTALL_HINT, file=sys.stderr)
        return 0

    if args.all:
        paths = git("ls-files")
    else:
        paths = git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    # Deleted or renamed-away paths still appear in some git output.
    paths = [p for p in paths if (REPO_ROOT / p).is_file()]
    if not paths:
        return 0

    proc = subprocess.run(
        [binary, "dir", "--no-banner", "--redact",
         "--config", str(CONFIG), "--exit-code", "1", *paths],
        cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        print(
            "\nSecret scan failed. If this is a false positive, prefer making the\n"
            "placeholder obviously fake (<your-token>, EXAMPLE) or adding a filter\n"
            "to .betterleaks.toml over bypassing the hook.\n",
            file=sys.stderr,
        )
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
