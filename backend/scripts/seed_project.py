"""Seed or update a project from a JSON file.

Onboarding is the normal way a project is created; this is the same write for
cases where the profile already exists as a document — a migrated account, a
demo tenant, or a research dump too long to retype into a five-step form.

The payload's ``id`` is the upsert key, so re-running after an edit updates the
row in place. That matters for memory: ``seed_project_profile`` supersedes the
previous derived entries rather than duplicating them, which is what makes
"target CPA $45 (was $60 until 30 Jun)" possible.

Reads DATABASE_URL the same way the server does — ``backend/.env`` then
``backend/.env.local`` — so run it from the backend directory:

    poetry run python scripts/seed_project.py --file path/to/project.json --dry-run
    poetry run python scripts/seed_project.py --file path/to/project.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlmodel import Session  # noqa: E402

from db.session import get_engine  # noqa: E402
from models.auth import User  # noqa: E402
from models.project import Project  # noqa: E402
from service.membership import ensure_owner_membership  # noqa: E402
from service.memory import seed_project_profile  # noqa: E402
from utils.dates import utcnow  # noqa: E402

# Payload key -> Project attribute. `url` is spelled `url` on the model but
# `website_url` in the API, so both are accepted.
SCALAR_FIELDS = {
    "name": "name",
    "slug": "slug",
    "tagline": "tagline",
    "description": "description",
    "url": "url",
    "website_url": "url",
    "company_name": "company_name",
    "industry": "industry",
    "business_model": "business_model",
    "pitch": "pitch",
    "autonomy_level": "autonomy_level",
}

JSON_FIELDS = (
    "targets",
    "audience",
    "competition",
    "brand_channels",
    "content_brand",
    "content_pillars",
    "content_visual_assets",
)


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text())
    # Keys starting with "_" are notes for whoever edits the file.
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def _resolve_owner(session: Session, email: str) -> User:
    user = session.execute(
        select(User).where(User.email == email)
    ).scalars().first()
    if user is None:
        raise SystemExit(
            f"No user with email {email!r} in this database. "
            "Sign in once through the app first, or point --file at a different owner."
        )
    return user


def _describe(value) -> str:
    """One-line preview of a value, for the plan output."""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= 96 else text[:93] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path, help="Project JSON payload")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to the database. Without it the script only prints the plan.",
    )
    args = parser.parse_args()

    payload = _load(args.file)
    project_id = UUID(str(payload["id"]))
    owner_email = payload["owner_email"]

    engine = get_engine()
    if engine is None:
        raise SystemExit("DATABASE_URL is not configured.")

    with Session(engine) as session:
        user = _resolve_owner(session, owner_email)
        existing = session.execute(
            select(Project).where(Project.id == project_id)
        ).scalars().first()
        is_new = existing is None
        project = existing or Project(id=project_id, user_id=user.id)

        print(f"database : {engine.url.host}/{engine.url.database}")
        print(f"owner    : {user.email} ({user.id})")
        print(f"project  : {project_id} — {'CREATE' if is_new else 'UPDATE'}\n")

        changes: list[tuple[str, str]] = []
        for key, attr in SCALAR_FIELDS.items():
            if key not in payload:
                continue
            new = payload[key]
            if getattr(project, attr, None) != new:
                changes.append((attr, _describe(new)))
            setattr(project, attr, new)

        for key in JSON_FIELDS:
            if key not in payload:
                continue
            new = payload[key]
            if getattr(project, key, None) != new:
                changes.append((key, _describe(new)))
            setattr(project, key, new)

        if not changes:
            print("No changes — the stored project already matches this file.")
            return 0

        width = max(len(name) for name, _ in changes)
        for name, preview in changes:
            print(f"  {name.ljust(width)}  {preview}")

        if not args.apply:
            print("\nDry run. Re-run with --apply to write.")
            return 0

        project.updated_at = utcnow()
        session.add(project)
        session.flush()
        ensure_owner_membership(project, session)
        session.commit()
        session.refresh(project)

        written = seed_project_profile(session, project, user_id=user.id)
        print(f"\nWrote project. Derived {len(written)} project-memory entries:")
        for row in written:
            print(f"  [{row.kind}] {row.title}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
