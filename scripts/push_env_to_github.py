#!/usr/bin/env python3
"""Push allowlisted keys from gitignored .env.test files to GitHub Actions secrets/variables.

Reads: backend/.env.test, app/.env.test (later file wins on duplicate keys).

Does NOT bulk-upload backend secrets (DUCT_API_KEY, Google, LLM, etc.) — only keys used for
Cloudflare deploy CI. Requires: gh auth login, repo checkout as cwd.

See: docs/engineering/deployment-cloudflare-railway.md
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from envfile import merge_dotenv_files  # noqa: E402

# Match .github/workflows/deploy-cloudflare-app.yml — secrets vs vars.
GITHUB_SECRETS = frozenset(
    {
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "NEXT_PUBLIC_DUCT_API_KEY",  # browser-exposed but treat as sensitive in GH
    }
)


def _is_github_variable(key: str) -> bool:
    if key in GITHUB_SECRETS:
        return False
    return key.startswith("NEXT_PUBLIC_")


def _gh_secret_set(key: str, value: str, *, dry_run: bool, cwd: Path) -> None:
    if dry_run:
        print(f"[dry-run] gh secret set {key} (hidden)")
        return
    subprocess.run(
        ["gh", "secret", "set", key],
        input=value.encode("utf-8"),
        cwd=cwd,
        check=True,
    )
    print(f"set secret {key}")


def _gh_variable_set(key: str, value: str, *, dry_run: bool, cwd: Path) -> None:
    if dry_run:
        print(f"[dry-run] gh variable set {key}={value!r}")
        return
    subprocess.run(
        ["gh", "variable", "set", key, "--body", value],
        cwd=cwd,
        check=True,
    )
    print(f"set variable {key}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync allowlisted env to GitHub Actions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without calling gh",
    )
    args = parser.parse_args()

    paths = [ROOT / "backend" / ".env.test", ROOT / "app" / ".env.test"]
    merged = merge_dotenv_files(paths)
    if not merged:
        print("error: no values found (create backend/.env.test and/or app/.env.test)", file=sys.stderr)
        return 1

    touched_secret = False
    touched_var = False
    for key in sorted(merged.keys()):
        value = merged[key]
        if not value.strip():
            print(f"skip empty: {key}", file=sys.stderr)
            continue
        if key in GITHUB_SECRETS:
            _gh_secret_set(key, value, dry_run=args.dry_run, cwd=ROOT)
            touched_secret = True
        elif _is_github_variable(key):
            _gh_variable_set(key, value, dry_run=args.dry_run, cwd=ROOT)
            touched_var = True

    if not touched_secret and not touched_var:
        print(
            "error: no allowlisted keys found in .env.test files "
            f"(secrets={sorted(GITHUB_SECRETS)}, variables=NEXT_PUBLIC_*)",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
