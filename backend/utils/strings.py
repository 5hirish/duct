"""Generic string helpers.

Leaf module: standard library only.
"""

from __future__ import annotations

import re

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60, sep: str = "-") -> str:
    """Kebab-case slug from arbitrary text ('' if nothing survives).

    ``sep`` covers the underscore-keyed variants (content pillar / format ids).
    """
    slug = _NON_SLUG.sub(sep, (text or "").lower()).strip(sep)
    return slug[:max_len].rstrip(sep)


def titleize(value: str) -> str:
    """Human label from a slug or snake_case key: ``face_shape`` -> ``Face Shape``."""
    return re.sub(r"\b\w", lambda m: m.group().upper(), re.sub(r"[_-]+", " ", value or "")).strip()

