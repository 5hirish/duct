"""Google OAuth (Authorization Code) flow for connectors that use Google identity."""

from __future__ import annotations

from google_auth_oauthlib.flow import Flow

from config import get_configs

# Use canonical URLs so token response scopes match (avoids "Scope has changed" from
# google-auth when Google returns userinfo.* URLs vs short "email"/"profile" names).
_GOOGLE_SIGNIN_SCOPES_DEFAULT: tuple[str, ...] = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
)


def create_google_oauth_flow(*, state: str | None, scopes: list[str]) -> Flow:
    """Build a Google OAuth web flow; ``redirect_uri`` comes from config."""
    cfg = get_configs()
    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        raise ValueError(
            "Missing GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET backend env vars."
        )
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": cfg.google_oauth_client_id,
                "client_secret": cfg.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=scopes,
        state=state,
    )
    flow.redirect_uri = cfg.google_oauth_redirect_uri
    return flow


def create_google_signin_flow(*, state: str | None, scopes: list[str] | None = None) -> Flow:
    """Build a Google OAuth web flow for user sign-in (identity, not data access)."""
    cfg = get_configs()
    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        raise ValueError(
            "Missing GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET backend env vars."
        )
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": cfg.google_oauth_client_id,
                "client_secret": cfg.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=scopes or list(_GOOGLE_SIGNIN_SCOPES_DEFAULT),
        state=state,
    )
    flow.redirect_uri = cfg.google_signin_redirect_uri
    return flow
