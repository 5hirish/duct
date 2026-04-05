"""Parse .env-style files (KEY=value). Used by deploy helper scripts only."""

from __future__ import annotations

from pathlib import Path


def parse_dotenv_file(path: Path) -> dict[str, str]:
    """Load KEY=value pairs. Skips blank lines and # comments. Strips optional quotes."""
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def merge_dotenv_files(paths: list[Path]) -> dict[str, str]:
    """Later files override earlier keys."""
    merged: dict[str, str] = {}
    for p in paths:
        merged.update(parse_dotenv_file(p))
    return merged
