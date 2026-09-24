"""docs/engineering/data-model.md lists every table the backend owns.

The page exists so the question "is this already recorded somewhere?" gets
asked against the full list before a new table or log is proposed. A table
missing from it is a table nobody will think to check, which is how a
redundant one gets designed.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlmodel import SQLModel

import models  # noqa: F401  (registers every table on SQLModel.metadata)

DOC = Path(__file__).resolve().parents[2] / "docs" / "engineering" / "data-model.md"


def _documented_tables() -> set[str]:
    return set(re.findall(r"^\| `([a-z_]+)` \|", DOC.read_text(), flags=re.MULTILINE))


def test_every_table_is_on_the_data_model_page():
    missing = sorted(set(SQLModel.metadata.tables) - _documented_tables())
    assert not missing, f"Add these tables to {DOC.name}: {missing}"


def test_the_page_names_no_table_that_is_gone():
    stale = sorted(_documented_tables() - set(SQLModel.metadata.tables))
    assert not stale, f"{DOC.name} lists tables that no longer exist: {stale}"
