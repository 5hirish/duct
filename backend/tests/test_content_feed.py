"""Planning from shipped work (#561): what a feed run keeps, what it leaves
out and why, and when it is not worth a model call."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agents.content.feed import (
    GATE_SCORE,
    DaySource,
    Disclosure,
    FeedItem,
    FeedOptions,
    FeedSource,
    build_digest,
    conventional_type,
    duct_items,
    feed_window,
    github_items,
    planned_refs,
    render_digest,
    resolve_sources,
    source_problems,
)

TODAY = date(2026, 11, 11)


def _row(kind: str, ref: str, title: str, **extra) -> dict:
    return {"kind": kind, "ref": ref, "title": title, "body": extra.pop("body", ""),
            "author": extra.pop("author", "maker"), "url": f"https://github.com/o/r/{ref}",
            "state": extra.pop("state", None), "at": extra.pop("at", "2026-11-10T10:00:00Z"), **extra}


ROWS = [
    _row("release", "v1.4.0", "v1.4.0", state="release", body="Faster onboarding."),
    _row("pull_request", "#412", "feat(onboarding): retry the GA4 handshake", state="merged"),
    _row("pull_request", "#413", "chore(ci): cache poetry", state="merged"),
    _row("pull_request", "#414", "Bump httpx from 0.27 to 0.28", author="dependabot[bot]", state="merged"),
    _row("commit", "abc1234def", "feat(onboarding): retry the GA4 handshake (#412)"),
    _row("commit", "bbb2222aaa", "fix: drafts keep their hook on resume"),
    _row("commit", "ccc3333bbb", "Merge pull request #412 from o/feat"),
    _row("commit", "ddd4444ccc", "Update react from 18.2.0 to 18.3.1"),
    _row("issue", "#90", "Onboarding drops GA4", state="completed"),
    _row("docs_change", "README.md", "README.md (+4 −1)", body="+ secret patch text"),
    _row("docs_change", "docs/engineering/plan.md", "docs/engineering/plan.md (+40 −0)", body="+ internal"),
]


def test_shipped_keeps_what_a_user_got_and_says_why_the_rest_went():
    kept, left = github_items(ROWS, Disclosure.SHIPPED, already=set())
    assert [i.ref for i in kept] == ["gh:r-v1.4.0", "gh:pr-412", "gh:c-bbb2222", "gh:doc-README.md"]
    assert left == {"chore": 1, "bot": 1, "squashed": 2, "dependency": 1, "issue": 1, "internal_docs": 1}


def test_a_docs_patch_never_reaches_the_prompt():
    kept, _ = github_items(ROWS, Disclosure.EVERYTHING, already=set())
    docs = [i for i in kept if i.kind == "docs_change"]
    assert {i.ref for i in docs} == {"gh:doc-README.md", "gh:doc-docs/engineering/plan.md"}
    assert all(i.detail == "" for i in docs)
    assert "patch" not in render_digest(build_digest(
        FeedOptions(disclosure=Disclosure.EVERYTHING), (TODAY, TODAY),
        github_rows=ROWS, duct=None, already=set(),
    ))


def test_everything_adds_completed_issues_and_releases_only_keeps_releases():
    kept, _ = github_items(ROWS, Disclosure.EVERYTHING, already=set())
    assert "gh:i-90" in {i.ref for i in kept}
    kept, left = github_items(ROWS, Disclosure.RELEASES, already=set())
    assert [i.ref for i in kept] == ["gh:r-v1.4.0"]
    assert left["disclosure"] == len(ROWS) - 1


def test_a_story_already_on_a_plan_is_not_offered_again():
    plans = [SimpleNamespace(days=[{"topic": "t", "sources": [{"ref": "gh:pr-412"}]}, {"topic": "u"}])]
    already = planned_refs(plans)
    kept, left = github_items(ROWS, Disclosure.SHIPPED, already=already)
    assert "gh:pr-412" not in {i.ref for i in kept}
    assert left["already_planned"] == 1


def test_untyped_work_is_kept_and_typed_noise_is_not():
    assert conventional_type("feat(app)!: new board") == "feat"
    assert conventional_type("Ship the new board") == ""
    kept, _ = github_items([_row("commit", "e" * 10, "Ship the new board")], Disclosure.SHIPPED, already=set())
    assert len(kept) == 1


def test_the_window_starts_where_the_last_feed_plan_ended():
    plans = [SimpleNamespace(strategy={"feed": {"window_to": "2026-11-04"}}),
             SimpleNamespace(strategy={"mix": {}})]
    assert feed_window(FeedOptions(), plans, today=TODAY) == (date(2026, 11, 5), TODAY)
    # The first time, a fixed look-back.
    assert feed_window(FeedOptions(), [], today=TODAY) == (TODAY - timedelta(days=13), TODAY)
    # A look-back the person picked wins.
    assert feed_window(FeedOptions(look_back_days=7), plans, today=TODAY) == (TODAY - timedelta(days=6), TODAY)
    # A window that ended months ago is held to the cap.
    old = [SimpleNamespace(strategy={"feed": {"window_to": "2026-01-01"}})]
    assert feed_window(FeedOptions(), old, today=TODAY)[0] == TODAY - timedelta(days=29)


def test_a_quiet_window_is_not_worth_a_model_call():
    quiet = [_row("commit", "f" * 10, "fix: typo in the footer")]
    digest = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=quiet, duct=[], already=set())
    assert digest.score < GATE_SCORE and not digest.worth_a_plan
    release = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=ROWS[:1], duct=[], already=set())
    assert release.worth_a_plan
    applied = FeedItem(ref="cs:3f2a9c1d", kind="change_set", title="Shift budget (google_ads, applied)")
    assert build_digest(FeedOptions(), (TODAY, TODAY), github_rows=None, duct=[applied], already=set()).worth_a_plan


def test_releases_and_applied_changes_lead_and_the_payload_has_no_bodies():
    applied = FeedItem(ref="cs:3f2a9c1d", kind="change_set", title="Shift budget", detail="private context")
    digest = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=ROWS, duct=[applied], already=set())
    assert [i.ref for i in digest.items][:2] == ["gh:r-v1.4.0", "cs:3f2a9c1d"]
    payload = digest.payload()
    assert set(payload["items"][0]) == {"ref", "kind", "title", "url"}
    assert payload["left_out"]["bot"] == 1 and payload["worth_a_plan"] is True
    assert digest.strategy()["window_to"] == TODAY.isoformat()


def _day(*refs: str):
    return SimpleNamespace(sources=[DaySource(ref=r) for r in refs])


def test_a_feed_day_must_cite_what_the_run_was_shown_and_stay_under_the_cap():
    known = {"gh:pr-412": FeedItem(ref="gh:pr-412", kind="pull_request", title="Retry the GA4 handshake",
                                   url="https://github.com/o/r/pull/412")}
    assert source_problems([_day("gh:pr-412"), _day()], known, max_days=2) == []
    problems = source_problems([_day("gh:pr-999"), _day("PR 412")], known, max_days=2)
    assert "gh:pr-999 is not in this run's feed" in problems[0]
    assert "is not a ref" in problems[1]
    over = source_problems([_day("gh:pr-412")] * 3, known, max_days=2)
    assert over and "at most 2" in over[-1]


def test_a_cited_source_takes_the_feed_s_title_and_link():
    known = {"gh:pr-412": FeedItem(ref="gh:pr-412", kind="pull_request", title="Retry the GA4 handshake",
                                   url="https://github.com/o/r/pull/412")}
    day = SimpleNamespace(sources=[DaySource(ref="gh:pr-412", title="whatever the model said")])
    resolve_sources([day], known)
    assert day.sources[0].title == "Retry the GA4 handshake"
    assert day.sources[0].url.endswith("/412")


def test_options_refuse_an_empty_source_list_and_a_runaway_cap():
    with pytest.raises(ValueError):
        FeedOptions(sources=[])
    with pytest.raises(ValueError):
        FeedOptions(max_days=12)
    assert FeedOptions().sources == [FeedSource.GITHUB, FeedSource.DUCT]


# ---------------------------------------------------------------------------
# Duct's own record
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    from sqlmodel import Session

    from tests.conftest import make_sqlite_engine

    with Session(make_sqlite_engine()) as session:
        yield session


def test_duct_s_record_reads_briefs_landed_changes_and_shared_memory_only(db):
    from models.artifact import Artifact
    from models.execution import ExecutionChangeSet
    from models.memory import ProjectMemory
    from models.project import Project
    from models.auth import User

    owner = User(email="o@example.com")
    db.add(owner)
    db.commit()
    project = Project(user_id=owner.id, name="Acme")
    db.add(project)
    db.commit()
    when = datetime(2026, 11, 10, 9, tzinfo=timezone.utc)
    group = uuid4()
    db.add_all([
        Artifact(project_id=project.id, user_id=owner.id, agent_type="insights", kind="report",
                 title="Organic signups up 18%", slug="weekly-brief", group_id=group, version=1,
                 content_type="text/markdown", created_at=when),
        Artifact(project_id=project.id, user_id=owner.id, agent_type="insights", kind="report",
                 title="Organic signups up 18%", slug="weekly-brief", group_id=group, version=2,
                 content_type="text/markdown", created_at=when + timedelta(hours=1)),
        Artifact(project_id=project.id, user_id=owner.id, agent_type="tiktok_studio", kind="image",
                 title="slide", slug="slide", group_id=uuid4(), version=1, content_type="image/png",
                 created_at=when),
        ExecutionChangeSet(project_id=project.id, user_id=owner.id, connector_type="google_ads",
                           title="Shift budget to brand", status="applied", updated_at=when),
        ExecutionChangeSet(project_id=project.id, user_id=owner.id, connector_type="google_ads",
                           title="Pause campaign", status="proposed", updated_at=when),
        ProjectMemory(project_id=project.id, kind="outcome", title="Brand budget shift: +12% clicks",
                      recorded_at=when),
        # A teammate's private note bound to this project is not a source.
        ProjectMemory(project_id=project.id, scope="user", user_id=owner.id, kind="outcome",
                      title="Private note", recorded_at=when),
        ProjectMemory(project_id=project.id, kind="entity", title="Competitor X", recorded_at=when),
    ])
    db.commit()

    items = duct_items(db, project.id, date(2026, 11, 4), TODAY, already=set())
    kinds = [(i.kind, i.title) for i in items]
    assert kinds == [
        ("artifact", "Organic signups up 18%"),
        ("change_set", "Shift budget to brand (google_ads, applied)"),
        ("memory", "Brand budget shift: +12% clicks"),
    ]
    assert items[0].ref == "art:weekly-brief"
    # Outside the window, nothing.
    assert duct_items(db, project.id, date(2026, 10, 1), date(2026, 10, 7), already=set()) == []
