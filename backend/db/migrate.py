"""Schema management for the desktop sidecar — Alembic, not `create_all`.

The deployment runs `alembic upgrade head` as a deploy step, so `create_all` was
only ever the desktop shortcut. That shortcut is wrong for anything but a first
run: `create_all` issues `CREATE TABLE ... IF NOT EXISTS` and nothing else, so a
migration that adds a *column* to an existing table (see
`b8f3d1e6a274_memory_pause_flags`, which adds `projects.memory_paused`) is
silently skipped on every install that already has the table. The user's next
query then fails with `no such column`.

So the sidecar runs the same migrations as the server. The DB is whatever
`DATABASE_URL` points at — SQLite by default on a laptop, but a self-hoster
pointing at Postgres gets the identical path.

Three states, distinguished by what is already in the file:

* **Fresh** (no tables) — `create_all` builds the current schema in one shot,
  then we `stamp head`. Replaying 30-odd migrations to reach the same place
  would be slower and would exercise the handful of legacy revisions that use
  `drop_constraint` / `create_foreign_key`, which SQLite cannot do.
* **Legacy** (tables, but no `alembic_version`) — an install created by the old
  `create_all` path. Its schema matches whatever shipped, so we stamp it at
  `LEGACY_BASELINE_REVISION` and upgrade forward from there.
* **Managed** (`alembic_version` present) — just `upgrade head`.

Never called for the Railway deployment: `ensure_schema` is a no-op unless
`duct_local` is set. Prod's migrations stay a deliberate deploy step.

**Only migrations after the baseline ever run on SQLite.** Fourteen of the
earlier revisions declare `postgresql.JSONB` directly (rather than through the
`sa.JSON().with_variant(...)` form that `models/columns.py` standardised), so
replaying history from `base` on SQLite fails at the first one. It never has to:
a fresh install is built by `create_all` and stamped, and a legacy install is
stamped at the baseline. Those revisions are history and are left alone.

The rule that follows, for anyone adding a migration: **every new revision must
be SQLite-safe.** Use `sa.JSON().with_variant(postgresql.JSONB(...), 'postgresql')`
for JSON columns, keep `alter_column` inside `op.batch_alter_table`, and assume
it will run on a laptop as well as on Railway. `tests/test_desktop_migrations.py`
exercises exactly that path.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

log = logging.getLogger(__name__)

# The Alembic revision whose schema matches the last desktop build that shipped
# with `create_all` owning the schema (head of `main` at the Aug 2026 DMG).
# An install from that build has every table but no `alembic_version`, so it is
# stamped here and migrated forward rather than being rebuilt.
#
# This constant is historical — it pins a released artifact, so it must NOT be
# advanced when new migrations land. It can only be retired once no install from
# that build can still be upgraded.
LEGACY_BASELINE_REVISION = "b6d2f8a4c1e7"

# Present in every schema since long before the baseline, so its existence is a
# reliable "this database has been used" signal.
_SENTINEL_TABLE = "users"


def _alembic_root() -> Path:
    """Directory holding `alembic.ini` and the `alembic/` script tree.

    Under PyInstaller both ship as bundle data (`duct_sidecar.spec` adds them),
    which unpacks to `sys._MEIPASS`. From source they sit next to this package.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def alembic_config(database_url: str) -> Config:
    """Alembic config pointed at an explicit URL and the bundled script tree.

    The URL is passed in rather than read from `alembic.ini` because a frozen
    build has no `.env` to resolve it from, and `env.py` would otherwise
    re-derive it through `get_configs()` — fine, but this keeps the caller in
    charge of which database is being migrated.
    """
    root = _alembic_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def ensure_schema() -> None:
    """Bring the local database to `head`. No-op outside desktop/local mode."""
    from config import get_configs  # local import: avoids a cycle at module load

    cfg = get_configs()
    if not cfg.duct_local:
        return

    from db.session import get_engine

    engine = get_engine()
    if engine is None:
        return

    tables = set(inspect(engine).get_table_names())
    config = alembic_config(str(engine.url.render_as_string(hide_password=False)))

    if "alembic_version" in tables:
        log.info("migrating local database to head")
        command.upgrade(config, "head")
        return

    if _SENTINEL_TABLE in tables:
        # Pre-Alembic desktop install: adopt it at the released baseline, then
        # let the normal upgrade path add everything since.
        log.info(
            "adopting pre-Alembic local database at %s, then migrating",
            LEGACY_BASELINE_REVISION,
        )
        command.stamp(config, LEGACY_BASELINE_REVISION)
        command.upgrade(config, "head")
        return

    # Fresh install: build the current schema directly and record it as current.
    log.info("creating local database schema")
    import models  # noqa: F401 — registers every table on SQLModel.metadata
    from db.session import init_db

    init_db()
    command.stamp(config, "head")
