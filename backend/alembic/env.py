from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import get_configs
from db.migrate import LANGGRAPH_TABLES
from models import auth  # noqa: F401
from sqlmodel import SQLModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The Alembic CLI arrives here with no URL configured and resolves one from
# the app config. Programmatic callers (`db/migrate.py`, which the desktop
# sidecar runs at startup) already know which database they are migrating and
# set it on the Config — re-deriving it here would send them at whatever
# DATABASE_URL the developer's .env happens to hold.
database_url = config.get_main_option("sqlalchemy.url") or get_configs().database_url
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://") :]
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = SQLModel.metadata


# Indexes over a SQL *expression* rather than plain columns. SQLAlchemy can see
# that they exist but reflects the expression as an opaque blob, so autogenerate
# has nothing to compare against the model and reports the index as dropped on
# every run. Alembic's own documentation names this as the case for a filter.
# Each one is created by raw DDL in the revision named beside it and is
# Postgres-only, which is also why it cannot be declared in `__table_args__`
# without breaking the SQLite path the desktop sidecar runs on.
EXPRESSION_INDEXES = {
    "ix_project_memories_fts": "a4e1c7d2b953 — GIN over to_tsvector(title || body)",
}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """What `--autogenerate` and `alembic check` are allowed to see.

    LangGraph's checkpointer tables live in this database but are owned and
    migrated by LangGraph, so they are absent from `SQLModel.metadata`. Without
    this filter autogenerate reads that absence as "dropped" and writes an
    `op.drop_table` for each one — a revision that would delete every in-flight
    conversation on the next deploy. See `db.migrate.LANGGRAPH_TABLES`.

    Expression indexes are the second case, for the reason above the constant.
    Both are exclusions from *comparison* only: the objects are still created,
    still used, and still dropped by their own downgrade.
    """
    if type_ == "table" and name in LANGGRAPH_TABLES:
        return False
    if type_ == "index" and name in EXPRESSION_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # SQLite (the desktop sidecar, and self-hosters who choose it) has no
        # real ALTER TABLE: no altering a column, no dropping a constraint.
        # Batch mode makes Alembic emit those as create-copy-drop-rename instead
        # of failing. It is a no-op on Postgres, so it is safe to key on the
        # dialect rather than on an app-level "am I desktop" flag.
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

