"""The crawl onboarding starts the moment a URL validates.

``POST /api/audit/prefetch`` reads the root page synchronously — that is the
"Found it — Acme?" confirmation, and it takes a second — then crawls the rest
in the background while the user connects a provider. ``GET
/api/audit/prefetch/{id}`` is what the tray polls. The session that follows
passes ``crawl_id`` and ``run_pipeline`` picks the crawl up instead of
fetching it again (``agents/audit/prefetch.py``).

The caller is a guest most of the time, so the gate is the guest's own
token plus a per-user rate limit rather than Turnstile, which the desktop
shell could not render anyway. The crawl is the only cost here and it is
Duct's; inference never runs on this route.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from agents.audit.prefetch import get_prefetch, start_prefetch
from models.auth import User
from service.auth import get_current_user
from service.crawl.fetcher import SiteUnreachableError
from service.ratelimit import RateLimit

router = APIRouter(tags=["audit-prefetch"])

# A person retries a URL a few times at most; a script crawling the internet
# through us does not get to.
_PREFETCH_LIMIT = RateLimit(limit=6, window_seconds=600.0)

REASON_INVALID = "invalid_url"
REASON_UNREACHABLE = "unreachable"


class PrefetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    # The lead magnet's crawl depth; the app audit's default is deep.
    light: bool = False


def _normalise(url: str) -> str:
    url = (url or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    return url


@router.post("/audit/prefetch")
async def prefetch(
    body: PrefetchRequest, request: Request, user: User = Depends(get_current_user)
) -> dict:
    allowed, retry_after = _PREFETCH_LIMIT.allow(str(user.id))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="That is a lot of sites in a row. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    url = _normalise(body.url)
    if not url:
        raise HTTPException(status_code=422, detail={"reason": REASON_INVALID, "message": "Enter a website address."})
    try:
        entry = await start_prefetch(url, owner_id=str(user.id), light=body.light)
    except SiteUnreachableError:
        raise HTTPException(
            status_code=422,
            detail={"reason": REASON_UNREACHABLE, "message": "We couldn't reach that site — double-check the address."},
        ) from None
    except ValueError:
        # The SSRF guard's refusal reads like a network error and must not:
        # an internal address is not "unreachable", it is off limits.
        raise HTTPException(
            status_code=422,
            detail={"reason": REASON_INVALID, "message": "That doesn't look like a public website address."},
        ) from None
    return entry.status()


@router.get("/audit/prefetch/{crawl_id}")
async def prefetch_status(crawl_id: str, user: User = Depends(get_current_user)) -> dict:
    entry = get_prefetch(crawl_id, owner_id=str(user.id))
    if entry is None:
        # Expired, unknown, or someone else's — one answer for all three.
        raise HTTPException(status_code=404, detail="No such crawl.")
    return entry.status()
