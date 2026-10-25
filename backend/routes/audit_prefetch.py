"""The crawl onboarding starts the moment a URL validates.

``POST /api/audit/prefetch`` reads the root page synchronously — that is the
"Found it — Acme?" confirmation, and it takes a second — then crawls the rest
in the background while the user connects a provider. ``GET
/api/audit/prefetch/{id}`` is what the tray polls. The session that follows
passes ``crawl_id`` and ``run_pipeline`` picks the crawl up instead of
fetching it again (``agents/audit/prefetch.py``).

``POST /api/audit/documents`` is the same idea for the files the user adds
on the "Found it" card: the text is read now, the session names the ids it
was handed (``agents/audit/documents.py``).

The caller is a guest most of the time, so the gate is the guest's own
token plus rate limits rather than Turnstile, which the desktop shell could
not render anyway. The crawl and the text extraction are the only costs here
and both are Duct's; inference never runs on these routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from pydantic import BaseModel, ConfigDict

from agents.audit.documents import add_documents
from agents.audit.prefetch import get_prefetch, start_prefetch
from models.auth import User
from service.auth import get_current_user
from service.crawl.fetcher import SiteUnreachableError
from service.documents import MAX_BYTES, MAX_DOCUMENTS, Unreadable
from service.ratelimit import RateLimit, client_address

router = APIRouter(tags=["audit-prefetch"])

# A person retries a URL a few times at most; a script crawling the internet
# through us does not get to.
_PREFETCH_LIMIT = RateLimit(limit=6, window_seconds=600.0)
# The same bound per address, looser for a shared office line: a guest is a
# user anyone can mint, so a per-user limit alone multiplies by the guests.
_PREFETCH_ADDRESS_LIMIT = RateLimit(limit=20, window_seconds=600.0)
_PREFETCH_LIMIT_DETAIL = "That is a lot of sites in a row. Try again in a few minutes."

REASON_INVALID = "invalid_url"
REASON_UNREACHABLE = "unreachable"

# Someone adds a deck, removes it, adds two more; ten uploads covers a fussy
# person, and each one parses up to five files on our CPU.
_DOCUMENTS_LIMIT = RateLimit(limit=10, window_seconds=600.0)
_DOCUMENTS_ADDRESS_LIMIT = RateLimit(limit=30, window_seconds=600.0)
_DOCUMENTS_LIMIT_DETAIL = "That is a lot of files in a row. Try again in a few minutes."
REASON_TOO_MANY = "too_many_files"
_FILES_FIELD = "files"
# Five files at the per-file cap, plus the multipart framing around them. A
# body that declares more is refused before a byte of it is parsed.
_UPLOAD_MAX_BYTES = MAX_DOCUMENTS * MAX_BYTES + 64 * 1024


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
    _PREFETCH_ADDRESS_LIMIT.enforce(client_address(request), _PREFETCH_LIMIT_DETAIL)
    _PREFETCH_LIMIT.enforce(str(user.id), _PREFETCH_LIMIT_DETAIL)
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


@router.post("/audit/documents")
async def upload_documents(request: Request, user: User = Depends(get_current_user)) -> dict:
    """Read up to five files now; one result per file, readable or not.

    A file that cannot be read is a result with a reason, not a failed
    request, so the other four still land and the tile can say which one
    and why.

    The form is parsed here rather than declared as ``File(...)`` because
    FastAPI reads a declared body before any dependency runs: a stranger's
    2 GB upload would be spooled to disk before the token or the limiter was
    looked at. Here both come first, then the declared length.
    """
    _DOCUMENTS_ADDRESS_LIMIT.enforce(client_address(request), _DOCUMENTS_LIMIT_DETAIL)
    _DOCUMENTS_LIMIT.enforce(str(user.id), _DOCUMENTS_LIMIT_DETAIL)
    declared = int(request.headers.get("content-length") or 0)
    if not declared or declared > _UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"reason": Unreadable.TOO_LARGE.value, "message": "Those files are too large to read."},
        )
    async with request.form(max_files=MAX_DOCUMENTS, max_fields=0) as form:
        uploads = [f for f in form.getlist(_FILES_FIELD) if isinstance(f, UploadFile)]
        if not uploads or len(uploads) > MAX_DOCUMENTS:
            raise HTTPException(
                status_code=422,
                detail={"reason": REASON_TOO_MANY, "message": f"Add between 1 and {MAX_DOCUMENTS} files."},
            )
        names: list[str] = []
        payloads: dict[int, bytes] = {}
        for i, upload in enumerate(uploads):
            names.append(upload.filename or "document")
            # One byte past the cap is enough to know it is over.
            data = await upload.read(MAX_BYTES + 1)
            if len(data) <= MAX_BYTES:
                payloads[i] = data
    read = iter(await add_documents([(names[i], data) for i, data in payloads.items()], owner_id=str(user.id)))
    return {
        "documents": [
            next(read) if i in payloads else {"name": name, "error": Unreadable.TOO_LARGE.value}
            for i, name in enumerate(names)
        ]
    }
