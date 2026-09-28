#!/usr/bin/env python3
"""Demand signals for a blog topic, from free sources, in one Markdown report.

The paid keyword tools are not on our plan (the Ahrefs connector answers
"Insufficient plan" on every endpoint), and search volume was never the signal
that mattered most for answer engines anyway. What a post needs to know before
it is written is how people *phrase* the question, which pages the community
already treats as the reference, and what is being argued about. Three free
sources answer that:

  Google autocomplete   the phrasings, comparisons ("x vs y") and question forms
  Hacker News (Algolia) what builders upvoted and argued about, with links
  GitHub                the repositories the topic orbits, by stars

Reddit is not here: its JSON search answers 403 to an unauthenticated client.
Search it through the agent's web search (`site:reddit.com <topic>`) instead.

Usage (network; in the agent sandbox pass these hosts as allowed domains):

    python3 .agents/skills/add-blog-post/research.py "harness engineering"
    python3 .agents/skills/add-blog-post/research.py "agent memory" --also "agent memory staleness"

Hosts: suggestqueries.google.com, hn.algolia.com, api.github.com.
A source that fails is reported and skipped; the rest of the report still prints.
"""

from __future__ import annotations

import argparse
import http.client
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

USER_AGENT = "duct-blog-research/1.0 (+https://getduct.ai)"
TIMEOUT = 15
ONE_YEAR = 365 * 24 * 3600

# Autocomplete is prefix completion, so each form below surfaces a different
# slice of how people ask: definitions, how-tos, comparisons, audiences.
PREFIXES = ("what is {q}", "how to {q}", "why {q}", "is {q}")
SUFFIXES = ("{q}", "{q} vs", "{q} for", "{q} example", "{q} best practices",
            "{q} github", "{q} reddit", "{q} tools")
QUESTION_WORDS = ("what", "how", "why", "when", "which", "is", "are", "can", "does", "should")


def fetch_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
    except http.client.IncompleteRead:
        # Behind the agent sandbox's proxy, urllib's read of a large body is
        # cut short (GitHub's 60 KB search result) while curl's is not.
        body = subprocess.run(["curl", "-sfL", "--max-time", str(TIMEOUT), "-A", USER_AGENT, url],
                              check=True, capture_output=True).stdout
    return json.loads(body.decode("utf-8", "replace"))


def autocomplete(q: str) -> list[str]:
    url = "https://suggestqueries.google.com/complete/search?client=firefox&q=" + urllib.parse.quote(q)
    data = fetch_json(url)
    return list(data[1]) if isinstance(data, list) and len(data) > 1 else []


def section_autocomplete(seed: str) -> str:
    seen: dict[str, None] = {}
    for form in SUFFIXES + PREFIXES:
        for s in autocomplete(form.format(q=seed)):
            seen.setdefault(s.strip().lower())
        time.sleep(0.2)  # be a polite client; this is an unauthenticated endpoint
    phrasings = [s for s in seen if s != seed.lower()]
    questions = [s for s in phrasings if s.split(" ", 1)[0] in QUESTION_WORDS]
    comparisons = [s for s in phrasings if " vs" in s or " versus " in s]
    rest = [s for s in phrasings if s not in questions and s not in comparisons]
    out = [f"### Autocomplete for “{seed}”", ""]
    for title, items in (("Questions (candidate H2s and FAQ)", questions),
                         ("Comparisons (a table or an H2 each)", comparisons),
                         ("Other phrasings (secondary keywords)", rest)):
        out.append(f"**{title}:** " + ("; ".join(items) if items else "none"))
        out.append("")
    return "\n".join(out)


def section_hn(seed: str) -> str:
    since = int(time.time()) - ONE_YEAR
    url = ("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=12"
           f"&numericFilters=created_at_i>{since}&query=" + urllib.parse.quote(seed))
    hits = sorted(fetch_json(url)["hits"], key=lambda h: h.get("points") or 0, reverse=True)
    rows = [f"- {h.get('points', 0)} pts, {h.get('num_comments', 0)} comments, {h['created_at'][:10]}: "
            f"[{h['title']}]({h.get('url') or ''}) · [thread](https://news.ycombinator.com/item?id={h['objectID']})"
            for h in hits]
    return "### Hacker News, last 12 months\n\n" + ("\n".join(rows) or "nothing") + "\n"


def section_github(seed: str) -> str:
    url = ("https://api.github.com/search/repositories?sort=stars&order=desc&per_page=10&q="
           + urllib.parse.quote(seed))
    repos = fetch_json(url)["items"]
    rows = [f"- {r['stargazers_count']:,}★ [{r['full_name']}]({r['html_url']}), pushed {r['pushed_at'][:10]}: "
            f"{(r.get('description') or '').strip()}" for r in repos]
    return "### GitHub repositories\n\n" + ("\n".join(rows) or "nothing") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("seed", help="the topic, as a reader would type it")
    parser.add_argument("--also", action="append", default=[], help="another phrasing to expand")
    args = parser.parse_args()

    print(f"# Research signals: {args.seed}\n")
    print(f"Pulled {time.strftime('%Y-%m-%d')}. Free sources only; volumes are not estimated.\n")
    sections = [(section_autocomplete, s) for s in [args.seed, *args.also]]
    sections += [(section_hn, args.seed), (section_github, args.seed)]
    for fn, seed in sections:
        try:
            print(fn(seed))
        except Exception as exc:  # one dead source must not sink the report
            print(f"### {fn.__name__.removeprefix('section_')}: unavailable ({exc.__class__.__name__}: {exc})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
