"""Design slides: a slide the agent lays out itself in HTML and CSS.

The five templates (photo, text, collage, before-after, editorial) cover the
common carousel shapes, and a text-led slide in them is a centred paragraph:
a three-point brief, a comparison table or a checklist reads as a wall of
words, and the agent could only answer "I can't add custom HTML/CSS here"
(2026-11-27). Current models lay out a 1080×1920 card well when they can see
the result, and ``render_slide`` lets them: draw, render, look, fix. The
brief is creative freedom (a Canva-grade card or better), so the allowlist is
wide on anything that draws (CSS, SVG shapes, gradients, filters, masks, a
dozen fonts) and closed on anything that acts.

The markup is the model's, so it is treated as untrusted three times. Here it
is rebuilt from an allowlist when stored (layout, text and SVG drawing
elements and presentational attributes only: no script, frame, link, event
handler or SVG animation, references only to ids in the slide itself; CSS
that cannot import, run code or pin to the window); in the app it renders in
a frame that runs no scripts; and the capture that turns it into the
published PNG strips scripts, frames, SVG animation and event handlers again
from the parsed DOM before it touches the page (``app/src/lib/slideCapture.js``).
Its CSS is scoped to its own slide with ``@scope``, and its ids are prefixed
with the slide's own at render (``scope_ids``), because the stored
``slides_html`` holds every slide of a post in one document: two slides each
defining ``#glow`` would otherwise both paint the first one's.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

MAX_HTML_CHARS = 30_000
MAX_CSS_CHARS = 16_000

# The fonts a design slide may name, loaded in every slide document's head
# beside the templates' Inter and Playfair Display. A browser downloads only
# the faces a slide uses, and the capture embeds only those, so the list costs
# a stylesheet, not a font file per family. ``@import`` is stripped from slide
# CSS, so a font not here is not reachable: add it here, never per slide.
DESIGN_FONTS: tuple[tuple[str, str], ...] = (
    ("Inter", "Inter:wght@300;400;500;600;700;800;900"),
    ("Playfair Display", "Playfair+Display:ital,wght@0,400;0,700;1,400"),
    ("Space Grotesk", "Space+Grotesk:wght@400..700"),
    ("Bricolage Grotesque", "Bricolage+Grotesque:wght@400..800"),
    ("Syne", "Syne:wght@500..800"),
    ("Archivo Black", "Archivo+Black"),
    ("Anton", "Anton"),
    ("Bebas Neue", "Bebas+Neue"),
    ("Fraunces", "Fraunces:ital,wght@0,400..900;1,400..900"),
    ("DM Serif Display", "DM+Serif+Display:ital@0;1"),
    ("Instrument Serif", "Instrument+Serif:ital@0;1"),
    ("Caveat", "Caveat:wght@500..700"),
    ("JetBrains Mono", "JetBrains+Mono:wght@400..700"),
)
DESIGN_FONT_NAMES = ", ".join(name for name, _ in DESIGN_FONTS)

_SKIP = frozenset({"script", "style", "template", "noscript", "iframe", "object", "title", "textarea"})

# An allowlist, read by a real HTML parser: anything not named here (script,
# frames, forms, links, SVG animation that can rewrite attributes, any event
# handler, any external reference) is dropped, however it is spelled. A regex
# denylist was the first draft and a review showed the usual bypasses
# (``<svg/onload=…>``). The parser lowercases names; the browser's HTML parser
# puts SVG's camelCase back (``lineargradient`` → ``linearGradient``).
_HTML_TAGS = {
    "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
    "b", "strong", "i", "em", "u", "s", "small", "sup", "sub", "mark", "br", "hr",
    "wbr", "img", "figure", "figcaption", "blockquote", "section", "header",
    "footer", "article", "aside", "main", "time", "code", "pre", "q", "cite",
    "abbr", "del", "ins", "dl", "dt", "dd",
    "table", "caption", "thead", "tbody", "tfoot", "tr", "td", "th", "col", "colgroup",
}
_SVG_TAGS = {
    "svg", "g", "defs", "symbol", "use", "path", "circle", "ellipse", "rect",
    "line", "polyline", "polygon", "text", "tspan", "textpath", "marker",
    "lineargradient", "radialgradient", "stop", "pattern", "clippath", "mask",
    "filter", "fegaussianblur", "feoffset", "fedropshadow", "fecolormatrix",
    "feblend", "fecomposite", "feflood", "femerge", "femergenode", "feturbulence",
    "fedisplacementmap", "femorphology", "fecomponenttransfer", "fefuncr",
    "fefuncg", "fefuncb", "fefunca",
}
_TAGS = frozenset(_HTML_TAGS | _SVG_TAGS)
_VOID = frozenset({
    "br", "hr", "wbr", "img", "col", "path", "circle", "ellipse", "rect", "line",
    "polyline", "polygon", "stop", "use", "fegaussianblur", "feoffset",
    "fedropshadow", "fecolormatrix", "feblend", "fecomposite", "feflood",
    "femergenode", "feturbulence", "fedisplacementmap", "femorphology",
    "fefuncr", "fefuncg", "fefuncb", "fefunca",
})
_ATTRS = frozenset({
    # HTML
    "class", "style", "src", "alt", "width", "height", "colspan", "rowspan", "dir",
    "id", "href", "xlink:href",
    # SVG geometry and paint
    "viewbox", "xmlns", "xmlns:xlink", "d", "fill", "stroke", "stroke-width",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset",
    "stroke-miterlimit", "fill-opacity", "stroke-opacity", "fill-rule", "clip-rule",
    "opacity", "transform", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r",
    "rx", "ry", "fx", "fy", "fr", "points", "pathlength", "offset", "stop-color",
    "stop-opacity", "gradientunits", "gradienttransform", "spreadmethod",
    "preserveaspectratio", "paint-order", "vector-effect", "display", "visibility",
    "overflow", "clip-path", "mask", "filter", "mix-blend-mode",
    "patternunits", "patterncontentunits", "patterntransform", "maskunits",
    "maskcontentunits", "clippathunits", "filterunits", "primitiveunits",
    "marker-start", "marker-mid", "marker-end", "markerwidth", "markerheight",
    "markerunits", "refx", "refy", "orient",
    # SVG text
    "text-anchor", "dominant-baseline", "font-size", "font-weight", "font-family",
    "font-style", "letter-spacing", "word-spacing", "text-decoration", "dx", "dy",
    "rotate", "textlength", "lengthadjust", "startoffset", "method", "spacing",
    # SVG filter primitives
    "in", "in2", "result", "mode", "operator", "values", "type", "stddeviation",
    "basefrequency", "numoctaves", "seed", "stitchtiles", "scale",
    "xchannelselector", "ychannelselector", "radius", "k1", "k2", "k3", "k4",
    "flood-color", "flood-opacity", "tablevalues", "slope", "intercept",
    "amplitude", "exponent", "color-interpolation-filters",
})
# A picture over https, an inline one, or one of ours (one slash, never two:
# "//host" is another site).
_SAFE_SRC = re.compile(r"^(https://|data:image/(png|jpe?g|webp|gif);|/(?!/))", re.I)
# An id is a name for an SVG reference, nothing more.
_SAFE_ID = re.compile(r"^[A-Za-z][\w-]{0,63}$")
# In an attribute, url() may point only at this slide's own ids.
_ATTR_URL = re.compile(r"url\(\s*(['\"]?)(?!#)[^)]*\)", re.I)


class _Allowlist(HTMLParser):
    """Rebuilds the markup from allowed parts, balanced: an unclosed or stray
    tag in the model's markup would otherwise close the slide's own wrapper
    and pull the next slide inside it."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[str] = []
        self.skip = 0  # inside an element whose whole content is dropped

    def _attrs(self, attrs) -> str:
        kept = []
        for name, value in attrs:
            name = (name or "").lower()
            value = (value or "").strip()
            if name not in _ATTRS:
                continue
            if name == "src" and not _SAFE_SRC.match(value):
                continue
            if name in ("href", "xlink:href") and not value.startswith("#"):
                continue
            if name == "id" and (not _SAFE_ID.match(value) or value.lower().startswith("slide-")):
                continue
            if name == "style":
                value = clean_design_css(value)
            elif "url(" in value.lower():
                value = _ATTR_URL.sub("none", value)
            kept.append(f' {name}="{html.escape(value, quote=True)}"')
        return "".join(kept)

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip or tag not in _TAGS:
            return
        if tag in _VOID:
            self.out.append(f"<{tag}{self._attrs(attrs)} />")
            return
        self.out.append(f"<{tag}{self._attrs(attrs)}>")
        self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in _SKIP or self.skip or tag not in _TAGS:
            return
        if tag in _VOID:
            self.handle_starttag(tag, attrs)
        else:
            self.out.append(f"<{tag}{self._attrs(attrs)}></{tag}>")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.open:
            return  # a stray close never reaches past what this slide opened
        while self.open:
            last = self.open.pop()
            self.out.append(f"</{last}>")
            if last == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        return "".join(self.out) + "".join(f"</{t}>" for t in reversed(self.open))


_CSS_IMPORT = re.compile(r"@import[^;]*;?", re.I)
_CSS_BREAKOUT = re.compile(r"</\s*style", re.I)
_CSS_FIXED = re.compile(r"position\s*:\s*fixed", re.I)
_CSS_CODE = re.compile(r"(expression\s*\(|javascript:|behavior\s*:|-moz-binding)", re.I)
# A url() may name a picture over https, an inline one, one of ours, or an id
# in this slide's SVG (a clip path, a mask, a filter).
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(?!https:|data:image/|/(?!/)|#)[^)]*\)", re.I)


def clean_design_html(markup: str) -> str:
    """The slide's markup rebuilt from the allowlist: only layout, text and
    drawing elements, only presentational attributes, pictures from safe
    sources, references only within the slide."""
    parser = _Allowlist()
    parser.feed(str(markup or "")[:MAX_HTML_CHARS])
    parser.close()
    return parser.result()


def clean_design_css(css: str) -> str:
    """The slide's stylesheet, unable to import, break out of its tag, run
    code or pin anything to the window."""
    text = str(css or "")[:MAX_CSS_CHARS]
    text = _CSS_IMPORT.sub("", text)
    # No "<" at all: a stylesheet never needs one, and without it nothing in
    # the CSS can close its <style> tag and open another.
    text = _CSS_BREAKOUT.sub("", text).replace("<", "")
    text = _CSS_CODE.sub("", text)
    text = _CSS_FIXED.sub("position: absolute", text)
    return _CSS_URL.sub("none", text)


_ID_ATTR = re.compile(r'(\s)id="([\w-]+)"')
_ID_HREF = re.compile(r'(\s(?:xlink:)?href)="#([\w-]+)"')
_ID_URL = re.compile(r"url\(\s*(['\"]?)#([\w-]+)\1\s*\)")


def scope_ids(text: str, prefix: str) -> str:
    """Every id the slide defines or references, prefixed with its own slide
    id. ``scopeIds`` in ``app/src/lib/slideDoc.js`` does the same."""
    text = _ID_ATTR.sub(lambda m: f'{m[1]}id="{prefix}-{m[2]}"', text)
    text = _ID_HREF.sub(lambda m: f'{m[1]}="#{prefix}-{m[2]}"', text)
    return _ID_URL.sub(lambda m: f"url({m[1]}#{prefix}-{m[2]}{m[1]})", text)


def design_slide_markup(slide_html: str, slide_css: str, n: int) -> str:
    """One design slide as the renderer writes it. The app's
    ``renderDesign`` in ``app/src/lib/slideDoc.js`` writes the same markup."""
    sid = f"slide-{n:02d}"
    css = scope_ids(clean_design_css(slide_css), sid) if slide_css else ""
    style = f"<style>@scope (#{sid}) {{ {css} }}</style>" if css else ""
    return (
        f'<div class="slide slide-design" id="{sid}">{style}'
        f'<div class="design">{scope_ids(clean_design_html(slide_html), sid)}</div></div>'
    )
