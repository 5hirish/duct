"""The key service that wraps credential data keys on hosted Duct.

``service/credentials.py`` encrypts each stored credential with a data key of
its own and asks a KMS to wrap that data key. The wrapping key never leaves
the KMS, so what sits in the database, and what sits in the server's
environment beside it, cannot decrypt anything offline: each unwrap is a live
request that the KMS logs, and revoking the service account ends it.

Google Cloud KMS, over its REST API with google-auth (already a dependency of
the Google connectors), because Duct's Google project is the cloud account it
already has. Another provider is one more class with ``wrap``/``unwrap``.

Grant the service account ``roles/cloudkms.cryptoKeyEncrypterDecrypter`` on
the one key and nothing else. A symmetric key with automatic rotation on is
enough: KMS unwraps with whichever version wrapped, and new data keys are
wrapped with the primary.

No DB here, and nothing about credentials: bytes in, bytes out.
"""

from __future__ import annotations

import base64
import json
import threading

KMS_SCOPE = "https://www.googleapis.com/auth/cloudkms"
KMS_API = "https://cloudkms.googleapis.com/v1"
# Long enough for a cold token fetch plus the call; a credential read that
# waits longer than this is better reported than hung on.
KMS_TIMEOUT_S = 10


class KmsUnavailable(Exception):
    """The KMS could not wrap or unwrap: unreachable, refused, or misconfigured."""


class GcpKms:
    """One Cloud KMS symmetric key.

    ``key_name`` is the key's resource name,
    ``projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>``.
    ``service_account_json`` is the key file's contents; empty uses
    Application Default Credentials (``GOOGLE_APPLICATION_CREDENTIALS``, or
    the metadata server on Google's own hosting).
    """

    def __init__(self, key_name: str, service_account_json: str = "") -> None:
        self.key_name = key_name.strip()
        self._service_account_json = service_account_json.strip()
        self._session = None
        self._lock = threading.Lock()

    def _authorized_session(self):
        # Built on first use, not at import: a process that never touches a
        # credential (most tests, the prompt dump) never needs google-auth.
        with self._lock:
            if self._session is None:
                import google.auth
                from google.auth.transport.requests import AuthorizedSession
                from google.oauth2 import service_account

                try:
                    if self._service_account_json:
                        creds = service_account.Credentials.from_service_account_info(
                            json.loads(self._service_account_json), scopes=[KMS_SCOPE],
                        )
                    else:
                        creds, _ = google.auth.default(scopes=[KMS_SCOPE])
                except Exception as exc:  # noqa: BLE001 — any bad credential is the same answer
                    raise KmsUnavailable(f"KMS credentials are not usable: {type(exc).__name__}") from exc
                self._session = AuthorizedSession(creds)
            return self._session

    def _call(self, verb: str, body: dict) -> dict:
        try:
            res = self._authorized_session().post(
                f"{KMS_API}/{self.key_name}:{verb}", json=body, timeout=KMS_TIMEOUT_S,
            )
        except KmsUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — transport, token refresh
            raise KmsUnavailable(f"KMS {verb} failed: {type(exc).__name__}") from exc
        if res.status_code != 200:
            # The status only: KMS error bodies name the key and the caller,
            # which is fine for the log but not worth echoing anywhere else.
            raise KmsUnavailable(f"KMS {verb} answered {res.status_code}")
        return res.json()

    def wrap(self, plaintext: bytes) -> bytes:
        out = self._call("encrypt", {"plaintext": base64.b64encode(plaintext).decode()})
        return base64.b64decode(out["ciphertext"])

    def unwrap(self, ciphertext: bytes) -> bytes:
        out = self._call("decrypt", {"ciphertext": base64.b64encode(ciphertext).decode()})
        return base64.b64decode(out["plaintext"])
