#!/usr/bin/env python3
"""Generate the integrations hub and one page per connector, from the backend.

    python3 scripts/build_integrations.py          # writes site/integrations/*.html
    python3 scripts/build_integrations.py --check  # CI: fails if a page is stale

A connector page says three things a visitor weighs before installing: what
Duct reads, what it can change, and when a change waits for a person. All
three already exist in code, so they are read from it rather than restated:

- what it reads: the entity catalogue (backend/agents/insights/catalog/), or
  for a connector without one, the `reads` list in the copy file checked
  against the fetch module it names;
- what it can change: every `ExecutorSpec` registered under
  backend/service/execution/, with its rollback and destructive flags;
- when it waits: `AUTO_APPLY_ALLOWLIST` in service/execution/policy.py, the
  only operations that may apply without a click, and only in assisted mode;
- how you sign in: `ConnectorMeta` (an OAuth scope, or none for a pasted key).

The backend is parsed, never imported: this runs on the site's CI job, which
installs nothing, and a module-level literal is all these files expose anyway
(the catalogues are dict literals on purpose; see catalog/base.py).

What code cannot say (the questions, the knowledge-pack rules in plain words,
setup, FAQ) is hand-written in scripts/integrations/connectors.py. `--check`
fails when a connector gains a field or an operation and its page has not been
regenerated, and when the backend registers a connector the hub does not list,
so the pages cannot drift from the product the way the site's connector count
once did (it said thirteen while HubSpot was still "Coming soon" in the app).

The English pages are then translated by scripts/build_site_i18n.py like any
hand-written page; the hreflang block written here is that script's own.
"""

from __future__ import annotations

import argparse
import ast
import html
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = SITE / "integrations"
BACKEND = ROOT / "backend"
BASE_URL = "https://getduct.ai"
REPO_BLOB = "https://github.com/5hirish/duct/blob/main/"
DISCUSSIONS = "https://github.com/5hirish/duct/discussions"
MCP_ISSUE = "https://github.com/5hirish/duct/issues/197"
GTM_ID = "GTM-PKL589SW"

sys.path.insert(0, str(ROOT / "scripts"))
import build_site_i18n as i18n  # noqa: E402  (its hreflang block, so the two scripts agree)

TITLE_MAX = 60
DESCRIPTION_RANGE = (140, 160)
NUMBER_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
                "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
                "Seventeen", "Eighteen", "Nineteen", "Twenty"]
#: How a catalogue field reads on the page when it carries no label of its own.
FIELD_WORDS = {"roas": "ROAS", "ctr": "CTR", "cpc": "CPC", "cpm": "CPM", "cpa": "CPA",
               "avg_position": "avg. position", "country_criterion_id": "country",
               "campaign_name": "campaign", "ad_group_name": "ad group", "page_path": "page",
               "session_source_medium": "source / medium",
               "session_default_channel_group": "channel group", "total_revenue": "revenue"}


class BuildError(Exception):
    pass


# ---------------------------------------------------------------------------
# Reading the backend
# ---------------------------------------------------------------------------

def _module_literal(path: Path, name: str):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        targets = node.targets if isinstance(node, ast.Assign) else [target] if target else []
        if any(getattr(t, "id", None) == name for t in targets):
            value = node.value
            # frozenset({...}) is how the allowlist is spelled; its argument is the literal.
            if isinstance(value, ast.Call) and getattr(value.func, "id", "") in {"frozenset", "set"}:
                value = value.args[0]
            return ast.literal_eval(value)
    raise BuildError(f"{path.relative_to(ROOT)} has no literal {name}")


def _calls(path: Path, func: str):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == func:
            yield {k.arg: k.value for k in node.keywords}


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def read_catalogs() -> dict[str, dict]:
    out = {}
    for path in sorted((BACKEND / "agents/insights/catalog").glob("*.py")):
        if path.stem in {"__init__", "base", "prompt"}:
            continue
        catalog = _module_literal(path, "ENTITY_CATALOG")
        catalog["file"] = path.relative_to(ROOT).as_posix()
        out[catalog["connector_id"]] = catalog
    return out


def read_executors() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for path in sorted((BACKEND / "service/execution").glob("*_exec.py")):
        for kw in _calls(path, "ExecutorSpec"):
            rollback = kw.get("rollback")
            out.setdefault(_const(kw["connector_type"]), []).append({
                "op": _const(kw["op_type"]),
                "label": _const(kw["label"]),
                "destructive": bool(_const(kw["destructive"])) if "destructive" in kw else False,
                # `rollback=None` spelled out is as absent as leaving it off.
                "rollback": rollback is not None and not (isinstance(rollback, ast.Constant) and rollback.value is None),
            })
    return out


def read_metas() -> dict[str, dict]:
    """ConnectorMeta by label: whether it signs in with OAuth, and the file that registers it."""
    out = {}
    for path in sorted((BACKEND / "service").rglob("*.py")):
        for kw in _calls(path, "ConnectorMeta"):
            label = _const(kw.get("label"))
            if label:
                scope = kw.get("oauth_scope")
                out[label] = {"oauth": not (isinstance(scope, ast.Constant) and scope.value is None),
                              "file": path.relative_to(ROOT).as_posix()}
    return out


def load_copy():
    spec = importlib.util.spec_from_file_location("integrations_copy", ROOT / "scripts/integrations/connectors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The model: copy joined with the backend, and everything that must hold
# ---------------------------------------------------------------------------

def build_model():
    copy = load_copy()
    catalogs, executors, metas = read_catalogs(), read_executors(), read_metas()
    allow = _module_literal(BACKEND / "service/execution/policy.py", "AUTO_APPLY_ALLOWLIST")
    stripe_version = _module_literal(BACKEND / "service/stripe/client.py", "STRIPE_VERSION")
    errors: list[str] = []
    by_id = {c["id"]: c for c in copy.CONNECTORS}
    groups = {g for g, _ in copy.GROUPS}

    listed = {c.get("label") for c in copy.CONNECTORS if not c.get("soon")}
    for label, meta in metas.items():
        if label not in listed:
            errors.append(f"{meta['file']} registers the connector {label!r}, which the integrations hub "
                          "does not list: add it to scripts/integrations/connectors.py")
    for connector_type in executors:
        if connector_type not in by_id:
            errors.append(f"executors exist for {connector_type!r}, which the copy file does not name")

    for c in copy.CONNECTORS:
        cid = c["id"]
        c.setdefault("short", c["name"])
        if c["group"] not in groups:
            errors.append(f"{cid}: unknown group {c['group']!r}")
        if not (SITE / "assets/icons" / c["logo"]).is_file():
            errors.append(f"{cid}: site/assets/icons/{c['logo']} does not exist")
        c["ops"] = [dict(op, auto=op["op"] in allow) for op in executors.get(cid, [])]
        c["catalog"] = catalogs.get(cid)
        if c.get("soon"):
            continue
        meta = metas.get(c["label"])
        if not meta:
            errors.append(f"{cid}: no ConnectorMeta labelled {c['label']!r} in backend/service")
        else:
            if meta["file"] != c["meta"]:
                errors.append(f"{cid}: registered in {meta['file']}, the copy file says {c['meta']}")
            if meta["oauth"] != c["auth"].startswith("Sign in"):
                errors.append(f"{cid}: signs in {'with OAuth' if meta['oauth'] else 'with a pasted key'}, "
                              f"but the copy says {c['auth']!r}")
        if not (ROOT / c["pack"]).is_file():
            errors.append(f"{cid}: knowledge pack {c['pack']} does not exist")
        page = c.get("page")
        if not page:
            continue
        if c["catalog"]:
            if c.get("reads"):
                errors.append(f"{cid}: has an entity catalogue, so `reads` must come from it, not the copy file")
            c["api_line"] = c.get("api", "{api_version}").format(api_version=c["catalog"]["api_version"])
        else:
            if not c.get("reads") or not c.get("source") or not c.get("checked"):
                errors.append(f"{cid}: no entity catalogue, so the copy needs `reads`, `source` and `checked`")
            elif not (ROOT / c["source"]).is_file():
                errors.append(f"{cid}: source {c['source']} does not exist")
            c["api_line"] = c.get("api", "").format(stripe_version=stripe_version)
        if len(page["title"]) > TITLE_MAX:
            errors.append(f"{cid}: title is {len(page['title'])} characters, the limit is {TITLE_MAX}")
        lo, hi = DESCRIPTION_RANGE
        if not lo <= len(page["description"]) <= hi:
            errors.append(f"{cid}: description is {len(page['description'])} characters, keep it {lo}–{hi}")
        named = [j for _, joins in page["questions"] for j in joins] + page["hero"]["joins"] + [o for o, _ in page["pairs"]]
        for other in named:
            if other not in by_id or by_id[other].get("soon"):
                errors.append(f"{cid}: names {other!r}, which is not a live connector")
        if not c["ops"] and any("{changes}" in a for _, a in page["faq"]):
            errors.append(f"{cid}: the FAQ lists its changes, but the backend registers none for it")
    if errors:
        raise BuildError("\n".join(errors))
    return copy, by_id


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def e(text: str) -> str:
    return html.escape(text, quote=True)


def plain(markup: str) -> str:
    """Visible text of a snippet, for JSON-LD: same words as the page, no tags."""
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def icon(name: str) -> str:
    return f'<svg class="ic" aria-hidden="true"><use href="/assets/icons.svg#{name}"/></svg>'


def logo(c: dict, size: int) -> str:
    return f'<img src="../assets/icons/{c["logo"]}" width="{size}" height="{size}" alt=""/>'


def human_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def sentence_case(text: str, first: bool = True) -> str:
    """"Campaign Performance" → "Campaign performance": the site writes sentence
    case (DESIGN.md, Voice). Acronyms and names with digits (GA4, ROAS) keep theirs."""
    words = text.split(" ")
    keep = lambda w: w.isupper() or any(ch.isdigit() for ch in w)  # noqa: E731
    out = [w if keep(w) else w.lower() for w in words]
    if first and out and not keep(words[0]):
        out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out)


def field_word(name: str, spec) -> str:
    if name in FIELD_WORDS:
        return FIELD_WORDS[name]
    if isinstance(spec, dict):
        if spec.get("type") == "classification":
            return "suggested action"
        if spec.get("label"):
            return sentence_case(spec["label"], first=False)
    return name.replace("_", " ")


def page_url(c: dict) -> str:
    return f"/integrations/{c['slug']}"


def link_for(c: dict) -> str:
    """A connector's page, or its card on the hub until it has one."""
    return page_url(c) if c.get("page") else f"/integrations/#{c['slug']}"


def reads_of(c: dict) -> list[tuple[str, list[str]]]:
    if c["catalog"]:
        return [(sentence_case(ent["label"]), [field_word(n, s) for n, s in ent["fields"].items()])
                for ent in c["catalog"]["entities"]]
    return [(label, [field_word(f, None) for f in fields]) for label, fields in c["reads"]]


def and_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def changes_sentence(c: dict) -> str:
    ops = c["ops"]
    labels = [op["label"][0].lower() + op["label"][1:] for op in ops]
    back = sum(op["rollback"] for op in ops)
    tail = "every one can be rolled back" if back == len(ops) else f"{NUMBER_WORDS[back].lower()} of them can be rolled back"
    return (f"{NUMBER_WORDS[len(ops)]}: {and_list(labels)}. "
            f"By default each one waits for your Apply, and {tail}.")


def fill(answer: str, copy, c: dict) -> str:
    return answer.replace("{free}", copy.FREE_ANSWER).replace("{changes}", changes_sentence(c) if c["ops"] else "")


def head(*, title: str, description: str, url_path: str, og_title: str, og_description: str,
         twitter_description: str, og_image: str, ld: list[dict]) -> str:
    canonical = BASE_URL + url_path
    blocks = "\n".join(
        '<script type="application/ld+json">\n' + json.dumps(b, ensure_ascii=False, separators=(",", ":")) + "\n</script>"
        for b in ld)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link rel="icon" href="../assets/icon.svg" type="image/svg+xml"/>
<link rel="apple-touch-icon" href="../assets/apple-icon.svg"/>
<title>{e(title)}</title>
<link rel="canonical" href="{canonical}"/>
<meta name="description" content="{e(description)}"/>
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1"/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="{canonical}"/>
<meta property="og:title" content="{e(og_title)}"/>
<meta property="og:description" content="{e(og_description)}"/>
<meta property="og:image" content="{BASE_URL}/assets/og/{og_image}"/>
<meta property="og:image:width" content="1200"/>
<meta property="og:image:height" content="630"/>
<meta property="og:site_name" content="Duct"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{e(og_title)}"/>
<meta name="twitter:description" content="{e(twitter_description)}"/>
<meta name="twitter:image" content="{BASE_URL}/assets/og/{og_image}"/>
<link rel="stylesheet" href="../assets/duct.css"/>
<script src="../assets/config.js"></script>
{blocks}
</head>
"""


def body_open(experiment: str) -> str:
    return f"""<body>
<a href="#main-content" class="skip-link">Skip to content</a>

<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM_ID}" height="0" width="0" style="display:none;visibility:hidden" title="Google Tag Manager"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->

<!-- GENERATED by scripts/build_integrations.py from the backend and scripts/integrations/connectors.py.
     Do not edit this file: edit those and run the script. -->
<!-- EXPERIMENT: {e(experiment)} -->

<!-- NAV (shared: site/partials/nav-home.html) -->
<div data-duct-partial="/partials/nav-home.html"></div>

<main id="main-content">
"""


BODY_CLOSE = """
<!-- CTA (shared: site/partials/cta-home.html) -->
<div data-duct-partial="/partials/cta-home.html"></div>

</main>

<!-- FOOTER (shared: site/partials/footer-expanded.html) -->
<div data-duct-partial="/partials/footer-expanded.html"><div class="legal-fallback"><a href="/">Duct</a><a href="/about">About</a><a href="/privacy">Privacy Policy</a><a href="/terms">Terms of Service</a></div></div>

<script src="../assets/duct-partials.js"></script>
<script src="../assets/duct.js" defer></script>
<script src="../assets/duct-download.js" defer></script>
</body>
</html>
"""


def faq_section(heading: str, items: list[tuple[str, str]]) -> str:
    rows = "\n".join(
        f'<details class="faq-item">\n<summary class="faq-q">{e(q)}</summary>\n<p class="faq-a">{a}</p>\n</details>'
        for q, a in items)
    return f"""
<!-- FAQ -->
<section class="faq" id="faq">
<div class="faq-inner">
<div class="reveal">
<p class="tag">FAQ</p>
<h2>{heading}</h2>
</div>
<div class="faq-list reveal" style="transition-delay:.08s">
{rows}
</div>
</div>
</section>
"""


def faq_ld(items: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": "en", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in items]}


def breadcrumb_ld(trail: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "inLanguage": "en", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": BASE_URL + path}
        for i, (name, path) in enumerate(trail, 1)]}


def flow_svg(n: int) -> str:
    """The channels from each source down into the answer: the homepage mock's shape, for n sources."""
    gap = 70
    width = gap * (n - 1) + 30
    mid = width / 2
    xs = [15 + gap * i for i in range(n)]
    d = [f"M{x} 0C{x} 16 {mid:g} 14 {mid:g} 30" if x != mid else f"M{mid:g} 0V30" for x in xs]
    bed = "".join(f'<path pathLength="1" d="{p}"/>' for p in d)
    water = "".join(f'<path d="{p}"/>' for p in d)
    return (f'<svg class="ig-flow" viewBox="0 0 {width} 30" width="{width}" height="30" aria-hidden="true">'
            f'<g class="ig-flow-bed">{bed}</g><g class="ig-flow-water">{water}</g></svg>')


def mock(c: dict, by_id: dict) -> str:
    hero = c["page"]["hero"]
    sources = "".join(logo(by_id[j], 34) for j in hero["joins"])
    change = ""
    if hero.get("change"):
        title, detail = hero["change"]
        change = (f'<div class="ig-change">{logo(c, 22)}<span><b>{e(title)}</b><s>{e(detail)}</s></span></div>\n'
                  '<div class="ig-actions"><span class="ig-btn ig-btn-reject">Reject</span>'
                  '<span class="ig-btn ig-btn-apply"><span class="ig-apply-idle">Apply</span>'
                  f'<span class="ig-apply-done">{icon("check")}Applied</span>'
                  '<svg class="ig-cursor" aria-hidden="true"><use href="/assets/icons.svg#mouse-pointer-click"/></svg></span></div>\n')
    return f"""<figure class="ig-mock reveal{' has-change' if change else ''}">
<div class="ig-mock-panel" aria-hidden="true">
<div class="ig-sources">{sources}</div>
{flow_svg(len(hero['joins']))}
<div class="ig-answer">{icon('sparkles')}<span>{e(hero['answer'])}</span></div>
{change}</div>
<figcaption>An example answer. Yours is read from your own accounts.</figcaption>
</figure>"""


# ---------------------------------------------------------------------------
# A connector page
# ---------------------------------------------------------------------------

def connector_page(c: dict, copy, by_id: dict) -> str:
    p = c["page"]
    short = c["short"]
    url_path = page_url(c)
    reads = reads_of(c)
    catalog = c["catalog"]
    checked = human_date(catalog["last_audited"] if catalog else c["checked"])
    faq = [(q, fill(a, copy, c)) for q, a in p["faq"]]

    chips = [
        ("key-round", c["auth"]),
        ("database", f"Reads {NUMBER_WORDS[len(reads)].lower()} datasets"),
        ("shield-check", f"{NUMBER_WORDS[len(c['ops'])]} kinds of change" if c["ops"] else "Read-only"),
        ("circle-check", f"{'Fields audited' if catalog else 'Checked'} {checked}"),
    ]
    chip_html = "".join(f'<li>{icon(i)}<span>{e(t)}</span></li>' for i, t in chips)
    alias = f'<p class="ig-alias">Listed as {e(c["alias"])} in the Duct app.</p>' if c.get("alias") else ""

    questions = "\n".join(
        f'<li class="ig-q reveal" style="transition-delay:{i * .06:.2f}s"><p>{e(q)}</p>'
        f'<span class="ig-q-joins">{"".join(logo(by_id[j], 18) for j in joins)}'
        f'<span>{e(" + ".join(by_id[j]["short"] for j in joins))}</span></span></li>'
        for i, (q, joins) in enumerate(p["questions"]))

    read_rows = "\n".join(
        f'<li><b>{e(label)}</b><span class="ig-fields">{"".join(f"<span>{e(f)}</span>" for f in fields)}</span></li>'
        for label, fields in reads)
    source = catalog["file"] if catalog else c["source"]
    read_note = (f'{e(c["api_line"])} · {"fields audited" if catalog else "checked against the fetch code"} {checked} · '
                 f'<a href="{REPO_BLOB}{source}" rel="noopener">read the source</a>')

    if c["ops"]:
        # A badge marks an exception. Rollback is the rule, so it is one line
        # under the list while every operation has one, and a badge on any that lacks it.
        every_rollback = all(op["rollback"] for op in c["ops"])

        def badges(op):
            out = [] if op["rollback"] else ['<span class="ig-badge is-warn">No rollback</span>']
            if op["destructive"]:
                out.append('<span class="ig-badge is-warn">Always waits for you</span>')
            elif op["auto"]:
                out.append('<span class="ig-badge is-auto">May self-apply in assisted mode</span>')
            return "".join(out)
        op_rows = "\n".join(
            ('<li class="is-destructive">' if op["destructive"] else "<li>") +
            f'{icon("triangle-alert" if op["destructive"] else "check")}<span class="ig-op">{e(op["label"])}</span>'
            f'<span class="ig-badges">{badges(op)}</span></li>' for op in c["ops"])
        changes = f"""<div class="ig-col">
<h3>{icon('shield-check')}What it can change</h3>
<ul class="ig-ops">
{op_rows}
</ul>
<p class="ig-note">{"Every one rolls back. " if every_rollback else ""}By default each change waits for your Apply: it arrives as a preview of what it touches and lands in the activity log. <a href="/doctrine">How approval works</a></p>
</div>"""
    else:
        changes = f"""<div class="ig-col ig-readonly">
<h3>{icon('shield-check')}What it can change</h3>
<p class="ig-readonly-big">Nothing.</p>
<p>Duct has no {e(short)} change operation, so it cannot edit anything in {e(short)}. It can still recommend a change for you to make there.</p>
</div>"""

    knows = "\n".join(
        f'<li class="reveal" style="transition-delay:{i * .06:.2f}s"><span class="ig-k-num">{i + 1:02d}</span>'
        f'<h3>{e(h)}</h3><p>{e(b)}</p></li>'
        for i, (h, b) in enumerate(p["knows"]))

    pairs = "\n".join(
        f'<a class="ig-pair reveal" style="transition-delay:{i * .06:.2f}s" href="{link_for(by_id[o])}">'
        f'<span class="ig-pair-logos">{logo(c, 28)}<span class="ig-pair-pipe" aria-hidden="true"></span>{logo(by_id[o], 28)}</span>'
        f'<span class="ig-pair-q">{e(q)}</span>'
        f'<span class="ig-pair-go">{e(short)} + {e(by_id[o]["short"])} {icon("arrow-right")}</span></a>'
        for i, (o, q) in enumerate(p["pairs"]))

    steps = "\n".join(f'<li><span class="ig-step-n">{i}</span><p>{e(s)}</p></li>'
                      for i, s in enumerate(p["setup"], 1))

    ld = [
        {"@context": "https://schema.org", "@type": "WebPage", "inLanguage": "en", "name": p["title"].removesuffix(" | Duct"),
         "url": BASE_URL + url_path, "description": p["description"],
         "about": {"@type": "SoftwareApplication", "name": c["name"]},
         "isPartOf": {"@type": "WebSite", "name": "Duct", "url": BASE_URL}},
        breadcrumb_ld([("Home", "/"), ("Integrations", "/integrations/"), (c["name"], url_path)]),
        faq_ld(faq),
    ]
    out = head(title=p["title"], description=p["description"], url_path=url_path,
               og_title=p["title"].removesuffix(" | Duct"), og_description=p["og_description"],
               twitter_description=p["twitter_description"], og_image=f"integrations-{c['slug']}.jpg", ld=ld)
    out += body_open(p["experiment"])
    out += f"""
<!-- HERO -->
<section class="ig-hero">
<div class="ig-hero-text">
<nav class="ig-crumbs" aria-label="Breadcrumb"><a href="/integrations/">Integrations</a><span aria-hidden="true">/</span><span aria-current="page">{e(c['name'])}</span></nav>
<div class="ig-lockup" aria-hidden="true">{logo(c, 40)}<span class="ig-plus">+</span><span class="logo">duct <span class="logo-mark"></span></span></div>
<h1>{p['h1']}</h1>
<p class="hero-sub">{e(p['sub'])}</p>
<div class="ig-cta">
<a class="btn btn-orange btn-lg" href="/download" data-duct-download>Download Duct ↓</a>
<a class="btn btn-ghost btn-lg" href="/integrations/">All integrations</a>
</div>
<ul class="ig-facts" aria-label="At a glance">{chip_html}</ul>
{alias}
</div>
{mock(c, by_id)}
</section>

<div class="channel" aria-hidden="true"></div>

<!-- ASK -->
<section class="ig-sec" id="ask">
<div class="ig-inner">
<div class="reveal">
<p class="tag">Ask</p>
<h2>Questions you can <em>just ask</em></h2>
</div>
<ul class="ig-qs">
{questions}
</ul>
</div>
</section>

<!-- ACCESS: generated from the catalogue and the executor registry -->
<section class="ig-sec ig-access" id="access">
<div class="ig-inner">
<div class="reveal">
<p class="tag">Access</p>
<h2>What it reads. <em>What it can change.</em></h2>
</div>
<div class="ig-cols reveal">
<div class="ig-col">
<h3>{icon('database')}What it reads</h3>
<ul class="ig-reads">
{read_rows}
</ul>
<p class="ig-note">{read_note}</p>
</div>
{changes}
</div>
</div>
</section>

<!-- KNOWS: the knowledge pack, in plain words -->
<section class="ig-sec ig-knows" id="knows">
<div class="ig-inner">
<div class="reveal">
<p class="tag">Knowledge</p>
<h2>What Duct already knows <em>about {e(short)}</em></h2>
</div>
<ol class="ig-k">
{knows}
</ol>
<p class="ig-k-src"><a href="{REPO_BLOB}{c['pack']}" rel="noopener">Read the {e(short)} notes Duct's agent works from {icon('arrow-right')}</a></p>
</div>
</section>

<!-- PAIRS -->
<section class="ig-sec" id="pairs">
<div class="ig-inner">
<div class="reveal">
<p class="tag">Better together</p>
<h2>What {e(short)} answers <em>with a partner</em></h2>
</div>
<div class="ig-pairs">
{pairs}
</div>
</div>
</section>

<!-- SETUP -->
<section class="ig-sec ig-setup" id="setup">
<div class="ig-inner">
<div class="reveal">
<p class="tag">Setup</p>
<h2>Connect {e(short)} <em>in three steps</em></h2>
</div>
<ol class="ig-steps reveal">
{steps}
</ol>
<div class="ig-trust reveal">
<p>{icon('key-round')}<span>{e(p['permissions'])}</span></p>
<p>{icon('shield-check')}<span>{e(copy.CREDENTIALS)}</span></p>
</div>
</div>
</section>
"""
    out += faq_section(f"{e(short)}, <em>answered</em>", faq)
    out += BODY_CLOSE
    return i18n.with_hreflang(out, url_path)


# ---------------------------------------------------------------------------
# The hub
# ---------------------------------------------------------------------------

def hub_page(copy, by_id: dict) -> str:
    live = [c for c in copy.CONNECTORS if not c.get("soon")]
    soon = [c for c in copy.CONNECTORS if c.get("soon")]
    writers = [c for c in live if c["ops"]]
    op_count = sum(len(c["ops"]) for c in live)

    def card(c: dict) -> str:
        if c.get("soon"):
            chips = '<span class="ig-chip is-soon">Coming soon</span>'
        else:
            write = (f'<span class="ig-chip is-write">{len(c["ops"])} kinds of change</span>'
                     if c["ops"] else '<span class="ig-chip">Read-only</span>')
            chips = f'<span class="ig-chip">{e(c["auth"])}</span>{write}'
        classes = ["ig-card"] + [k for k, on in (("is-link", c.get("page")), ("is-soon", c.get("soon")),
                                                  ("is-featured", c.get("featured"))) if on]
        line = (f'<span class="ig-card-feature">{e(c["featured"])}</span>' if c.get("featured")
                else f'<span class="ig-card-line">{e(c["card"])}</span>')
        inner = (f'{logo(c, 36)}<span class="ig-card-body"><span class="ig-card-name">{e(c["name"])}</span>'
                 f'{line}<span class="ig-card-chips">{chips}</span></span>')
        if c.get("page"):
            return (f'<a class="{" ".join(classes)}" id="{c["slug"]}" href="{page_url(c)}">{inner}'
                    f'<span class="ig-card-go">{icon("arrow-right")}</span></a>')
        return f'<div class="{" ".join(classes)}" id="{c["slug"]}">{inner}</div>'

    sections = []
    for key, title in copy.GROUPS:
        members = sorted((c for c in copy.CONNECTORS if c["group"] == key), key=lambda c: not c.get("featured"))
        cards = "\n".join(card(c) for c in members)
        sections.append(f"""<section class="ig-group reveal" aria-labelledby="g-{key}">
<h2 class="ig-group-h" id="g-{key}">{e(title)}</h2>
<div class="ig-grid">
{cards}
</div>
</section>""")

    names = [c["name"] for c in live]
    oauth = sum(c["auth"].startswith("Sign in") for c in live)
    faq = [
        ("Which tools does Duct connect to?",
         f"{and_list(names)}. The {NUMBER_WORDS[oauth].lower()} Google tools connect when you sign "
         f"in with Google; the rest take a key you paste once. {and_list([c['name'] for c in soon])} is next."),
        ("Does Duct need write access to my accounts?",
         f"No. Answers and briefs work with read access everywhere. {NUMBER_WORDS[len(writers)]} connectors can also make changes "
         f"({and_list([c['short'] for c in writers])}), {op_count} kinds in all, and by default "
         "every one waits for your Apply."),
        ("Where are my connector credentials stored?", copy.CREDENTIALS),
        ("Can I ask for a connector?",
         f'Yes. Open a <a href="{DISCUSSIONS}" rel="noopener">discussion on GitHub</a> naming the tool and the question you want '
         "it to answer. Connectors get built when a question needs one."),
        ("Does Duct have an MCP server?",
         f'Not yet. An MCP server, so Claude, Cursor and other agents can use Duct\'s connectors, is planned in '
         f'<a href="{MCP_ISSUE}" rel="noopener">issue #197</a>.'),
    ]
    items = [{"@type": "ListItem", "position": i, "name": c["name"], "url": BASE_URL + link_for(c)}
             for i, c in enumerate(live, 1)]
    ld = [
        {"@context": "https://schema.org", "@type": "CollectionPage", "inLanguage": "en", "name": "Duct integrations",
         "url": BASE_URL + "/integrations/",
         "description": "The tools Duct reads and the changes it can make in them, generated from its source code.",
         "isPartOf": {"@type": "WebSite", "name": "Duct", "url": BASE_URL}},
        {"@context": "https://schema.org", "@type": "ItemList", "inLanguage": "en", "name": "Duct connectors",
         "numberOfItems": len(items), "itemListElement": items},
        breadcrumb_ld([("Home", "/"), ("Integrations", "/integrations/")]),
        faq_ld(faq),
    ]
    title = f"Integrations: Google Ads, GA4, Stripe and {len(live) - 3} more | Duct"
    description = (f"The {len(live)} tools Duct reads, from Google Ads and Meta to GA4, Mixpanel and Stripe, what each one "
                   "can change, and how you connect it. Read-only by default.")
    stats = [(str(len(live)), "connectors"), (str(len(writers)), "can make changes"),
             (str(op_count), "kinds of change"), ("0", "changes without your Apply, by default")]
    stat_html = "".join(f"<li><b>{n}</b><span>{e(t)}</span></li>" for n, t in stats)
    marquee = "".join(logo(c, 30) for c in live)
    out = head(title=title, description=description, url_path="/integrations/",
               og_title=f"Duct integrations: {NUMBER_WORDS[len(live)].lower()} tools, read as one",
               og_description="Ads, analytics, product and revenue, joined for one question. What each connector reads and what it can change.",
               twitter_description=f"{NUMBER_WORDS[len(live)]} connectors, read-only by default. Every change waits for your Apply.",
               og_image="integrations.jpg", ld=ld)
    out += body_open("The hub is for the evaluator's first question, does it connect to my tool, and for the "
                     "internal links every connector page needs. Hypothesis: counts read from the code (connectors, "
                     "changes, zero self-applied) convert better than logos alone. Measured by clicks through to a "
                     "connector page and download clicks per visit.")
    out += f"""
<!-- HERO -->
<section class="hero ig-hub-hero">
<div class="hero-pill"><span class="hero-pill-dot" aria-hidden="true"></span> Generated from Duct's source code</div>
<h1>{NUMBER_WORDS[len(live)]} tools. <em>Read as one.</em></h1>
<p class="hero-sub">Ads, analytics, product and revenue, joined for one question. Read-only by default, and every change waits for your Apply.</p>
<div class="ig-logos" aria-hidden="true">{marquee}</div>
<ul class="ig-stats">{stat_html}</ul>
</section>

<!-- CONNECTORS: one card per connector, grouped -->
<div class="ig-hub">
{chr(10).join(sections)}

<aside class="ig-ask reveal">
<div>
<h2>Missing <em>yours?</em></h2>
<p>Name the tool and the question you want it to answer. Connectors get built when a question needs one.</p>
</div>
<a class="btn btn-dark" href="{DISCUSSIONS}" rel="noopener">Ask on GitHub {icon('arrow-right')}</a>
</aside>
</div>
"""
    out += faq_section("Connectors, <em>answered</em>", faq)
    out += BODY_CLOSE
    return i18n.with_hreflang(out, "/integrations/")


# ---------------------------------------------------------------------------

#: Hand-kept listings every page must appear in, as with the blog's posts: a
#: page nobody links from the sitemap or llms.txt is a page nobody finds.
LISTINGS = (SITE / "sitemap.xml", SITE / "llms.txt")


def render() -> dict[Path, str]:
    copy, by_id = build_model()
    pages = {OUT / "index.html": hub_page(copy, by_id)}
    urls = [BASE_URL + "/integrations/"]
    for c in copy.CONNECTORS:
        if c.get("page"):
            og = SITE / "assets/og" / f"integrations-{c['slug']}.jpg"
            if not og.is_file():
                raise BuildError(f"{og.relative_to(ROOT)} is missing: add the page to scripts/build_og_images.mjs and run it")
            pages[OUT / f"{c['slug']}.html"] = connector_page(c, copy, by_id)
            urls.append(BASE_URL + page_url(c))
    missing = [f"{url} is not in {path.relative_to(ROOT)}" for path in LISTINGS
               for url in urls if url not in path.read_text(encoding="utf-8")]
    if missing:
        raise BuildError("\n".join(missing))
    return pages


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if a generated page is stale or missing")
    args = ap.parse_args()
    try:
        pages = render()
    except BuildError as exc:
        print(exc, file=sys.stderr)
        return 1
    extra = sorted(p for p in OUT.glob("*.html") if p not in pages) if OUT.exists() else []
    if args.check:
        stale = [p for p, text in pages.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        for p in stale:
            print(f"stale: {p.relative_to(ROOT)} (run scripts/build_integrations.py)", file=sys.stderr)
        for p in extra:
            print(f"not generated by anything: {p.relative_to(ROOT)}", file=sys.stderr)
        if stale or extra:
            return 1
        print(f"integrations: {len(pages)} pages current")
        return 0
    OUT.mkdir(exist_ok=True)
    for p, text in pages.items():
        p.write_text(text, encoding="utf-8")
    for p in extra:
        p.unlink()
    print(f"wrote {len(pages)} pages to {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
