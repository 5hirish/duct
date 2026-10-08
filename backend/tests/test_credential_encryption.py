"""Credentials at rest: Fernet keys that rotate, and KMS envelopes beside them.

What these pin is the two promises service/credentials.py makes. A key can be
replaced without losing a row: the old key still opens what it wrote, and the
rotate script moves every row onto the new one. And with KMS on, nothing in
the database plus the environment decrypts a credential without asking KMS,
while rows written before it keep working.

No network: the KMS here is a stand-in with the same wrap/unwrap surface, and
the one test of the real client replaces its HTTP session.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlmodel import Session

import service.credentials as credentials_service
from config import Configs
from models.auth import User
from models.connector import ConnectorCredential
from scripts.rotate_credentials import rotate
from service.credential_kms import KMS_API, GcpKms, KmsUnavailable
from service.credentials import (
    KIND_FERNET_CURRENT,
    KIND_FERNET_OLD,
    KIND_KMS,
    KIND_UNREADABLE,
    decrypt_credentials,
    encrypt_credentials,
    token_kind,
)
from tests.conftest import make_sqlite_engine

OLD = Fernet.generate_key().decode()
NEW = Fernet.generate_key().decode()
KEY_NAME = "projects/p/locations/global/keyRings/duct/cryptoKeys/credentials"


class FakeKms:
    """Wraps with a master key the database never sees, and counts unwraps."""

    def __init__(self, key_name: str = KEY_NAME, *, down: bool = False) -> None:
        self.key_name = key_name
        self._master = Fernet(Fernet.generate_key())
        self.down = down
        self.unwraps = 0

    def wrap(self, plaintext: bytes) -> bytes:
        if self.down:
            raise KmsUnavailable("KMS encrypt answered 503")
        return self._master.encrypt(plaintext)

    def unwrap(self, ciphertext: bytes) -> bytes:
        if self.down:
            raise KmsUnavailable("KMS decrypt answered 503")
        self.unwraps += 1
        return self._master.decrypt(ciphertext)


@pytest.fixture
def keys(monkeypatch):
    """Set the Fernet keys (newest first) and, optionally, a KMS."""
    state = {"kms": None}
    credentials_service._unwrap_cached.cache_clear()

    def configure(*fernet: str, kms: FakeKms | None = None) -> None:
        config = Configs(credentials_encryption_key=",".join(fernet))
        monkeypatch.setattr(credentials_service, "get_configs", lambda: config)
        state["kms"] = kms
        credentials_service._unwrap_cached.cache_clear()

    monkeypatch.setattr(credentials_service, "_kms", lambda: state["kms"])
    yield configure
    credentials_service._unwrap_cached.cache_clear()


@pytest.fixture
def db():
    engine = make_sqlite_engine(drop_partial_indexes=True)
    with Session(engine) as session:
        yield session


def _row(db: Session, token: str, connector_type: str = "stripe") -> ConnectorCredential:
    user = User(email=f"{connector_type}-{len(token)}@example.com")
    db.add(user)
    db.commit()
    row = ConnectorCredential(user_id=user.id, connector_type=connector_type, credentials_enc=token)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Fernet: rotation
# ---------------------------------------------------------------------------


def test_a_new_key_in_front_still_opens_what_the_old_one_wrote(keys):
    keys(OLD)
    token = encrypt_credentials({"api_key": "rk_live"})

    keys(NEW, OLD)
    assert decrypt_credentials(token) == {"api_key": "rk_live"}
    assert token_kind(token) == KIND_FERNET_OLD
    assert token_kind(encrypt_credentials({"api_key": "rk_live"})) == KIND_FERNET_CURRENT


def test_dropping_a_key_before_rotating_loses_its_rows(keys):
    keys(OLD)
    token = encrypt_credentials({"api_key": "rk_live"})
    keys(NEW)
    with pytest.raises(HTTPException):
        decrypt_credentials(token)
    assert token_kind(token) == KIND_UNREADABLE


def test_the_rotate_script_moves_every_row_onto_the_new_key(keys, db):
    keys(OLD)
    rows = [_row(db, encrypt_credentials({"n": i}), f"type{i}") for i in range(3)]
    keys(NEW, OLD)

    kinds, rewritten, unreadable = rotate(db, apply=False)
    assert kinds[KIND_FERNET_OLD] == 3 and rewritten == 0  # a dry run writes nothing

    kinds, rewritten, unreadable = rotate(db, apply=True)
    assert rewritten == 3 and unreadable == []

    keys(NEW)  # the old key can go now
    for i, row in enumerate(rows):
        db.refresh(row)
        assert decrypt_credentials(row.credentials_enc) == {"n": i}


def test_a_row_no_key_opens_is_reported_and_left_alone(keys, db):
    keys(OLD)
    lost = _row(db, encrypt_credentials({"x": 1}))
    keys(NEW)
    before = lost.credentials_enc

    _, rewritten, unreadable = rotate(db, apply=True)

    assert unreadable == [str(lost.id)] and rewritten == 0
    db.refresh(lost)
    assert lost.credentials_enc == before


# ---------------------------------------------------------------------------
# KMS envelopes
# ---------------------------------------------------------------------------


def test_with_kms_a_token_is_an_envelope_the_fernet_key_cannot_open(keys):
    kms = FakeKms()
    keys(NEW, kms=kms)
    token = encrypt_credentials({"refresh_token": "1//secret"})

    assert token.startswith("kms1:") and token_kind(token) == KIND_KMS
    assert "secret" not in token
    # The environment's Fernet key is no help: the data key is KMS-wrapped.
    inner = token.split(":", 2)[2]
    with pytest.raises(Exception):
        Fernet(NEW.encode()).decrypt(inner.encode())
    assert decrypt_credentials(token) == {"refresh_token": "1//secret"}


def test_rows_from_before_kms_still_read_and_rotate_onto_it(keys, db):
    keys(NEW)
    legacy = _row(db, encrypt_credentials({"api_key": "pb_live"}), "post_bridge")

    kms = FakeKms()
    keys(NEW, kms=kms)
    assert decrypt_credentials(legacy.credentials_enc) == {"api_key": "pb_live"}

    _, rewritten, _ = rotate(db, apply=True)
    db.refresh(legacy)
    assert rewritten == 1 and token_kind(legacy.credentials_enc) == KIND_KMS
    assert decrypt_credentials(legacy.credentials_enc) == {"api_key": "pb_live"}


def test_a_data_key_is_unwrapped_once_per_process(keys):
    kms = FakeKms()
    keys(NEW, kms=kms)
    token = encrypt_credentials({"api_key": "apify_api_x"})
    for _ in range(5):
        decrypt_credentials(token)
    assert kms.unwraps == 1


def test_kms_down_is_an_error_not_an_empty_credential(keys):
    keys(NEW, kms=FakeKms())
    token = encrypt_credentials({"api_key": "k"})

    credentials_service._unwrap_cached.cache_clear()
    keys(NEW, kms=FakeKms(down=True))
    with pytest.raises(HTTPException):
        decrypt_credentials(token)
    with pytest.raises(HTTPException):
        encrypt_credentials({"api_key": "k"})


def test_an_envelope_without_kms_configured_is_refused(keys):
    keys(NEW, kms=FakeKms())
    token = encrypt_credentials({"api_key": "k"})
    keys(NEW)
    with pytest.raises(HTTPException):
        decrypt_credentials(token)


# ---------------------------------------------------------------------------
# The Cloud KMS client
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> dict:
        return self._body


class _Session:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict, timeout: float) -> _Response:  # noqa: A002 — requests' own name
        self.calls.append((url, json))
        if self.status != 200:
            return _Response(self.status, {"error": {"message": "denied"}})
        if url.endswith(":encrypt"):
            wrapped = b"wrapped:" + base64.b64decode(json["plaintext"])
            return _Response(200, {"ciphertext": base64.b64encode(wrapped).decode()})
        plain = base64.b64decode(json["ciphertext"]).removeprefix(b"wrapped:")
        return _Response(200, {"plaintext": base64.b64encode(plain).decode()})


def test_the_client_posts_base64_to_the_keys_encrypt_and_decrypt():
    kms = GcpKms(KEY_NAME, json.dumps({"type": "service_account"}))
    kms._session = _Session()

    wrapped = kms.wrap(b"data key")
    assert kms.unwrap(wrapped) == b"data key"
    (enc_url, enc_body), (dec_url, _) = kms._session.calls
    assert enc_url == f"{KMS_API}/{KEY_NAME}:encrypt" and dec_url == f"{KMS_API}/{KEY_NAME}:decrypt"
    assert base64.b64decode(enc_body["plaintext"]) == b"data key"


def test_a_refusal_from_kms_is_kms_unavailable():
    kms = GcpKms(KEY_NAME)
    kms._session = _Session(status=403)
    with pytest.raises(KmsUnavailable):
        kms.wrap(b"data key")
