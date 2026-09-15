"""Live smoke: every connector a real user has bound, pulled once, for real.

The offline suite proves each fetcher builds the right request; only the
vendor can prove the request is still accepted. This walks one user's
projects, and for every bound data source runs the same fetch the insights
agent would — every catalog entity for the connectors the catalog covers,
the connector's own pull for the rest — over a two-week window, and reports
one line per pull. Anything but ``ok`` fails the run at the end, together,
so one broken token does not hide a second.

It found the OAuth client split (a Google refresh token minted by the
desktop client cannot be refreshed by the hosted one) on its first hand run
on 2026-09-14. That is the class of thing it is for: a change on the
vendor's side, or in Duct's credential plumbing, that arrives as a support
thread otherwise.

Gated like the other live tests — skips unless the database and a user are
named — and run by `.github/workflows/connector-smoke.yml` on a schedule:

  DATABASE_URL=… CREDENTIALS_ENCRYPTION_KEY=… GOOGLE_WEB_OAUTH_CLIENT_ID=… \\
  GOOGLE_WEB_OAUTH_CLIENT_SECRET=… DUCT_SMOKE_USER_EMAIL=you@example.com \\
    poetry run pytest -m live tests/test_connector_smoke.py -s

Output is status only. Rows, tokens and account names never print: the run
log is a GitHub Actions artifact and this repository is public.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from utils.dates import last_n_days

pytestmark = pytest.mark.live

WINDOW_DAYS = 14

#: Read connectors the insights catalog does not cover, pulled through their
#: own fetcher: ``connector_id -> (module path, function name)``. Imported
#: lazily so collecting this file costs nothing offline.
_DIRECT_PULLS = {
    "meta_ads": ("service.meta.ads.fetch", "fetch_meta_ads"),
    "apple_ads": ("service.apple.ads.fetch", "fetch_apple_ads"),
    "openai_ads": ("service.openai.ads.fetch", "fetch_openai_ads"),
    "stripe": ("service.stripe.fetch", "fetch_stripe"),
    "revenuecat": ("service.revenuecat.fetch", "fetch_revenuecat"),
}


@dataclass(frozen=True)
class Pull:
    project: str
    connector: str
    entity: str
    status: str
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _skip_reason() -> str | None:
    from config import get_configs

    if not (os.environ.get("DATABASE_URL") or get_configs().database_url):
        return "DATABASE_URL not set"
    if not os.environ.get("DUCT_SMOKE_USER_EMAIL"):
        return "DUCT_SMOKE_USER_EMAIL not set (whose connectors to pull)"
    return None


def _user(session, email: str):
    from sqlmodel import select

    from models.auth import User
    from service.membership import normalize_email

    user = session.exec(select(User).where(User.email == normalize_email(email))).first()
    if user is None:
        pytest.fail("no user with that email in this database")
    return user


def _pulls(session, user) -> Iterator[Pull]:
    from agents.insights.fetchers import fetch_entity, fetch_specs
    from service.connector_access import STATUS_BOUND, list_data_sources, resolve_read_credentials
    from service.membership import accessible_projects

    date_from, date_to = last_n_days(WINDOW_DAYS)
    by_connector: dict[str, list[str]] = {}
    for entity_id, spec in fetch_specs().items():
        by_connector.setdefault(spec.connector_id, []).append(entity_id)

    for project in accessible_projects(user, session):
        # Names are the user's; the index is what the log may show.
        label = f"project#{str(project.id)[:8]}"
        for source in list_data_sources(session, user_id=user.id, project_id=project.id):
            if source.status != STATUS_BOUND:
                continue
            if source.connector_id in by_connector:
                for entity_id in sorted(by_connector[source.connector_id]):
                    result = fetch_entity(
                        entity_id, user_id=user.id, project_id=project.id,
                        date_from=date_from, date_to=date_to,
                    )
                    yield Pull(label, source.connector_id, entity_id, result["status"], result.get("message", ""))
                continue
            direct = _DIRECT_PULLS.get(source.connector_id)
            if direct is None:
                yield Pull(label, source.connector_id, "-", "skipped", "no read fetcher for this connector")
                continue
            creds = resolve_read_credentials(
                session, user_id=user.id, project_id=project.id,
                connector_type=source.connector_id, account_id=source.account_id,
            )
            yield _direct_pull(label, source.connector_id, direct, creds)


def _direct_pull(label: str, connector_id: str, target: tuple[str, str], creds: dict) -> Pull:
    import importlib

    module, name = target
    fetch = getattr(importlib.import_module(module), name)
    if not creds:
        return Pull(label, connector_id, "pull", "not_connected", "no credentials stored")
    try:
        payload = fetch(creds, WINDOW_DAYS)
    except Exception as exc:  # noqa: BLE001 — the status line is the whole point
        return Pull(label, connector_id, "pull", "fetch_failed", f"{type(exc).__name__}: {str(exc)[:200]}")
    # The manual-connector pulls isolate per section; a section that failed is
    # a failed pull here, because the agent would be reading a hole.
    errors = payload.get("errors") or {}
    if errors:
        return Pull(label, connector_id, "pull", "fetch_failed", "; ".join(f"{k}: {v[:120]}" for k, v in errors.items()))
    return Pull(label, connector_id, "pull", "ok")


def test_every_bound_connector_still_answers(capsys):
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)

    from db.session import get_session

    with next(get_session()) as session:
        user = _user(session, os.environ["DUCT_SMOKE_USER_EMAIL"])
        pulls = list(_pulls(session, user))

    with capsys.disabled():
        print()
        for pull in pulls:
            mark = "ok  " if pull.ok else "FAIL"
            print(f"  {mark}  {pull.project:<16} {pull.connector:<12} {pull.entity:<32} {pull.status}")
            if pull.message and not pull.ok:
                print(f"        {pull.message}")
        print(f"\n  {sum(p.ok for p in pulls)} ok, {sum(not p.ok for p in pulls)} failed, {len(pulls)} pulls")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("| project | connector | entity | status |\n|---|---|---|---|\n")
            for pull in pulls:
                fh.write(f"| {pull.project} | {pull.connector} | {pull.entity} | {pull.status} |\n")

    assert pulls, "the user has no bound data source in any project — nothing was smoked"
    failed = [p for p in pulls if not p.ok]
    assert not failed, f"{len(failed)} of {len(pulls)} pulls did not come back ok (see the table above)"
