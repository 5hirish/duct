#!/usr/bin/env python3
"""Local static server with Cloudflare Pages-style route fallback.

Examples:
  python3 dev_server.py
  python3 dev_server.py --port 8090
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parent
NOT_FOUND_PAGE = ROOT / "404.html"


class CloudflarePagesDevHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _safe_under_root(self, candidate: Path) -> Path | None:
        resolved_root = ROOT.resolve()
        resolved_candidate = candidate.resolve()
        try:
            resolved_candidate.relative_to(resolved_root)
        except ValueError:
            return None
        return resolved_candidate

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
            safe_candidate = self._safe_under_root(candidate)
            if safe_candidate is not None and safe_candidate.exists():
                return str(safe_candidate)

        safe_base = self._safe_under_root(base)
        if safe_base is None:
            return str(ROOT / "__not_found__")
        return str(safe_base)

    def send_head(self):
        """Serve 404.html for unmatched routes, the way Cloudflare Pages does.

        Without this the page can only ever be viewed at /404.html, where every
        relative asset path happens to resolve — the one URL that hides the bug
        of a 404 rendering unstyled below the site root.
        """
        translated = Path(self.translate_path(self.path))
        safe_path = self._safe_under_root(translated)
        if (safe_path is not None and safe_path.exists()) or not NOT_FOUND_PAGE.exists():
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
