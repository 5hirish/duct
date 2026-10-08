"""Re-encrypt every stored credential under the current key.

Run it after either change to how credentials are encrypted
(service/credentials.py):

* a new Fernet key put in front of CREDENTIALS_ENCRYPTION_KEY, to move rows
  off the old one before it is dropped;
* CREDENTIALS_KMS_KEY set, to move rows written before it onto KMS envelopes.

Dry run by default: it reports how many rows are under each key and changes
nothing. ``--apply`` rewrites every row not already under the current key. A
row no configured key can open is counted and left alone, by id only: it was
unreadable before the run as well, and deleting someone's credential is not
this script's call.

It is safe to run twice, and safe to stop halfway: each row is committed on
its own and is readable under both keys until the old one is dropped. Drop the
old Fernet key only after a dry run reports nothing left on it.

Reads DATABASE_URL and the keys the way the server does (``backend/.env`` then
``backend/.env.local``), so run it from ``backend/`` with the environment of
the database you mean:

    poetry run python scripts/rotate_credentials.py
    poetry run python scripts/rotate_credentials.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlmodel import Session  # noqa: E402

from db.session import get_engine  # noqa: E402
from models.connector import ConnectorCredential  # noqa: E402
from service.credentials import (  # noqa: E402
    KIND_UNREADABLE,
    current_kind,
    decrypt_credentials,
    encrypt_credentials,
    token_kind,
)


def rotate(session: Session, *, apply: bool) -> tuple[Counter, int, list[str]]:
    """(rows per kind before, rows rewritten, ids no key could open)."""
    target = current_kind()
    kinds: Counter = Counter()
    rewritten = 0
    unreadable: list[str] = []
    ids = session.execute(select(ConnectorCredential.id)).scalars().all()
    for row_id in ids:
        row = session.get(ConnectorCredential, row_id)
        if row is None:
            continue
        kind = token_kind(row.credentials_enc)
        kinds[kind] += 1
        if kind == KIND_UNREADABLE:
            unreadable.append(str(row_id))
            continue
        if kind == target or not apply:
            continue
        row.credentials_enc = encrypt_credentials(decrypt_credentials(row.credentials_enc))
        session.add(row)
        session.commit()
        rewritten += 1
    return kinds, rewritten, unreadable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--apply", action="store_true", help="rewrite rows (default: report only)")
    args = parser.parse_args()

    engine = get_engine()
    if engine is None:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return 2
    with Session(engine) as session:
        kinds, rewritten, unreadable = rotate(session, apply=args.apply)

    target = current_kind()
    print(f"current key: {target}")
    for kind, count in sorted(kinds.items()):
        print(f"  {kind:<12} {count}")
    if args.apply:
        print(f"rewritten: {rewritten}")
    else:
        pending = sum(n for k, n in kinds.items() if k not in (target, KIND_UNREADABLE))
        print(f"would rewrite: {pending} (dry run; --apply to write)")
    if unreadable:
        print(f"unreadable under every configured key: {len(unreadable)}")
        for row_id in unreadable:
            print(f"  {row_id}")
    return 1 if unreadable else 0


if __name__ == "__main__":
    raise SystemExit(main())
