#!/usr/bin/env python3
"""
Validates every marketing HTML page under site/ against the Duct <head> checklist
(see CLAUDE.md).

Exits non-zero if any required element is missing or out of spec.
"""

import sys
import os
import glob
import json
from html.parser import HTMLParser

# ── Configuration ─────────────────────────────────────────────────────────────

# Pages where canonical AND meta description are set dynamically by JS.
# Empty since blog posts became static (scripts/build_blog.py); kept because
# the next dynamic page should be declared here rather than special-cased.
DYNAMIC_META = set()

# Error/utility pages — skip all SEO checks (no canonical, OG, Twitter needed).
ERROR_PAGES = {"404.html"}

REQUIRED_OG = {"og:type", "og:url", "og:title", "og:description", "og:image", "og:site_name"}
REQUIRED_TWITTER = {"twitter:card", "twitter:title", "twitter:description", "twitter:image"}

CANONICAL_BASE = "https://getduct.ai"

# ── HTML parser ───────────────────────────────────────────────────────────────

class PageChecker(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.errors = []
        self.warnings = []

        self.has_canonical = False
        self.canonical_href = None
        self.description = None
        self.has_robots = False
        self.og_props = set()
        self.twitter_props = set()
        self.has_css = False
        self.has_config_js = False
        self.has_duct_js = False
        self.duct_js_defer = False
        self.has_gtm_noscript = False
        self._in_noscript = False
        self._saw_body = False
        self.ld_blocks = []
        self._in_ld = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "body":
            self._saw_body = True

        if tag == "noscript":
            self._in_noscript = True

        if tag == "iframe" and self._in_noscript:
            src = attrs.get("src", "")
            if "googletagmanager.com/ns.html" in src:
                self.has_gtm_noscript = True

        if tag == "link":
            rel = attrs.get("rel", "")
            href = attrs.get("href", "")
            if rel == "canonical":
                self.has_canonical = True
                self.canonical_href = href
            if rel == "stylesheet" and "duct.css" in href:
                self.has_css = True

        if tag == "meta":
            name = attrs.get("name", "").lower()
            prop = attrs.get("property", "").lower()
            content = attrs.get("content", "")

            if name == "description":
                self.description = content
            if name == "robots":
                self.has_robots = True
            if prop in REQUIRED_OG:
                self.og_props.add(prop)
            if name in REQUIRED_TWITTER:
                self.twitter_props.add(name)

        if tag == "script":
            if attrs.get("type", "").lower() == "application/ld+json":
                self._in_ld = True
            src = attrs.get("src", "")
            if "config.js" in src:
                self.has_config_js = True
            if "duct.js" in src:
                self.has_duct_js = True
                self.duct_js_defer = "defer" in attrs

    def handle_data(self, data):
        if self._in_ld:
            self.ld_blocks.append(data)

    def handle_endtag(self, tag):
        if tag == "noscript":
            self._in_noscript = False
        if tag == "script":
            self._in_ld = False

    def run_checks(self, rel_path):
        is_dynamic = rel_path in DYNAMIC_META
        is_error = rel_path in ERROR_PAGES

        # Error pages only need CSS/JS; skip all SEO checks.
        if is_error:
            return

        # Determine expected asset prefix
        is_blog = rel_path.startswith("blog/")
        asset_prefix = "../assets/" if is_blog else "assets/"

        # Canonical
        if not is_dynamic:
            if not self.has_canonical:
                self.errors.append("Missing <link rel='canonical'>")
            elif self.canonical_href and not self.canonical_href.startswith(CANONICAL_BASE):
                self.errors.append(f"Canonical does not start with {CANONICAL_BASE}: {self.canonical_href!r}")
            elif self.canonical_href and self.canonical_href.endswith(".html"):
                self.errors.append(f"Canonical should use clean URL (no .html): {self.canonical_href!r}")

        # Description (dynamic pages set this via JS)
        if not is_dynamic:
            if self.description is None:
                self.errors.append("Missing <meta name='description'>")

        # Robots
        if not self.has_robots:
            self.errors.append("Missing <meta name='robots'>")

        # JSON-LD. A malformed block is silently dropped by every consumer, so a
        # page keeps rendering while its structured data is simply gone — which
        # is exactly the failure an answer engine punishes and nobody notices.
        for i, block in enumerate(self.ld_blocks):
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError as exc:
                self.errors.append(f"JSON-LD block {i + 1} is not valid JSON: {exc}")
                continue
            for obj in parsed if isinstance(parsed, list) else [parsed]:
                if not isinstance(obj, dict):
                    self.errors.append(f"JSON-LD block {i + 1} is not an object")
                elif "@type" not in obj:
                    self.errors.append(f"JSON-LD block {i + 1} has no @type")

        # OG tags
        missing_og = REQUIRED_OG - self.og_props
        if missing_og:
            self.errors.append(f"Missing OG properties: {', '.join(sorted(missing_og))}")

        # Twitter tags
        missing_tw = REQUIRED_TWITTER - self.twitter_props
        if missing_tw:
            self.errors.append(f"Missing Twitter meta tags: {', '.join(sorted(missing_tw))}")

        # CSS
        if not self.has_css:
            self.errors.append(f"Missing <link rel='stylesheet' href='{asset_prefix}duct.css'>")

        # config.js + duct.js
        if not self.has_config_js:
            self.errors.append(f"Missing <script src='{asset_prefix}config.js'>")
        if not self.has_duct_js:
            self.errors.append(f"Missing <script src='{asset_prefix}duct.js'>")
        elif not self.duct_js_defer:
            self.errors.append("duct.js script tag is missing the 'defer' attribute")

        # GTM noscript
        if not self.has_gtm_noscript:
            self.errors.append("Missing GTM <noscript><iframe> immediately after <body>")


# ── Runner ────────────────────────────────────────────────────────────────────

def check_file(filepath, site_root):
    rel = os.path.relpath(filepath, site_root)
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    checker = PageChecker(rel)
    checker.feed(content)
    checker.run_checks(rel)
    return checker.errors, checker.warnings


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    site_root = os.path.join(repo_root, "site")
    html_files = sorted(
        glob.glob(os.path.join(site_root, "*.html")) +
        glob.glob(os.path.join(site_root, "blog", "*.html"))
    )

    total_errors = 0
    total_warnings = 0

    for filepath in html_files:
        rel = os.path.relpath(filepath, site_root)
        errors, warnings = check_file(filepath, site_root)

        if errors or warnings:
            print(f"\n{'─' * 60}")
            print(f"  {rel}")
            print(f"{'─' * 60}")
            for e in errors:
                print(f"  ✗ ERROR   {e}")
            for w in warnings:
                print(f"  ⚠ WARNING {w}")

        total_errors += len(errors)
        total_warnings += len(warnings)

    print(f"\n{'═' * 60}")
    print(f"  Checked {len(html_files)} pages — "
          f"{total_errors} error(s), {total_warnings} warning(s)")
    print(f"{'═' * 60}\n")

    if total_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
