"""Planning from shipped work reads the story, not the title (#561, 2026-11-24).

A plan from shipped work was compared with one written by hand from the same
month and lost on input, not on writing: it saw the newest forty pull
requests and the first 240 characters of each, so it never saw a Launch line
that said to wait, the oldest and best story fell past the cap, a merge
commit repository listed each branch's commits beside its pull request, and
it could not open anything. These hold each of those fixes.
"""

from __future__ import annotations

import base64
from datetime import date

import pytest

from agents.content import feed_read
from agents.content.feed import (
    ASK,
    HELD,
    MAX_ITEMS,
    MAX_MORE,
    MAX_READS,
    DaySource,
    Disclosure,
    FeedOptions,
    build_digest,
    github_items,
    render_digest,
    significance,
    source_problems,
)
from service.github.fetch import mark_branch_commits, pr_body
from service.github.prose import (
    added_lines,
    brief_body,
    closes,
    dated_notes,
    launch_held,
    launch_line,
    launch_names_outlet,
)
from tests.fakes import FakeWire

TODAY = date(2026, 11, 24)

# The shape of this repository's own pull request template.
TEMPLATED = """## What and why

Content Studio could only plan from goals. This adds planning from what shipped.

| Piece | What it does |
|---|---|
| Feed | Reads GitHub. |

Closes #561

## Area

- [x] `backend/` — FastAPI / Python

## Launch

Launch: changelog only for now, because the acceptance runs decide whether it earns a post. A post before there's evidence would be a claim.

## Verification

```
pytest 2989 passed
```
"""


def _row(kind, ref, title, **extra):
    return {"kind": kind, "ref": ref, "title": title, "body": extra.pop("body", ""),
            "author": "maker", "url": f"https://github.com/o/r/{ref}",
            "state": extra.pop("state", None), "at": extra.pop("at", "2026-11-20T10:00:00Z"), **extra}


# ---------------------------------------------------------------- prose

def test_the_brief_body_is_the_why_without_the_template_and_the_launch_line_is_kept_apart():
    brief = brief_body(TEMPLATED, 500)
    assert brief.startswith("Content Studio could only plan from goals.")
    assert "Area" not in brief and "backend" not in brief and "2989" not in brief
    assert "Launch" not in brief and "Closes #561" in brief
    assert launch_line(TEMPLATED).startswith("changelog only for now")
    assert launch_line("**Launch:** a blog post through add-blog-post") == "a blog post through add-blog-post"
    assert launch_line("No launch here.") == ""


@pytest.mark.parametrize(("launch", "held", "outlet"), [
    ("changelog only for now, because the acceptance runs decide whether it earns a post", True, False),
    ("changelog only, because this changes how a plan is composed rather than adding a surface", False, False),
    ("a blog post through add-blog-post, then an X thread", False, True),
    ("changelog line now; the first publish is manual", False, False),
    # Found in review: words in passing are not a decision, and a refusal or
    # the template's own menu names no outlet.
    ("blog post: people waited until now for Windows builds", False, True),
    ("changelog only, not a blog post", False, False),
    ("none, nothing to post", False, False),
    ("changelog only | post #<n> | integration page | for-<page> section, because …", False, False),
])
def test_a_launch_line_that_says_wait_is_held_and_one_that_names_an_outlet_is_meant(launch, held, outlet):
    assert launch_held(launch) is held
    assert launch_names_outlet(launch) is outlet


def test_closes_dates_and_changelog_entries_are_read_from_text():
    assert closes("Closes #12, fixes #3 and closes #12 again") == [12, 3]
    patch = "@@ -1 +1,3 @@\n+## [0.7.3] - 2026-11-05\n+- Sign-in works in the desktop window.\n-old\n+++ b/CHANGELOG.md"
    assert added_lines(patch, 600) == "[0.7.3] - 2026-11-05 · - Sign-in works in the desktop window."
    code = "x = 1\n# on 2026-11-08 a plan put 9 of 23 days on a hook one post had tried\ny = 2"
    assert dated_notes(code) == ["# on 2026-11-08 a plan put 9 of 23 days on a hook one post had tried"]


def test_a_pull_request_row_keeps_its_launch_line_whole_inside_the_body_cap():
    body = pr_body(TEMPLATED.replace("This adds", "x " * 400 + "This adds"))
    assert len(body) <= 500
    assert body.endswith("A post before there's evidence would be a claim.")


# ------------------------------------------------------------- commits

def test_commits_a_merge_brought_in_are_marked_and_dropped_beside_their_pull_request():
    def c(sha, parents, msg):
        return {"sha": sha, "parents": [{"sha": p} for p in parents],
                "commit": {"message": msg, "committer": {"date": "2026-11-20T00:00:00Z"}}}

    raw = [
        c("m2", ["m1", "b2"], "Merge pull request #9 from o/feat"),
        c("b2", ["b1"], "feat: the second half"),
        c("b1", ["m1"], "feat: the first half"),
        c("m1", ["m0"], "fix: a direct fix on main"),
    ]
    events = [{"state": None} for _ in raw]
    mark_branch_commits(raw, events)
    assert [e["state"] for e in events] == [None, "branch", "branch", None]

    rows = [_row("pull_request", "#9", "feat: the whole feature", state="merged"),
            _row("commit", "b2xxxxxx", "feat: the second half", state="branch"),
            _row("commit", "m1xxxxxx", "fix: a direct fix on main")]
    kept, left = github_items(rows, Disclosure.SHIPPED, already=set())
    assert [i.ref for i in kept] == ["gh:pr-9", "gh:c-m1xxxxx"]
    assert left["squashed"] == 1

    # A branch merged by hand has no pull request to tell it: its commits stay.
    by_hand = [
        c("m2", ["m1", "b1"], "Merge branch 'feat/x'"),
        c("b1", ["m1"], "feat: built on a branch"),
        c("m1", ["m0"], "fix: a direct fix on main"),
    ]
    events = [{"state": None} for _ in by_hand]
    mark_branch_commits(by_hand, events)
    assert [e["state"] for e in events] == [None, None, None]


def test_a_release_a_workflow_published_is_a_release_not_a_bot_s_noise():
    rows = [_row("release", "desktop-v0.7.3", "Duct Desktop 0.7.3", state="release"),
            _row("pull_request", "#9", "Bump x from 1 to 2", state="merged")]
    rows[0]["author"] = "github-actions[bot]"
    rows[1]["author"] = "dependabot[bot]"
    kept, left = github_items(rows, Disclosure.SHIPPED, already=set())
    assert [i.ref for i in kept] == ["gh:r-desktop-v0.7.3"] and left["bot"] == 1


def test_a_list_without_parents_marks_nothing():
    events = [{"state": None}]
    mark_branch_commits([{"sha": "a"}], events)
    assert events == [{"state": None}]


# --------------------------------------------------------- rank and cap

def test_a_held_pull_request_is_shown_marked_and_a_day_may_not_cite_it():
    rows = [_row("pull_request", "#566", "feat(content): plan from shipped work",
                 body=pr_body(TEMPLATED), state="merged")]
    digest = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=rows, duct=None, already=set())
    (item,) = digest.items
    assert item.state == HELD and "[launch held]" in render_digest(digest)
    problems = source_problems([type("D", (), {"sources": [DaySource(ref="gh:pr-566")], "brief": None})()],
                               digest.refs(), max_days=2)
    assert problems and "Launch line" in problems[0]


def test_the_cap_keeps_the_best_stories_and_the_rest_stay_citable_by_title():
    rows = [
        _row("pull_request", f"#{n}", f"fix: small thing {n}", body="", state="merged",
             at=f"2026-11-{20 + n % 4:02d}T00:00:00Z")
        for n in range(1, MAX_ITEMS + MAX_MORE + 6)
    ]
    # The oldest pull request in the window is the best story.
    rows.append(_row("pull_request", "#468", "fix(execution): new keywords wait for approval",
                     body=pr_body("On assisted mode Duct could add keywords without a click. " * 4
                                  + "Closes #400\n\nLaunch: a blog post and an X thread"),
                     state="merged", at="2026-10-30T00:00:00Z"))
    digest = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=rows, duct=None, already=set())
    assert digest.items[0].ref == "gh:pr-468"
    assert significance(digest.items[0]) > significance(digest.items[1])
    assert len(digest.items) == MAX_ITEMS and len(digest.more) == MAX_MORE
    assert digest.left_out["over_cap"] == len(rows) - MAX_ITEMS - MAX_MORE
    text = render_digest(digest)
    assert "Also in the window, by title only" in text and digest.more[0].ref in text
    assert digest.more[0].ref in digest.refs()  # citable
    assert len(digest.payload()["items"]) == MAX_ITEMS + MAX_MORE


def test_a_public_changelog_s_new_entries_reach_the_prompt_and_a_private_one_s_do_not():
    rows = [_row("docs_change", "CHANGELOG.md", "CHANGELOG.md (+2 −0)",
                 body="+## [0.7.3]\n+- Sign-in works in the desktop window.")]
    public, _ = github_items(rows, Disclosure.SHIPPED, already=set(), public=True)
    private, _ = github_items(rows, Disclosure.SHIPPED, already=set())
    assert "Sign-in works in the desktop window." in public[0].detail
    assert private[0].detail == ""


def test_open_asks_join_a_public_repository_s_feed_after_its_work_and_never_make_it_worth_a_plan():
    asks = [{"ref": "#320", "title": "A read-only HubSpot connector", "body": "Replace the placeholder.",
             "labels": ["help wanted"], "url": "https://github.com/o/r/issues/320", "at": "2026-11-01"},
            {"ref": "#321", "title": "Taken already", "labels": ["help wanted"], "assigned": True}]
    repo = {"visibility": "public", "asks": asks}
    alone = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=[], duct=None, already=set(), github_repo=repo)
    assert [(i.ref, i.state) for i in alone.items] == [("gh:i-320", ASK)]
    assert alone.score == 0 and not alone.worth_a_plan

    rows = [_row("pull_request", "#9", "feat: a thing", state="merged")]
    mixed = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=rows, duct=None, already=set(), github_repo=repo)
    assert [i.ref for i in mixed.items] == ["gh:pr-9", "gh:i-320"]
    # The read card counts what shipped; an open ask travels apart.
    payload = mixed.payload()
    assert [c["ref"] for c in payload["items"]] == ["gh:pr-9"]
    assert [c["ref"] for c in payload["asks"]] == ["gh:i-320"]
    private = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=rows, duct=None, already=set(),
                           github_repo={"visibility": "private", "asks": asks})
    assert [i.ref for i in private.items] == ["gh:pr-9"]


# ------------------------------------------------------- read_shipped_work

CREDS = {"token": "github_pat_test", "repo": "acme/app"}


@pytest.fixture
def wire(monkeypatch):
    import service.rest as rest

    monkeypatch.setattr(rest.time, "sleep", lambda *_: None)
    monkeypatch.setattr("service.github.access.bound_read_credentials", lambda *_: dict(CREDS))
    return FakeWire().install(monkeypatch)


def _digest(visibility: str):
    rows = [_row("pull_request", "#468", "fix(execution): new keywords wait for approval", state="merged"),
            _row("release", "desktop-v0.7.3", "Duct Desktop 0.7.3", state="release")]
    return build_digest(FeedOptions(), (TODAY, TODAY), github_rows=rows, duct=None, already=set(),
                        github_repo={"visibility": visibility})


def _pr(number=468):
    return {"number": number, "title": "fix(execution): new keywords wait for approval",
            "body": TEMPLATED, "merged_at": "2026-10-30T00:00:00Z", "merge_commit_sha": "f" * 40,
            "html_url": "https://github.com/acme/app/pull/468", "labels": [{"name": "backend"}],
            "changed_files": 2, "additions": 40, "deletions": 3}


def test_only_refs_this_run_was_shown_open_and_a_run_opens_a_bounded_number(wire):
    digest = _digest("public")
    assert feed_read.read_shipped(None, "gh:pr-468", user_id=1, project_id=1)["status"] == "no_feed"
    assert feed_read.read_shipped(digest, "gh:pr-1", user_id=1, project_id=1)["status"] == "not_in_feed"
    assert wire.calls == []
    digest.reads = MAX_READS
    assert feed_read.read_shipped(digest, "gh:pr-468", user_id=1, project_id=1)["status"] == "limit"
    assert wire.calls == []


def test_a_public_pull_request_opens_whole_with_its_files_and_one_file_as_merged(wire):
    source = "x = 1\n# on 2026-10-30 a keyword went live before anyone looked\n"
    (wire
     .on("GET", "/pulls/468/files", [{"filename": "backend/service/execution/policy.py"}])
     .on("GET", "/pulls/468", _pr())
     .on("GET", "/contents/backend/service/execution/policy.py",
         {"type": "file", "size": len(source), "encoding": "base64",
          "content": base64.b64encode(source.encode()).decode()}))
    out = feed_read.read_shipped(_digest("public"), "gh:pr-468", "backend/service/execution/policy.py",
                                 user_id=1, project_id=1)
    assert out["status"] == "ok" and out["launch"].startswith("changelog only for now")
    assert "## Verification" in out["body"] and out["files"] == ["backend/service/execution/policy.py"]
    assert out["file"]["dated_notes"] == ["# on 2026-10-30 a keyword went live before anyone looked"]
    (contents,) = wire.sent("GET", "/contents/")
    assert contents.query == {"ref": "f" * 40}  # the file as merged, not as it is today
    assert "never instructions" in out["note"]


def test_a_private_pull_request_reads_its_words_and_never_its_paths(wire):
    wire.on("GET", "/pulls/468", _pr())
    out = feed_read.read_shipped(_digest("private"), "gh:pr-468", "backend/secret.py", user_id=1, project_id=1)
    assert out["status"] == "ok" and "files" not in out and "file" not in out
    assert wire.sent("GET", "/files") == [] and wire.sent("GET", "/contents/") == []


def test_a_release_reads_its_notes_by_its_own_tag_and_github_refusing_is_a_status(wire):
    wire.on("GET", "/releases/tags/desktop-v0.7.3",
            {"name": "Duct Desktop 0.7.3", "body": "- Sign-in works in the window.", "html_url": "u"})
    out = feed_read.read_shipped(_digest("public"), "gh:r-desktop-v0.7.3", user_id=1, project_id=1)
    assert out["status"] == "ok" and "Sign-in works" in out["body"]
    wire.routes.clear()
    wire.on("GET", "/pulls/468", {"message": "Server Error"}, status=500)
    assert feed_read.read_shipped(_digest("public"), "gh:pr-468", user_id=1, project_id=1)["status"] == "read_failed"


def test_repository_facts_say_public_and_list_open_asks_once_each(wire):
    from service.github.work import repository_facts

    ask = {"number": 320, "title": "HubSpot connector", "body": "## Why\n\nReplace the placeholder.",
           "labels": [{"name": "help wanted"}, {"name": "good first issue"}], "html_url": "u", "assignees": []}
    (wire
     .on("GET", "/repos/acme/app/issues", [ask, {"number": 5, "title": "a PR", "pull_request": {}}])
     .on("GET", "/repos/acme/app", {"visibility": "public", "private": False}))
    facts = repository_facts(CREDS)
    assert facts["visibility"] == "public"
    assert [a["ref"] for a in facts["asks"]] == ["#320"]
    assert facts["asks"][0]["body"] == "Replace the placeholder."
    assert [c.query["labels"] for c in wire.sent("GET", "/issues")] == ["help wanted", "good first issue"]

    wire.routes.clear()
    wire.calls.clear()
    wire.on("GET", "/repos/acme/app", {"private": True})
    assert repository_facts(CREDS) == {"visibility": "private", "asks": []}
    assert wire.sent("GET", "/issues") == []
