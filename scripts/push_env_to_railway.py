#!/usr/bin/env python3
"""Push backend/.env.test (or --file) to Railway service variables via Railway CLI.

Uses `railway variable set KEY --stdin` per key, with --skip-deploys to avoid N redeploys,
then optional `railway redeploy -y`.

Prerequisites: railway login, railway link (from backend/ or use RAILWAY_* env).

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

from envfile import parse_dotenv_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Push backend env file to Railway")
    parser.add_argument(
        "--file",
        type=Path,
        default=ROOT / "backend" / ".env.test",
        help="Path to .env file (default: backend/.env.test)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print keys only",
    )
    parser.add_argument(
        "--no-redeploy",
        action="store_true",
        help="After setting variables, do not run railway redeploy",
    )
    args = parser.parse_args()

    path = args.file.resolve()
    if not path.is_file():
        print(f"error: missing {path}", file=sys.stderr)
        return 1

    data = parse_dotenv_file(path)
    if not data:
        print(f"error: no entries in {path}", file=sys.stderr)
        return 1

    backend_dir = ROOT / "backend"
    for key, value in sorted(data.items()):
        if not value.strip():
            print(f"skip empty: {key}", file=sys.stderr)
            continue
        if args.dry_run:
            print(f"[dry-run] railway variable set {key} --stdin --skip-deploys")
            continue
        subprocess.run(
            [
                "railway",
                "variable",
                "set",
                key,
                "--stdin",
                "--skip-deploys",
            ],
            input=value.encode("utf-8"),
            cwd=backend_dir,
            check=True,
        )
        print(f"set {key}")

    if not args.dry_run and not args.no_redeploy:
        subprocess.run(
            ["railway", "redeploy", "-y"],
            cwd=backend_dir,
            check=True,
        )
        print("railway redeploy triggered")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
