#!/usr/bin/env python3
"""Local static server with Cloudflare Pages-style route fallback.

Examples:
  python3 dev_server.py
  python3 dev_server.py --port 8090
"""

from __future__ import annotations

import argparse
import os
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parent
ROOT_PREFIX = str(ROOT) + os.sep
NOT_FOUND_PAGE = ROOT / "404.html"
MISS = str(ROOT / "__not_found__")


def _under_root(relative: str) -> Path | None:
    """Join a URL path onto ROOT, or None if the result escapes it.

    Joined as strings and normalised before it is trusted, because
    `ROOT / relative` is not safe here: pathlib discards the left operand
    when the right one is absolute, and a request for "/%2Fetc/passwd"
    unquotes to exactly that. normpath also collapses any ".." lexically,
    so one prefix check covers both traversal and the absolute case.
    """
    candidate = os.path.normpath(os.path.join(str(ROOT), relative))
    if candidate != str(ROOT) and not candidate.startswith(ROOT_PREFIX):
        return None
    return Path(candidate)


class CloudflarePagesDevHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path: str) -> str:
        # Unquote before stripping the leading slashes, not after: "%2Fetc/..."
        # is still one harmless-looking segment until it is decoded.
        clean = unquote(urlparse(path).path).lstrip("/")

        if not clean:
            return str(ROOT / "index.html")

        base = _under_root(clean)
        if base is None:
            return MISS

        candidates = [base]
        if base.suffix == "":
            candidates.append(base.with_suffix(".html"))
            candidates.append(base / "index.html")

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return str(base)

    def send_head(self):
        """Serve 404.html for unmatched routes, the way Cloudflare Pages does.

        Without this the page can only ever be viewed at /404.html, where every
        relative asset path happens to resolve — the one URL that hides the bug
        of a 404 rendering unstyled below the site root.
        """
        # translate_path has already contained the path; anything it could not
        # contain comes back as MISS, which never exists.
        translated = Path(self.translate_path(self.path))
        if translated.exists() or not NOT_FOUND_PAGE.exists():
            return super().send_head()

        body = NOT_FOUND_PAGE.read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        return BytesIO(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the marketing site locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CloudflarePagesDevHandler)
    print(f"Serving Cloudflare-style site routes on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
