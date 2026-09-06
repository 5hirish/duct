"""`.env.example` must stay a true description of what the backend reads.

Why this drifted far enough to need a test: **every setting in `config.py` has a
default.** Nothing fails when a variable is missing — the feature it powers just
quietly does nothing. So an undocumented setting is not a broken build, it is an
undiscoverable one, and the file decayed to covering roughly a third of what a
running instance actually sets. `SENTRY_DSN` was in `.env.local` and `.env.prod`
and read by `config.py`, but a fresh clone had no way to learn it existed.

Two checks, chosen because both fail loudly and neither has false positives:

* Nothing stale — every key here still maps to a real setting. Catches the
  rename (`DUCT_GOOGLE_CLIENT_SECRET` → `GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET`
  left this file behind) and the typo.
* Nothing secret left undocumented — a credential-shaped field must appear.
  Deliberately narrower than "every field": the internal tuning knobs are
  numerous and uninteresting, and a check that fires constantly gets suppressed
  rather than fixed. Credentials are the ones whose absence actually blocks
  someone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from config import Configs

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"

# Read from the environment by something other than Configs, so they have no
# field to match. Each needs a reason, or it is just a hole in the check.
NOT_CONFIG_FIELDS = {
    # Supplied by Railway, consumed by the uvicorn start command in railway.json.
    "PORT",
    # Read straight from os.environ by the langchain-google-genai SDK.
    "GOOGLE_API_KEY",
}

# What counts as "a credential someone must be told about".
CREDENTIAL_PATTERN = re.compile(
    r"api_key|_secret|_token|_dsn|password|client_id|encryption_key|jwt_secret"
)


def _documented_keys() -> set[str]:
    keys = set()
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip().upper())
    return keys


def _accepted_names(field_name: str, field) -> set[str]:
    """Every env spelling that resolves to this field, aliases included."""
    names = {field_name.upper()}
    alias = field.validation_alias
    if alias is not None:
        for choice in getattr(alias, "choices", None) or [alias]:
            names.add(str(getattr(choice, "alias", choice)).upper())
    return names


ALL_ACCEPTED = {
    name
    for field_name, field in Configs.model_fields.items()
    for name in _accepted_names(field_name, field)
}

CREDENTIAL_FIELDS = sorted(
    field_name
    for field_name in Configs.model_fields
    if CREDENTIAL_PATTERN.search(field_name)
)


def test_no_stale_keys():
    """Every documented key still resolves to a real setting."""
    stale = sorted(_documented_keys() - ALL_ACCEPTED - NOT_CONFIG_FIELDS)
    assert not stale, (
        f".env.example documents {stale}, which config.py no longer reads. "
        "Rename or remove them — a stale example is worse than none, because it "
        "is followed."
    )


@pytest.mark.parametrize("field_name", CREDENTIAL_FIELDS)
def test_credentials_are_documented(field_name):
    """A credential-shaped setting must be discoverable from .env.example."""
    documented = _documented_keys()
    accepted = _accepted_names(field_name, Configs.model_fields[field_name])
    assert accepted & documented, (
        f"config.py reads `{field_name}` but .env.example never mentions it "
        f"(any of {sorted(accepted)}). Because every setting has a default, "
        "leaving it out does not fail — it just makes the feature silently "
        "inert for anyone who did not already know."
    )


def test_not_config_fields_are_really_absent():
    """The allowlist must not outlive its reason.

    If one of these becomes a real Configs field, it should be checked like any
    other rather than sitting in a permanent exemption.
    """
    now_real = sorted(NOT_CONFIG_FIELDS & ALL_ACCEPTED)
    assert not now_real, (
        f"{now_real} are now real config settings — drop them from "
        "NOT_CONFIG_FIELDS so they are covered by the checks above."
    )
