#!/usr/bin/env python3
"""Load app/.env.test and run OpenNext build + wrangler deploy (injects NEXT_PUBLIC_* at build time).

Prerequisites: npm deps in app/, wrangler login (or CLOUDFLARE_API_TOKEN), R2 bucket per wrangler.jsonc.

See: docs/engineering/deployment-cloudflare-railway.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from envfile import parse_dotenv_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build OpenNext with app/.env.test and wrangler deploy")
    parser.add_argument(
        "--file",
        type=Path,
        default=ROOT / "app" / ".env.test",
        help="Path to env file (default: app/.env.test)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print env keys and commands only",
    )
    args = parser.parse_args()

    path = args.file.resolve()
    if not path.is_file():
        print(f"error: missing {path}", file=sys.stderr)
        return 1

    extra = parse_dotenv_file(path)
    env = {**os.environ, **{k: v for k, v in extra.items() if v.strip()}}

    app_dir = ROOT / "app"
    cmds: list[tuple[list[str], str]] = [
        (["npm", "ci"], "npm ci"),
        (["npx", "opennextjs-cloudflare", "build"], "opennextjs-cloudflare build"),
        (["npx", "wrangler", "deploy"], "wrangler deploy"),
    ]

    if args.dry_run:
        print(f"[dry-run] cwd={app_dir}")
        print(f"[dry-run] extra keys from {path}: {sorted(extra.keys())}")
        for _, label in cmds:
            print(f"[dry-run] {label}")
        return 0

    for argv, label in cmds:
        print(f"--- {label}")
        subprocess.run(argv, cwd=app_dir, env=env, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
