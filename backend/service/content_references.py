"""Global content reference library — disk-resident enumeration.

Globals are bundled with the backend repo at
`backend/data/content/references/` (NOT the storage bucket) so the
agent picker has zero runtime network cost. See that directory's
README.md for the layout + contribution flow.

Per-project / user-uploaded references stay on the Railway Volume —
this module only enumerates the shipped globals.

Public surface:
  - GlobalReference         dataclass returned by the iterator
  - iter_global_references  generator + axis/subtype filters
  - global_references_dir   path resolver (used by server.py StaticFiles)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — must match the on-disk layout in data/content/references/
# ---------------------------------------------------------------------------

ReferenceAxis = Literal["layouts", "camera", "captions"]

_LAYOUT_SUBTYPES   = ("collage", "full-bleed", "before-after", "editorial", "text-only")
_CAMERA_SUBTYPES   = ("closeup", "selfie-talking", "lifestyle")
_CAPTION_SUBTYPES  = ("bold-sans", "pill-bubble", "serif-italic", "minimal-whisper")

_ALLOWED_SUBTYPES: dict[str, tuple[str, ...]] = {
    "layouts":  _LAYOUT_SUBTYPES,
    "camera":   _CAMERA_SUBTYPES,
    "captions": _CAPTION_SUBTYPES,
}

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

_EXT_TO_MIME = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
}

# Public URL prefix served by FastAPI StaticFiles in server.py.
PUBLIC_URL_PREFIX = "/static/references"

# Disk root — resolved once at import time. Repo-relative to backend/.
_THIS_DIR = Path(__file__).resolve().parent             # backend/service/
_BACKEND_ROOT = _THIS_DIR.parent                         # backend/
_DISK_ROOT = _BACKEND_ROOT / "data" / "content" / "references"


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GlobalReference:
    """One curated reference image shipped with the backend repo."""

    slug:      str    # stable identifier — e.g. "camera/selfie-talking/IMG_5885"
    axis:      str    # "layouts" | "camera" | "captions"
    subtype:   str    # e.g. "selfie-talking", "collage", "pill-bubble"
    filename:  str
    disk_path: Path   # absolute path — used by generate_image to read bytes
    public_url: str   # served by FastAPI StaticFiles


# ---------------------------------------------------------------------------
# Path / URL helpers
# ---------------------------------------------------------------------------


def global_references_dir() -> Path:
    """Absolute path to the disk root. Used by server.py to mount
    StaticFiles. Returns the path even if the dir doesn't exist yet —
    server.py checks existence before mounting."""
    return _DISK_ROOT


def disk_path_for_public_url(url: str) -> Path | None:
    """Resolve a `/static/references/...` URL back to an on-disk path.

    Used by the @tool layer when an asset's URL points at the global
    library. Returns None if the URL isn't under PUBLIC_URL_PREFIX.
    """
    if not url.startswith(f"{PUBLIC_URL_PREFIX}/"):
        return None
    rel = url[len(PUBLIC_URL_PREFIX) + 1:]
    # Defend against path traversal — accept only forward components.
    parts = [p for p in rel.split("/") if p and p not in ("..", ".")]
    return _DISK_ROOT.joinpath(*parts)


# ---------------------------------------------------------------------------
# Iteration
# ---------------------------------------------------------------------------


def iter_global_references(
    *,
    axis:    str | None = None,
    subtype: str | None = None,
) -> Iterator[GlobalReference]:
    """Yield every shipped global reference, filtered by axis/subtype.

    Stable order: axes alphabetical, subtypes in their canonical
    declaration order (matters because the agent picker iterates and
    the first hit per subtype is the default fallback). Filenames are
    sorted alphabetically within a subtype.

    Skips `.gitkeep` / hidden / non-image files silently.
    """
    if axis is not None and axis not in _ALLOWED_SUBTYPES:
        logger.warning("global_references: unknown axis %r requested", axis)
        return

    axes = (axis,) if axis else sorted(_ALLOWED_SUBTYPES.keys())
    for ax in axes:
        subtypes = _ALLOWED_SUBTYPES[ax]
        if subtype is not None:
            if subtype not in subtypes:
                logger.warning(
                    "global_references: unknown subtype %r for axis %r", subtype, ax,
                )
                continue
            subtypes = (subtype,)
        for sub in subtypes:
            dir_path = _DISK_ROOT / ax / sub
            if not dir_path.is_dir():
                continue
            for entry in sorted(dir_path.iterdir(), key=lambda p: p.name):
                if not entry.is_file():
                    continue
                if entry.name.startswith("."):
                    continue
                if entry.suffix.lower() not in _IMAGE_EXTS:
                    continue
                stem = entry.stem
                yield GlobalReference(
                    slug      = f"{ax}/{sub}/{stem}",
                    axis      = ax,
                    subtype   = sub,
                    filename  = entry.name,
                    disk_path = entry.resolve(),
                    public_url= f"{PUBLIC_URL_PREFIX}/{ax}/{sub}/{entry.name}",
                )


# ---------------------------------------------------------------------------
# Content-asset projection (consumed by the fetch_content_assets @tool)
# ---------------------------------------------------------------------------


def global_reference_asset_dicts(
    *,
    axis:    str | None = None,
    subtype: str | None = None,
) -> list[dict]:
    """Shape the shipped global references as content-asset dicts.

    Mirrors the row shape `fetch_content_assets` returns for DB-backed
    assets so the agent treats globals and per-project assets uniformly.
    The crucial field is `id`: for a global it is the `/static/references/...`
    public URL (NOT a DB UUID). The agent passes that id straight back into
    generate_image's `input_asset_ids`; the tool resolves it from disk via
    `disk_path_for_public_url` — no DB row, no bucket round-trip.

    `axis` / `subtype` narrow the pool (e.g. camera/selfie-talking) so the
    picker need not receive the whole library.
    """
    out: list[dict] = []
    for ref in iter_global_references(axis=axis, subtype=subtype):
        out.append({
            "id":         ref.public_url,
            "asset_type": "reference",
            "source":     "global",
            "url":        ref.public_url,
            "mime_type":  _EXT_TO_MIME.get(Path(ref.filename).suffix.lower(), "image/jpeg"),
            "prompt":     None,
            "model":      None,
            "params":     None,
            "created_at": None,
            "axis":       ref.axis,
            "subtype":    ref.subtype,
            "slug":       ref.slug,
        })
    return out
