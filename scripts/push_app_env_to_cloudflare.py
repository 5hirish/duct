#!/usr/bin/env python3
"""Load app env file and run OpenNext build + wrangler deploy (injects NEXT_PUBLIC_* at build time).

Prerequisites: npm deps in app/, wrangler login (or CLOUDFLARE_API_TOKEN), R2 bucket per wrangler.jsonc.
Put **CLOUDFLARE_ACCOUNT_ID** in the same app env file (e.g. `.env.local` / `.env.prod` / `.env.test`) when
your token can access multiple Cloudflare accounts (avoids interactive account selection). Override with
`--cloudflare-account-id` if needed.

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
    parser.add_argument(
        "--cloudflare-account-id",
        default="",
        help="Set CLOUDFLARE_ACCOUNT_ID for Wrangler (skips interactive account selection)",
    )
    args = parser.parse_args()

    path = args.file.resolve()
    if not path.is_file():
        print(f"error: missing {path}", file=sys.stderr)
        return 1

    extra = parse_dotenv_file(path)
    env = {**os.environ, **{k: v for k, v in extra.items() if v.strip()}}

    if args.cloudflare_account_id.strip():
        env["CLOUDFLARE_ACCOUNT_ID"] = args.cloudflare_account_id.strip()

    app_dir = ROOT / "app"
    cmds: list[tuple[list[str], str]] = [
        (["npm", "ci"], "npm ci"),
        (["npx", "opennextjs-cloudflare", "build"], "opennextjs-cloudflare build"),
        (["npx", "wrangler", "deploy"], "wrangler deploy"),
    ]

    if args.dry_run:
        print(f"[dry-run] cwd={app_dir}")
        print(f"[dry-run] extra keys from {path}: {sorted(extra.keys())}")
        if (env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip():
            print("[dry-run] CLOUDFLARE_ACCOUNT_ID is set (Wrangler account picker skipped)")
        for _, label in cmds:
            print(f"[dry-run] {label}")
        return 0

    for argv, label in cmds:
        print(f"--- {label}")
        subprocess.run(argv, cwd=app_dir, env=env, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
