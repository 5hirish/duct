#!/usr/bin/env python3
"""Local static server with Cloudflare Pages-style route fallback.

Examples:
  python3 dev_server.py
  python3 dev_server.py --port 8080
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import unquote, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parent


class CloudflarePagesDevHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean = unquote(parsed.path.lstrip("/"))

        if not clean:
            return str(ROOT / "index.html")

        # Block path traversal attempts.
        if ".." in Path(clean).parts:
            return str(ROOT / "__not_found__")

        base = ROOT / clean
        candidates = [base]
        if base.suffix == "":
            candidates.append(base.with_suffix(".html"))
            candidates.append(base / "index.html")

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        return str(base)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the marketing site locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CloudflarePagesDevHandler)
    print(f"Serving Cloudflare-style site routes on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
