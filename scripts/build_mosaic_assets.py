#!/usr/bin/env python3
"""Re-encode the mosaic panel masters into the WebP files the app ships.

Masters live in `app/art-src/mosaic/` at 1024px because a generated panel
cannot be reproduced byte-for-byte — the image models take no seed, so a
regenerated panel is a *different* panel, not the same one re-rendered. The
master is therefore the source of truth and this script is the only thing that
writes `app/public/art/mosaic/`; never hand-edit a file in there. They sit
beside the app rather than under `docs/` because they are a build input, not a
design document: `docs/design/` is flows and copy guidance, and a reader
opening it should not find six JPEGs and no spec.

Panels render at 320px at most (the "Illustration" rules in `app/DESIGN.md`),
so 640px is the 2x asset and no srcset is needed at that size.

    python3 scripts/build_mosaic_assets.py [--check]

--check re-encodes to a temp dir and fails if anything differs from what is
committed, which is what CI would run to catch a hand-edited output.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - dependency hint is the whole point
    sys.exit("Pillow is required: pip install Pillow")

REPO = Path(__file__).resolve().parent.parent
MASTERS = REPO / "app" / "art-src" / "mosaic"
OUTPUT = REPO / "app" / "public" / "art" / "mosaic"

# 320px is the largest a panel renders; 2x covers every display we support.
RENDER_PX = 640
WEBP_QUALITY = 82


def encode(master: Path, out_dir: Path) -> Path:
    """Write one master out as the WebP the app loads."""
    with Image.open(master) as im:
        im = im.convert("RGB").resize((RENDER_PX, RENDER_PX), Image.LANCZOS)
        target = out_dir / f"{master.stem}.webp"
        im.save(target, "WEBP", quality=WEBP_QUALITY, method=6)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed WebP files match the masters, write nothing",
    )
    args = parser.parse_args()

    masters = sorted(MASTERS.glob("*.jpg"))
    if not masters:
        sys.exit(f"no masters found in {MASTERS.relative_to(REPO)}")

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            stale = []
            for master in masters:
                fresh = encode(master, Path(tmp))
                committed = OUTPUT / fresh.name
                if not committed.exists():
                    stale.append(f"{fresh.name} is missing")
                elif committed.read_bytes() != fresh.read_bytes():
                    stale.append(f"{fresh.name} differs from its master")
            if stale:
                print("\n".join(stale), file=sys.stderr)
                print("\nrun: python3 scripts/build_mosaic_assets.py", file=sys.stderr)
                return 1
        print(f"{len(masters)} panels match their masters")
        return 0

    OUTPUT.mkdir(parents=True, exist_ok=True)
    for master in masters:
        target = encode(master, OUTPUT)
        print(f"{target.name:20} {target.stat().st_size // 1024:>4} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
