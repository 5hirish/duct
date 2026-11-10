#!/usr/bin/env python3
"""Post each new changelog entry as a GitHub Discussion in Announcements.

Why this exists: an entry on getduct.ai/changelog reaches people who already
visit the site. A Discussion in Announcements reaches everyone watching the
repository, lands in their GitHub notifications, and gives each release a
thread to answer in. Writing it by hand after every merge was a step nobody
took: the first changelog entries shipped with no announcement at all.

The source is `site/changelog/feed.xml`, not the HTML: the feed is already one
structured item per entry (title, link, guid, date, a one-paragraph summary),
written by the `add-changelog-entry` skill in the same change as the page.

    python3 .github/scripts/announce_changelog.py --before <sha>    # what CI runs
    python3 .github/scripts/announce_changelog.py --guid duct-changelog-2026-11-05
    python3 .github/scripts/announce_changelog.py --before <sha> --dry-run

A new entry is an item whose guid is in the feed at HEAD and not in the feed
at `--before`. Each post carries its guid in a hidden marker, and an entry
whose marker is already in Announcements is skipped, so a re-run, a revert
and re-merge, or a manual `--guid` for an entry CI already posted never
announces the same release twice.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
# The stdlib parser on purpose: the only input is the feed on this repository's
# own main branch, written by the changelog skill, so there is no untrusted XML
# to defend against and no reason to add a dependency to a five-minute job.
import xml.etree.ElementTree as ET  # nosec B405
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED = "site/changelog/feed.xml"
CATEGORY = "Announcements"
API = "https://api.github.com/graphql"
MARKER = "<!-- duct-changelog:{guid} -->"
#: How many recent Announcements to read when checking for a duplicate. Far
#: more than entries ever merge between two runs.
RECENT = 50


def feed_items(xml_text: str) -> list[dict[str, str]]:
    """Every item in a feed, newest first, as the fields a post needs."""
    if not xml_text.strip():
        return []
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        def field(name: str) -> str:
            el = item.find(name)
            return (el.text or "").strip() if el is not None else ""
        items.append({
            "title": field("title"),
            "link": field("link"),
            "guid": field("guid"),
            "date": field("pubDate"),
            "description": field("description"),
        })
    return items


def feed_at(rev: str) -> str:
    """The feed as it stood at a revision, or "" where it did not exist."""
    try:
        return subprocess.run(["git", "show", f"{rev}:{FEED}"], check=True,
                              capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        return ""


def new_items(before: str, after_text: str) -> list[dict[str, str]]:
    old = {i["guid"] for i in feed_items(feed_at(before))} if before else set()
    # Oldest first, so two entries merged together post in the order they shipped.
    return [i for i in reversed(feed_items(after_text)) if i["guid"] and i["guid"] not in old]


def body_for(item: dict[str, str]) -> str:
    try:
        day = parsedate_to_datetime(item["date"]).strftime("%-d %B %Y")
    except (TypeError, ValueError):
        day = item["date"]
    return "\n".join([
        item["description"],
        "",
        f"**[Read the full entry on the changelog]({item['link']})** · shipped {day}",
        "",
        "Questions, bugs or something you would like next? Reply here. "
        "If Duct saved you some time this release, a ⭐ on the repository helps other people find it.",
        "",
        MARKER.format(guid=item["guid"]),
    ])


def graphql(query: str, variables: dict, token: str) -> dict:
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise SystemExit(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]


def repo_state(owner: str, name: str, token: str) -> tuple[str, str, str]:
    """Repository id, the Announcements category id, and its recent bodies joined."""
    data = graphql(
        """query($owner: String!, $name: String!, $n: Int!) {
             repository(owner: $owner, name: $name) {
               id
               discussionCategories(first: 25) { nodes { id name } }
               discussions(first: $n, orderBy: {field: CREATED_AT, direction: DESC}) {
                 nodes { body category { name } }
               }
             }
           }""",
        {"owner": owner, "name": name, "n": RECENT},
        token,
    )["repository"]
    category = next((c["id"] for c in data["discussionCategories"]["nodes"] if c["name"] == CATEGORY), None)
    if not category:
        raise SystemExit(f"no '{CATEGORY}' discussion category in {owner}/{name}")
    posted = "\n".join(d["body"] for d in data["discussions"]["nodes"] if d["category"]["name"] == CATEGORY)
    return data["id"], category, posted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--before", default="", help="the revision the push started from")
    ap.add_argument("--guid", default="", help="announce this one entry, wherever it sits in the feed")
    ap.add_argument("--dry-run", action="store_true", help="print what would be posted; post nothing")
    args = ap.parse_args()

    feed = Path(FEED).read_text()
    if args.guid:
        items = [i for i in feed_items(feed) if i["guid"] == args.guid]
        if not items:
            raise SystemExit(f"{args.guid} is not in {FEED}")
    else:
        items = new_items(args.before, feed)
    if not items:
        print("no new changelog entries")
        return 0

    if args.dry_run:
        for item in items:
            print(f"--- would post: {item['title']}\n{body_for(item)}\n")
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    owner, _, name = os.environ.get("GITHUB_REPOSITORY", "5hirish/duct").partition("/")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set")
    repo_id, category_id, posted = repo_state(owner, name, token)

    for item in items:
        if MARKER.format(guid=item["guid"]) in posted:
            print(f"already announced: {item['title']}")
            continue
        created = graphql(
            """mutation($repo: ID!, $cat: ID!, $title: String!, $body: String!) {
                 createDiscussion(input: {repositoryId: $repo, categoryId: $cat, title: $title, body: $body}) {
                   discussion { url }
                 }
               }""",
            {"repo": repo_id, "cat": category_id, "title": item["title"], "body": body_for(item)},
            token,
        )
        print(f"announced: {item['title']} → {created['createDiscussion']['discussion']['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
