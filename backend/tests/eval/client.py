"""Judge client construction + credential resolution (Google Gemini).

The judge is the harness's only network dependency: one vision-capable Gemini
call that scores the deliverable. Gemini — the same stack the v2/ADK engine sits
on — is used here instead of Claude because (a) the grading call must inspect
images and return JSON in a single shot, which google-genai does natively, and
(b) the Gemini key has the rate-limit headroom the raw Anthropic Messages API
path did not.

We call ``google-genai`` directly rather than Google ADK: in this codebase the
ADK/v2 path neither accepts image input nor emits native structured output (see
agents/insights/v2/schema_compat.py), both of which the vision judge needs. The
call shape mirrors service/google/brief.py (text + JSON) and
service/google/gemini/client.py (image parts).
"""

from __future__ import annotations

import os

# Default judge model: the v2 engine's Gemini default — multimodal (accepts
# images) and proven with JSON output in service/google/brief.py. Override per
# run with DUCT_JUDGE_MODEL (e.g. "gemini-3.1-flash-preview").
DEFAULT_JUDGE_MODEL = "gemini-2.5-flash"


class JudgeUnavailable(RuntimeError):
    """No usable Gemini credential / SDK is available for the judge."""


def _config_cred(name: str) -> str:
    """Best-effort read of a credential from Duct's settings (covers backend/.env
    for local runs). Never raises if config can't be imported."""
    try:
        from config import get_configs

        return str(getattr(get_configs(), name, "") or "")
    except Exception:
        return ""


def resolve_judge_api_key() -> str:
    """The Gemini API key for the judge — env first, then Duct config."""
    return (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or _config_cred("gemini_api_key")
    ).strip()


def judge_available() -> bool:
    """True when the google-genai SDK is importable and a Gemini key is present."""
    try:
        from google import genai  # noqa: F401
    except Exception:
        return False
    return bool(resolve_judge_api_key())


def build_judge_client():
    """Construct a ``google.genai.Client`` from the resolved Gemini key. Raises
    ``JudgeUnavailable`` when the SDK is missing or no key is set."""
    try:
        from google import genai
    except Exception as exc:  # pragma: no cover - import guard
        raise JudgeUnavailable("the google-genai SDK is not installed") from exc

    key = resolve_judge_api_key()
    if not key:
        raise JudgeUnavailable("no Gemini credential found (set GEMINI_API_KEY)")
    return genai.Client(api_key=key)
