"""The page extractor reads a page the way a search engine does.

It parses whatever HTML a crawled site sends, on selectolax's Lexbor backend
(Modest, the default, is no longer maintained upstream). The two disagree in
ways that change an audit: Modest matched every attribute value ignoring case,
Lexbor only the few the selectors spec names (`rel`, `type`, ...), so a
selector reading a value search engines treat case-insensitively carries the
`i` flag. These pin that, and where Lexbor now reads a page like a browser.
"""

from __future__ import annotations

from service.crawl.extractor import extract_signals

URL = "https://example.com/pricing"


def test_uppercase_meta_names_are_still_read():
    """`<meta NAME="ROBOTS">` is common on older sites. Matched case-sensitively,
    its noindex went unseen and the description read as missing."""
    signals = extract_signals(
        '<head><meta NAME="ROBOTS" content="NOINDEX">'
        '<meta name="Description" content="Plans and prices">'
        '<meta PROPERTY="og:Title" content="Pricing">'
        '<meta name="Twitter:Card" content="summary"></head>',
        URL,
    )
    assert signals.is_noindex
    assert signals.meta_description == "Plans and prices"
    assert signals.og_title == "Pricing"
    assert signals.twitter_card == "summary"


def test_template_content_is_not_part_of_the_page():
    """A <template> is inert until script clones it: a browser renders none of
    it, so its headings and links are not the page's. Modest counted them."""
    signals = extract_signals(
        '<body><template><h1>Draft</h1><a href="/draft">d</a></template><h1>Pricing</h1></body>', URL
    )
    assert signals.h1s == ["Pricing"]
    assert signals.internal_links == []


def test_an_empty_alt_still_counts_as_missing():
    """Lexbor reports `alt=""` as an empty string where Modest reported None;
    the audit's reading of it does not change with the backend."""
    signals = extract_signals('<img src="a.png" alt=""><img src="b.png"><img src="c.png" alt="Logo">', URL)
    assert (signals.image_count, signals.images_missing_alt) == (3, 2)
