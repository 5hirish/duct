#!/usr/bin/env python
"""Alembic migration manager for the backend service.

Policy:
- Revisions are always created with --autogenerate.
- Generated files must be reviewed by a human before deploy.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def _build_config() -> Config:
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR / ".env.local", override=True)

    cfg = Config(str(ALEMBIC_INI))
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is required. Set it in env or backend/.env.local before running migrations."
        )
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _is_empty_upgrade(script_path: Path) -> bool:
    try:
        text_content = script_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "def upgrade() -> None:\n    pass\n" in text_content


def cmd_revision(cfg: Config, message: str, allow_empty: bool) -> int:
    command.revision(cfg, message=message, autogenerate=True)
    script = ScriptDirectory.from_config(cfg)
    after_heads = script.get_heads()
    if not after_heads:
        print("No migration head found after revision.", file=sys.stderr)
        return 1
    latest = script.get_revision(after_heads[0])
    if latest is None:
        print("Could not resolve latest generated revision.", file=sys.stderr)
        return 1
    generated_path = Path(latest.path)
    if not allow_empty and _is_empty_upgrade(generated_path):
        generated_path.unlink(missing_ok=True)
        print(
            "Aborted: autogenerate produced an empty migration. "
            "No file kept. Use --allow-empty to keep it.",
            file=sys.stderr,
        )
        return 2
    print(f"Generated migration: {generated_path}")
    return 0


def cmd_upgrade(cfg: Config, revision: str) -> int:
    command.upgrade(cfg, revision)
    return 0


def cmd_downgrade(cfg: Config, revision: str) -> int:
    command.downgrade(cfg, revision)
    return 0


def cmd_current(cfg: Config) -> int:
    command.current(cfg)
    return 0


def cmd_stamp(cfg: Config, revision: str) -> int:
    command.stamp(cfg, revision)
    return 0


def cmd_check_pending(cfg: Config) -> int:
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    if not head:
        print("No migration head found in script directory.")
        return 1
    engine = create_engine(cfg.get_main_option("sqlalchemy.url"))
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current = context.get_current_revision()
    if current != head:
        print(f"Pending migrations detected: current={current!r}, head={head!r}")
        return 1
    print(f"Database is at head revision: {head}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backend Alembic migration manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_revision = sub.add_parser("revision", help="Create revision (always autogenerate)")
    p_revision.add_argument("-m", "--message", required=True, help="Migration message")
    p_revision.add_argument(
        "--allow-empty",
        action="store_true",
        help="Keep migration file even if autogenerate found no changes",
    )

    p_upgrade = sub.add_parser("upgrade", help="Upgrade database")
    p_upgrade.add_argument("revision", nargs="?", default="head")

    p_downgrade = sub.add_parser("downgrade", help="Downgrade database")
    p_downgrade.add_argument("revision", nargs="?", default="-1")

    sub.add_parser("current", help="Show current revision")

    p_stamp = sub.add_parser("stamp", help="Stamp revision without running migrations")
    p_stamp.add_argument("revision", nargs="?", default="head")

    sub.add_parser("check-pending", help="Exit non-zero when DB is behind head")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    cfg = _build_config()

    if args.command == "revision":
        return cmd_revision(cfg, args.message, args.allow_empty)
    if args.command == "upgrade":
        return cmd_upgrade(cfg, args.revision)
    if args.command == "downgrade":
        return cmd_downgrade(cfg, args.revision)
    if args.command == "current":
        return cmd_current(cfg)
    if args.command == "stamp":
        return cmd_stamp(cfg, args.revision)
    if args.command == "check-pending":
        return cmd_check_pending(cfg)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

