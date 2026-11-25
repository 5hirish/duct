"""MCP tools for the changes, content and media scopes: work an outside agent
does on the person's behalf, every piece of which waits on the person in Duct.

Three capabilities, each its own scope, all unticked on the consent page:

* ``changes`` proposes a change to an ad or tag account. The proposal lands
  in the same review queue an in-app agent's does (``/execute``), through
  the same service (``service/execution/service.propose_change_set``), with
  ``source="mcp"``. ``service/execution/policy.should_auto_apply`` auto-applies
  only what Duct's own agent proposed, so an outside agent's proposal always
  waits for a human click, at every autonomy level: the person set autonomy
  for Duct's agent, which runs Duct's prompts, not for whatever reads their
  repo. A rollback is *requested* here and done by the person's click, for the
  same reason: it changes their live account.
* ``content`` reads the brand and the board and saves a text post as a draft.
  Draft only: scheduling and publishing are the person's buttons.
* ``media`` generates an image on the person's own saved image key. The one
  tool here that spends money, so it is its own scope, rate-limited, and
  returns a link, never the bytes.

No tool approves, applies, publishes, connects a tool or touches a credential,
and none calls a chat model on Duct's side.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from agents.content.channels import Platform, copy_problems, primary_channel, resolve as resolve_channel
from agents.content.publishing import project_publishing
from agents.content.schema import TEXT_POST_TYPE, ContentStatus
from agents.content.voice_rules import banned_words_in, voice_rules_of, writing_samples_of
from agents.engines import resolve_image_run
from agents.models import AspectRatio, image_model_for
from agents.tools.execution_tools import (
    STATUS_DESCRIPTION,
    ChangeSetArgs,
    ProposeChangesArgs,
    _register_executors,
    change_set_card,
)
from models.content import ContentPlan, ContentPost
from models.execution import ExecutionChangeSet
from service.connector_access import _GOOGLE_SHAPED
from service.execution.creds import resolve_execution_creds
from service.execution.registry import EXECUTOR_REGISTRY
from service.execution.service import guardrails_for, propose_change_set as propose_core
from service.images import GenerateImageRequest, ImageAPIError, asset_source_for, image_client_for, persist_generated_image
from service.mcp_server import scopes
from service.mcp_server.common import app_link, mark_untrusted, member_project, record_write
from service.mcp_server.protocol import Caller, Tool, ToolError
from service.model_settings import get_model_settings
from service.project_draft import get_value
from service.provider_keys import stored_provider_keys
from service.ratelimit import RateLimit
from utils.dates import utcnow

logger = logging.getLogger(__name__)

# Recorded on every change set an outside agent proposes. The policy's
# auto-apply verdict requires "agent", so this value is what keeps every MCP
# proposal in the review queue; the queue lists it under all sources.
MCP_SOURCE = "mcp"
MCP_AGENT_TYPE = "mcp"

EXECUTE_PATH = "/execute"
_EXECUTORS = ("google_ads", "ga4", "gtm", "mixpanel")

# Pictures cost the person money on their own key; an agent in a loop would
# spend it fast. Per person, so two of their agents share one budget.
_IMAGE_LIMIT = RateLimit(limit=10, window_seconds=600.0)

# The same decline the content agent gives, so the person reads one sentence
# about images wherever they asked for one.
NO_IMAGE_KEY = (
    "Image generation needs an API key from a provider with an image model: Google Gemini, "
    "OpenAI, xAI or OpenRouter. Add one in Duct (Settings, Providers), then try again."
)

_LIST_LIMIT = 50
_CAPTION_PREVIEW = 280


# -- changes ------------------------------------------------------------------

class ListOpsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector_type: Literal["", "google_ads", "ga4", "gtm", "mixpanel"] = Field(
        default="", description="Only this connector's operations. Empty for all."
    )


def list_change_ops(args: ListOpsArgs, caller: Caller) -> dict[str, Any]:
    # The same listing as the in-app agent's ListExecutableOps, read on this
    # request's session rather than a second one.
    _register_executors()
    wanted = args.connector_type
    ops = [
        {
            "op_type": spec.op_type,
            "connector_type": spec.connector_type,
            "label": spec.label,
            "destructive": spec.destructive,
            "supports_rollback": spec.rollback is not None,
        }
        for spec in EXECUTOR_REGISTRY.values()
        if spec.connector_type in _EXECUTORS and (not wanted or spec.connector_type == wanted)
    ]
    rules = {}
    for connector in _EXECUTORS:
        if wanted and connector != wanted:
            continue
        found = [g.rule for g in guardrails_for(caller.session, caller.user.id, connector, "") if g.active]
        if found:
            rules[connector] = found
    listing: dict[str, Any] = {"ops": ops, "guardrails": rules}
    # What the review queue will do with a proposal from here, said once so a
    # model does not tell the person their change is live.
    listing["note"] = (
        "Every change you propose waits for the person to approve it in Duct. Nothing you "
        "propose applies by itself, and no tool here approves or applies."
    )
    return listing


class ProposeArgs(ProposeChangesArgs):
    project_id: UUID = Field(description="The project the change is for, from list_projects.")


def propose_change_set(args: ProposeArgs, caller: Caller) -> dict[str, Any]:
    project = member_project(args.project_id, caller)
    _register_executors()
    connector_type = args.connector_type.strip()
    creds = resolve_execution_creds(
        caller.session, caller.user.id, connector_type, args.account_id.strip(), project_id=project.id,
    )
    connected = creds.get("refresh_token") if connector_type in _GOOGLE_SHAPED else bool(creds)
    if not connected:
        raise ToolError(
            f"{connector_type} is not connected for this project. Ask the person to connect it in Duct "
            f"({app_link('/connections')}), then propose again.",
            code="not_connected",
        )
    try:
        row = propose_core(
            caller.session,
            user_id=caller.user.id,
            connector_type=connector_type,
            account_id=args.account_id,
            account_name=args.account_name,
            title=args.title.strip() or "Proposed changes",
            context=args.context,
            changes=args.changes,
            creds=creds,
            project_id=project.id,
            agent_type=MCP_AGENT_TYPE,
            source=MCP_SOURCE,
        )
    except KeyError as exc:
        raise ToolError(f"Unknown op_type {exc}. Call list_change_ops for the ones you can propose.")
    except ValueError as exc:
        raise ToolError(str(exc))
    # The service records the proposal in the activity log itself
    # (change_set.proposed), so no second row here.
    return {
        **change_set_card(row),
        "review_url": app_link(EXECUTE_PATH),
        "next": "Tell the person what you proposed and that it waits for their approval in Duct.",
    }


def _own_change_set(change_set_id: str, caller: Caller) -> ExecutionChangeSet:
    """The person's own change set, on a project this connection may reach.
    One answer for a made-up id, a stranger's set and an ungranted project."""
    missing = ToolError("No change set with that id. Ids come from propose_change_set.", code="not_found")
    try:
        row = caller.session.get(ExecutionChangeSet, UUID(change_set_id.strip()))
    except ValueError:
        raise missing
    if row is None or row.user_id != caller.user.id:
        raise missing
    if row.project_id is None:
        # Not tied to a project: only a connection that reaches every project
        # may read it, since a grant names projects.
        if caller.project_grant is not None:
            raise missing
        return row
    try:
        member_project(row.project_id, caller)
    except ToolError:
        raise missing
    return row


def get_change_set(args: ChangeSetArgs, caller: Caller) -> dict[str, Any]:
    return {**change_set_card(_own_change_set(args.change_set_id, caller)), "review_url": app_link(EXECUTE_PATH)}


class RollbackArgs(ChangeSetArgs):
    reason: str = Field(
        min_length=1, max_length=1000,
        description="Why it should be undone, in a sentence the person reads before they click.",
    )


def request_rollback(args: RollbackArgs, caller: Caller) -> dict[str, Any]:
    row = _own_change_set(args.change_set_id, caller)
    if row.status not in ("applied", "partial"):
        raise ToolError(f"Nothing to roll back: this change set is {row.status}.", code="refused")
    record_write(
        caller,
        project_id=row.project_id,
        category="execution",
        action="change_set.rollback_requested",
        summary=f"Asked to roll back “{row.title}”: {args.reason.strip()}",
        target_type="change_set",
        target_id=str(row.id),
        data={"reason": args.reason.strip()},
    )
    return {
        "change_set_id": str(row.id),
        "status": row.status,
        "requested": True,
        "review_url": app_link(EXECUTE_PATH),
        "next": (
            "Nothing was rolled back yet. The person rolls it back from the change set in Duct; "
            "give them the link and your reason."
        ),
    }


# -- content ------------------------------------------------------------------

class ProjectArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID = Field(description="A project_id from list_projects.")


def get_brand(args: ProjectArgs, caller: Caller) -> dict[str, Any]:
    project = member_project(args.project_id, caller)
    brand = project.content_brand or {}
    rules = voice_rules_of(brand)
    return {
        "project_id": str(project.id),
        "name": project.name,
        "tagline": project.tagline or "",
        "description": project.description or "",
        "website_url": project.url or "",
        "brand": {k: v for k, v in brand.items() if k not in ("voice_rules", "writing_samples")},
        "voice_rules": rules.model_dump(),
        "writing_samples": writing_samples_of(brand),
        "pillars": (project.content_pillars or {}).get("items", []),
        "personas": list(get_value(project, "personas") or []),
        "brand_url": app_link("/content"),
        "note": "Write in this voice. A draft that uses a banned word is refused by save_post_draft.",
    }


class ListContentArgs(ProjectArgs):
    kind: Literal["posts", "plans"] = Field(default="posts", description="Posts on the board, or content plans.")
    status: Literal["", "draft", "scheduled", "posted", "failed"] = Field(
        default="", description="Posts only: just this status. Empty for every saved post."
    )


def _post_row(post: ContentPost) -> dict[str, Any]:
    caption = post.caption or ""
    return {
        "post_id": str(post.id),
        "status": post.status,
        "channel": primary_channel(post.platforms),
        "post_type": post.post_type,
        "title": post.title,
        "topic": post.topic,
        "pillar": post.pillar,
        "caption": caption if len(caption) <= _CAPTION_PREVIEW else caption[:_CAPTION_PREVIEW] + "…",
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "posted_at": post.posted_at.isoformat() if post.posted_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "review_url": app_link(f"/content/posts/{post.id}"),
    }


def _plan_row(plan: ContentPlan) -> dict[str, Any]:
    days = [d for d in (plan.days or []) if isinstance(d, dict)]
    return {
        "plan_id": str(plan.id),
        "name": plan.name,
        "status": plan.status,
        "start_date": plan.start_date.isoformat() if plan.start_date else None,
        "days": [
            {
                "date": d.get("date"),
                "topic": d.get("topic", ""),
                "pillar": d.get("pillar", ""),
                "status": d.get("status", ""),
                "post_type": d.get("post_type", ""),
                "platforms": d.get("platforms", []),
                "post_id": d.get("post_id"),
            }
            for d in days
        ],
        "review_url": app_link("/content"),
    }


def list_content(args: ListContentArgs, caller: Caller) -> dict[str, Any]:
    project = member_project(args.project_id, caller)
    if args.kind == "plans":
        plans = caller.session.execute(
            select(ContentPlan).where(ContentPlan.project_id == project.id)
            .order_by(ContentPlan.created_at.desc()).limit(_LIST_LIMIT)
        ).scalars().all()
        # A plan made from shipped work names issues and pull requests
        # strangers may have written; its topics echo them.
        return mark_untrusted(
            {"project_id": str(project.id), "plans": [_plan_row(p) for p in plans]}, ["plans[].days[].topic"]
        )
    stmt = select(ContentPost).where(ContentPost.project_id == project.id)
    if args.status:
        stmt = stmt.where(ContentPost.status == args.status)
    else:
        # Unsaved drafts live only in a drafting session, as on the board.
        stmt = stmt.where(ContentPost.status != ContentStatus.PENDING)
    posts = caller.session.execute(stmt.order_by(ContentPost.updated_at.desc()).limit(_LIST_LIMIT)).scalars().all()
    # A clone's caption follows a stranger's post closely.
    return mark_untrusted(
        {"project_id": str(project.id), "posts": [_post_row(p) for p in posts]}, ["posts[].caption"]
    )


_TEXT_CHANNELS = tuple(
    str(p) for p in Platform if not resolve_channel(str(p)).rules.requires_media
)
TextChannel = Literal[_TEXT_CHANNELS]  # type: ignore[valid-type]


class PostDraftArgs(ProjectArgs):
    channel: TextChannel = Field(  # type: ignore[valid-type]
        description="Where it would go. Text channels only: a channel that needs a picture or video is drafted in Duct."
    )
    text: str = Field(min_length=1, max_length=60000, description="The post's words, exactly as they would publish.")
    replies: list[str] = Field(
        default_factory=list, max_length=25,
        description="Follow-up posts in a thread, where the channel takes them. Usually empty.",
    )
    title: str = Field(default="", max_length=200, description="A short name for the board. Optional.")
    topic: str = Field(default="", max_length=200, description="What it is about, for the board. Optional.")


def _slug(title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return f"{date.today().isoformat()}-{words or 'post'}-{uuid4().hex[:6]}"


def save_post_draft(args: PostDraftArgs, caller: Caller) -> dict[str, Any]:
    project = member_project(args.project_id, caller)
    channel = resolve_channel(args.channel)
    replies = [r for r in args.replies if r.strip()]
    spec = project_publishing(caller.session, project.id, project.user_id).for_channel(channel.id)
    problems = copy_problems(
        channel.id, args.text, replies, strips_links=bool(spec and spec.strips_links_on(channel.id)),
    )
    # The project's banned words, checked here as the content agent checks
    # them: a rule a model may forget is a suggestion.
    used = banned_words_in("\n".join([args.text, *replies]), voice_rules_of(project.content_brand).banned_words)
    if used:
        problems.append(
            f"It uses {', '.join(repr(w) for w in used)}, which this project's voice rules ban. Rewrite those lines."
        )
    if problems:
        raise ToolError("Nothing saved. " + " ".join(problems) + " Fix it and call again.", code="validation")
    now = utcnow()
    post = ContentPost(
        project_id=project.id,
        post_dir_slug=_slug(args.title or args.topic or args.text[:40]),
        post_type=TEXT_POST_TYPE,
        # A draft the person can see on the board straight away. Pending is
        # for a drafting session's unsaved work, which this is not.
        status=ContentStatus.DRAFT,
        caption=args.text,
        replies=replies,
        title=args.title.strip(),
        topic=args.topic.strip(),
        platforms=[channel.id],
        created_at=now,
        updated_at=now,
    )
    caller.session.add(post)
    caller.session.commit()
    caller.session.refresh(post)
    record_write(
        caller,
        project_id=project.id,
        category="content",
        action="post.drafted",
        summary=f"Saved a {channel.label} draft" + (f" “{post.title}”" if post.title else ""),
        target_type="post",
        target_id=str(post.id),
        data={"channel": channel.id},
    )
    return {
        **_post_row(post),
        "next": "Saved as a draft. The person schedules or publishes it from Duct; nothing goes out from here.",
    }


# -- media --------------------------------------------------------------------

_RATIOS = tuple(r.value for r in AspectRatio)
RatioValue = Literal[_RATIOS]  # type: ignore[valid-type]


class ImageArgs(ProjectArgs):
    prompt: str = Field(min_length=3, max_length=4000, description="What the picture shows, in detail.")
    aspect_ratio: RatioValue = Field(default="1:1", description="Width to height.")  # type: ignore[valid-type]


def _image_run(caller: Caller):
    """The caller's own image-capable key, never the project owner's or
    Duct's: a collaborator's agent spending the owner's key is a bill the
    owner did not choose, and a hosted key is Duct's money."""
    run = resolve_image_run(
        None,
        stored_provider_keys(caller.session, caller.user.id),
        preferred=get_model_settings(caller.user.id).image_model,
    )
    if run is None or run.source == "cloud":
        return None
    return run


async def _generate(client, request):
    return await client.generate_image(request)


def generate_image(args: ImageArgs, caller: Caller) -> dict[str, Any]:
    import asyncio

    project = member_project(args.project_id, caller)
    allowed, retry_after = _IMAGE_LIMIT.allow(str(caller.user.id))
    if not allowed:
        raise ToolError(
            f"Too many images in a short time. Try again in {int(retry_after) + 1} seconds.", code="rate_limited"
        )
    run = _image_run(caller)
    if run is None:
        raise ToolError(NO_IMAGE_KEY, code="not_connected")
    request = GenerateImageRequest(
        prompt=args.prompt.strip(),
        model=image_model_for(run.provider),
        aspect_ratio=args.aspect_ratio,
        number_of_images=1,
    )
    client = image_client_for(run.provider, run.api_key)
    try:
        # The route runs tools in a worker thread with no loop of its own.
        images = asyncio.run(_generate(client, request))
    except ImageAPIError as exc:
        logger.warning("mcp: image generation failed: %s", exc)
        raise ToolError("The image provider declined or failed. Try again in a moment, or change the prompt.")
    if not images:
        raise ToolError("The image provider returned no picture. Try again, or change the prompt.")
    asset = persist_generated_image(
        project.id, images[0],
        db=caller.session,
        prompt=request.prompt,
        model=request.model.value,
        params={"aspect_ratio": request.aspect_ratio.value, "source": "mcp"},
        source=asset_source_for(run.provider),
    )
    record_write(
        caller,
        project_id=project.id,
        category="content",
        action="image.generated",
        summary=f"Generated an image on {run.provider.value}",
        target_type="asset",
        target_id=str(asset.asset_id),
        data={"model": request.model.value},
    )
    return {
        "asset_id": str(asset.asset_id),
        "url": asset.url,
        "model": request.model.value,
        "provider": run.provider.value,
        "billed_to": "the person's own provider key",
    }


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="list_change_ops",
        title="List changes Duct can propose",
        description=(
            "The operations you can propose on the person's ad and tag accounts (Google Ads, GA4, Tag "
            "Manager, Mixpanel), with which are destructive or reversible, and the account's guardrails. "
            "Call it before your first propose_change_set."
        ),
        args=ListOpsArgs,
        run=list_change_ops,
        read_only=True,
        scope=scopes.CHANGES,
    ),
    Tool(
        name="propose_change_set",
        title="Propose a change for approval",
        # Written for this path rather than reusing the in-app text: there a
        # proposal may auto-apply under the project's autonomy, here it never
        # does, and one description must not say both.
        description=(
            "Propose a change to the person's connected ad or tag account (call list_change_ops "
            "first for what you can propose). Every change is previewed as a dry-run diff against "
            "the account's current state and checked against its guardrails before anything is "
            "stored. A proposal from you never applies by itself, at any autonomy level: it waits "
            "in Duct's review queue until the person approves it there, and no tool approves or "
            "applies one. Explain WHY in `context`; the person reads it on the review card. Tell "
            "them it is waiting and give them review_url, then move on rather than polling."
        ),
        args=ProposeArgs,
        run=propose_change_set,
        read_only=False,
        scope=scopes.CHANGES,
    ),
    Tool(
        name="get_change_set",
        title="Read a proposed change",
        description=STATUS_DESCRIPTION.replace("ProposeChanges", "propose_change_set"),
        args=ChangeSetArgs,
        run=get_change_set,
        read_only=True,
        scope=scopes.CHANGES,
    ),
    Tool(
        name="request_rollback",
        title="Ask to roll back a change",
        description=(
            "Ask the person to roll back a change set that was applied and turned out wrong. "
            "Nothing is reverted by this call: it records your reason on the change set and returns "
            "the link where the person rolls it back in Duct with one click, using the rollback "
            "handles recorded at apply time. Only an applied or partially applied set can be rolled "
            "back. Tell the person what you asked for and why, and give them the link."
        ),
        args=RollbackArgs,
        run=request_rollback,
        read_only=False,
        scope=scopes.CHANGES,
    ),
    Tool(
        name="get_brand",
        title="Read the brand",
        description=(
            "The project's brand for writing posts: tagline, description, tone, voice rules (banned words "
            "included), writing samples, content pillars and audience personas."
        ),
        args=ProjectArgs,
        run=get_brand,
        read_only=True,
        scope=scopes.CONTENT,
    ),
    Tool(
        name="list_content",
        title="List posts or plans",
        description=(
            "The project's saved posts (newest first, optionally one status) or its content plans with "
            "their days, each with a link to it in Duct."
        ),
        args=ListContentArgs,
        run=list_content,
        read_only=True,
        scope=scopes.CONTENT,
        open_world=True,
    ),
    Tool(
        name="save_post_draft",
        title="Save a post draft",
        description=(
            "Save a text post for a channel as a draft on the project's board. Checked against the channel's "
            "length limit and the project's banned words; a refusal says what to fix. Draft only: the person "
            "schedules or publishes it in Duct. Show them the text before saving."
        ),
        args=PostDraftArgs,
        run=save_post_draft,
        read_only=False,
        scope=scopes.CONTENT,
    ),
    Tool(
        name="generate_image",
        title="Generate an image",
        description=(
            "Generate one image for the project on the person's own saved image key (Gemini, OpenAI, xAI or "
            "OpenRouter), which costs them money. Saved to the project's assets; returns its link. Say what "
            "you will generate before calling this."
        ),
        args=ImageArgs,
        run=generate_image,
        read_only=False,
        scope=scopes.MEDIA,
    ),
)
