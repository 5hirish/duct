"""Staged-execution tools — agents propose, humans approve.

The tool surface is deliberately asymmetric, and that asymmetry is the safety
property rather than a limitation:

- ``ProposeChanges`` stages a change set through the same service core as the
  HTTP route (preview + guardrails + autonomy policy). Reversible,
  allowlisted, guardrail-clean sets auto-apply when the project's autonomy
  level is ``assisted`` or ``auto``; everything else waits for a human.
- ``RollbackChangeSet`` exists as the safe escape hatch.
- There is **no approve or apply tool** — approval is human-only by
  construction (service/execution/policy.py). An agent cannot talk itself past
  the review gate at any autonomy level.

Two binders, one set of tool bodies: ``build_execution_tools_lc`` for the V1
(LangChain/deepagents) runners and ``build_execution_mcp_server`` for the V3
Claude Agent SDK runners, which mount it as the in-process ``duct_execute``
MCP server. The domain functions below are plain — the ports rule is that a
second harness costs a binder, never a second implementation.

DB access runs in ``asyncio.to_thread`` (sync SQLModel sessions) so tool calls
never block the SSE event loop; executor previews/applies do network I/O and
run in the same thread. Credentials resolve from the project's connector
binding → the user's stored encrypted connector rows → server env
(service/execution/creds.py) — agents never see or pass credentials.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agents.core.telemetry import tool_span

logger = logging.getLogger(__name__)

_DEFAULT_CONNECTORS = ("google_ads", "ga4", "gtm")


# ---------------------------------------------------------------------------
# Tool descriptions — shared by both binders, so the two harnesses cannot
# drift into describing different contracts to their models.
# ---------------------------------------------------------------------------

LIST_OPS_DESCRIPTION = (
    "List the operations you can propose as staged change sets — op_type, "
    "connector, whether it is destructive, whether it can be rolled back — "
    "plus the account's active guardrail rules (invariants you must respect). "
    "Call this before your first ProposeChanges to see what is executable."
)

PROPOSE_DESCRIPTION = (
    "Propose a staged change set against the user's connected account. Every "
    "change is previewed (dry-run diff + current-state snapshot) and checked "
    "against the account's guardrails before anything is stored. THE CONTRACT: "
    "destructive operations (GTM publish, GA4 archive/unlink) ALWAYS wait for "
    "explicit human approval in the review UI — you cannot apply them, and no "
    "tool exists that approves a change set. Reversible, guardrail-clean, "
    "non-destructive changes may auto-apply only when the user has set this "
    "project's autonomy to 'assisted' or 'auto'; raising autonomy never widens "
    "what may apply. The result tells you what happened: status 'proposed' = "
    "waiting for the user's review (tell them, then move on — do not poll); "
    "status 'applied' with applied_by 'auto' = done, report the results. Always "
    "explain WHY in `context` — the user reads it in the review card."
)

STATUS_DESCRIPTION = (
    "Fetch the current status of one change set you proposed earlier — overall "
    "status (proposed/approved/applied/partial/failed/rejected/rolled_back) "
    "plus per-change results and rollback availability. Use it when the user "
    "says they approved/applied something, or before proposing a rollback. "
    "Do not poll it while waiting for approval."
)

ROLLBACK_DESCRIPTION = (
    "Revert an applied change set using the rollback handles recorded at apply "
    "time — the safe escape hatch when an applied change turns out wrong "
    "(including auto-applied ones). Only works on applied/partial sets; "
    "changes whose op has no rollback are reported, not silently skipped."
)


# ---------------------------------------------------------------------------
# Argument schemas — one definition, rendered as a LangChain args_schema and
# as an MCP input_schema.
# ---------------------------------------------------------------------------

class ListOpsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_type: str = Field(
        default="",
        description="Filter by connector ('google_ads', 'ga4', 'gtm'). Empty = all available.",
    )


class ProposeChangesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_type: str = Field(
        description="Connector to execute against: 'google_ads', 'ga4', or 'gtm'."
    )
    account_id: str = Field(
        default="",
        description=(
            "Account identifier: Google Ads customer id, GA4 property id, or GTM "
            "account id. May be empty when the target paths carry it."
        ),
    )
    account_name: str = Field(
        default="", description="Human-readable account name for the review card. Optional."
    )
    title: str = Field(
        default="",
        description="Short imperative title for the change set (e.g. 'Add 12 negative keywords').",
    )
    context: str = Field(
        default="",
        description=(
            "Why these changes: the finding or reasoning behind them and the expected "
            "impact. Shown to the user in the review card."
        ),
    )
    changes: list[dict] = Field(
        default_factory=list,
        description=(
            "List of changes, each {op_type, summary, target: {...}, payload: {...}}. "
            "See ListExecutableOps for op_types; target/payload shapes follow each "
            "op's documented fields (e.g. google_ads.add_negative_keywords needs "
            "target.customer_id + target.campaign_id + payload.keywords)."
        ),
    )


class ChangeSetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_set_id: str = Field(description="The change set id (UUID) from ProposeChanges.")


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

def change_set_card(row, *, registry=None) -> dict:
    """Compact change-set payload for EXECUTION_PROPOSED SSE cards + tool results."""
    if registry is None:
        from service.execution.registry import EXECUTOR_REGISTRY as registry  # noqa: N813
    changes = []
    for change in row.changes or []:
        spec = registry.get(change.get("op_type", ""))
        changes.append(
            {
                "id": change.get("id", ""),
                "op_type": change.get("op_type", ""),
                "summary": change.get("summary", ""),
                "status": change.get("status", ""),
                "diff": (change.get("preview") or {}).get("diff", ""),
                "warnings": (change.get("preview") or {}).get("warnings", []),
                "guardrail_violations": change.get("guardrail_violations", []),
                "preview_error": (change.get("preview") or {}).get("error", ""),
                "destructive": bool(spec.destructive) if spec else False,
            }
        )
    return {
        "change_set_id": str(row.id),
        "connector_type": row.connector_type,
        "account_id": row.account_id,
        "account_name": row.account_name,
        "title": row.title,
        "context": row.context,
        "status": row.status,
        "source": row.source,
        "applied_by": row.applied_by,
        "auto_apply_eligible": bool(row.auto_apply_eligible),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "changes": changes,
    }


# ---------------------------------------------------------------------------
# Domain — sync, DB-bound, harness-free
# ---------------------------------------------------------------------------

def _register_executors() -> None:
    """Import side effects: make sure every wave-1 executor is in the registry."""
    import service.execution.ga4_exec  # noqa: F401
    import service.execution.google_ads_exec  # noqa: F401
    import service.execution.gtm_exec  # noqa: F401


def _list_ops_sync(wanted: str, *, user_id: UUID, connector_types: tuple[str, ...]) -> dict:
    from db.session import get_session as db_session
    from service.execution.policy import AUTO_APPLY_ALLOWLIST
    from service.execution.registry import EXECUTOR_REGISTRY
    from service.execution.service import guardrails_for

    ops = [
        {
            "op_type": spec.op_type,
            "connector_type": spec.connector_type,
            "label": spec.label,
            "destructive": spec.destructive,
            "supports_rollback": spec.rollback is not None,
            "may_auto_apply": spec.op_type in AUTO_APPLY_ALLOWLIST,
        }
        for spec in EXECUTOR_REGISTRY.values()
        if spec.connector_type in connector_types
        and (not wanted or spec.connector_type == wanted)
    ]
    rules: dict[str, list[str]] = {}
    with next(db_session()) as db:
        for connector in connector_types:
            if wanted and connector != wanted:
                continue
            found = [g.rule for g in guardrails_for(db, user_id, connector, "") if g.active]
            if found:
                rules[connector] = found
    return {"ops": ops, "guardrails": rules}


def _propose_sync(
    args: dict,
    *,
    user_id: UUID,
    project_id: UUID | None,
    conversation_id: UUID | None,
    agent_type: str,
):
    from db.session import get_session as db_session
    from service.execution.creds import resolve_execution_creds
    from service.execution.service import propose_change_set

    connector_type = str(args.get("connector_type") or "").strip()
    with next(db_session()) as db:
        # The row is card-serialized after this session closes; the
        # activity-log commits inside the service must not expire it.
        db.expire_on_commit = False
        # project_id came membership-checked from the session; the project's
        # connector binding (if any) wins over user rows.
        creds = resolve_execution_creds(
            db, user_id, connector_type, str(args.get("account_id") or ""),
            project_id=project_id,
        )
        if not creds.get("refresh_token"):
            raise ValueError(
                f"No stored credentials for {connector_type}. Ask the user to "
                "connect it (signed in) on the Connections page first."
            )
        return propose_change_set(
            db,
            user_id=user_id,
            connector_type=connector_type,
            account_id=str(args.get("account_id") or ""),
            account_name=str(args.get("account_name") or ""),
            title=str(args.get("title") or "").strip() or "Proposed changes",
            context=str(args.get("context") or ""),
            changes=args.get("changes") or [],
            creds=creds,
            project_id=project_id,
            conversation_id=conversation_id,
            agent_type=agent_type,
            source="agent",
        )


def _status_sync(raw_id: str, *, user_id: UUID) -> dict | None:
    from db.session import get_session as db_session
    from models.execution import ExecutionChangeSet

    with next(db_session()) as db:
        row = db.get(ExecutionChangeSet, UUID(raw_id))
        if row is None or row.user_id != user_id:
            return None
        return change_set_card(row)


def _rollback_sync(raw_id: str, *, user_id: UUID):
    from db.session import get_session as db_session
    from models.execution import ExecutionChangeSet
    from service.execution.creds import resolve_execution_creds
    from service.execution.service import rollback_change_set as rollback_core

    with next(db_session()) as db:
        db.expire_on_commit = False  # card-serialized after the session closes
        row = db.get(ExecutionChangeSet, UUID(raw_id))
        if row is None or row.user_id != user_id:
            return None
        creds = resolve_execution_creds(
            db, user_id, row.connector_type, row.account_id, project_id=row.project_id,
        )
        return rollback_core(db, row, creds, actor="agent")


# ---------------------------------------------------------------------------
# Tool bodies — harness-neutral. Each returns a payload dict; a body never
# raises, because a raised exception ends the agent loop while an error
# payload lets the model read what went wrong and try something else.
# ---------------------------------------------------------------------------

def _error(message: str) -> dict:
    return {"status": "error", "message": message}


def _is_error(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("status") == "error"


async def _emit_card(row, on_change_set: Callable | None) -> dict:
    card = change_set_card(row)
    if on_change_set is not None:
        try:
            await on_change_set(card)
        except Exception:  # noqa: BLE001 — the card is UI sugar, never fatal
            logger.debug("change-set card emit failed", exc_info=True)
    return card


async def _list_ops(
    connector_type: str, *, user_id: UUID, connector_types: tuple[str, ...]
) -> dict:
    wanted = (connector_type or "").strip()
    if wanted and wanted not in connector_types:
        return _error(
            f"Connector {wanted!r} is not available here. Available: {list(connector_types)}"
        )
    try:
        return await asyncio.to_thread(
            _list_ops_sync, wanted, user_id=user_id, connector_types=connector_types
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ListExecutableOps failed", exc_info=True)
        return _error(f"Listing executable ops failed: {exc}")


async def _propose(
    args: dict,
    *,
    user_id: UUID,
    project_id: UUID | None,
    conversation_id: UUID | None,
    agent_type: str,
    connector_types: tuple[str, ...],
    on_change_set: Callable | None,
) -> dict:
    connector_type = str(args.get("connector_type") or "").strip()
    if connector_type not in connector_types:
        return _error(
            f"Connector {connector_type!r} is not available here. Available: {list(connector_types)}"
        )
    changes = args.get("changes") or []
    if not isinstance(changes, list) or not changes:
        return _error("changes must be a non-empty list of {op_type, summary, target, payload}.")

    try:
        row = await asyncio.to_thread(
            _propose_sync, args,
            user_id=user_id, project_id=project_id,
            conversation_id=conversation_id, agent_type=agent_type,
        )
    except KeyError as exc:
        return _error(str(exc.args[0]) if exc.args else str(exc))
    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ProposeChanges failed", exc_info=True)
        return _error(f"Proposing the change set failed: {exc}")

    card = await _emit_card(row, on_change_set)
    auto_applied = row.status in ("applied", "partial") and row.applied_by == "auto"
    payload = dict(card)
    payload["auto_applied"] = auto_applied
    payload["next_step"] = (
        "Applied automatically — report the per-change results to the user."
        if auto_applied
        else "Waiting for the user's approval in the review card — tell them what you "
             "proposed and why, then continue. Do not poll."
    )
    return payload


async def _status(change_set_id: str, *, user_id: UUID) -> dict:
    raw_id = (change_set_id or "").strip()
    try:
        card = await asyncio.to_thread(_status_sync, raw_id, user_id=user_id)
    except ValueError:
        return _error(f"{raw_id!r} is not a valid change set id.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("GetChangeSetStatus failed", exc_info=True)
        return _error(f"Status fetch failed: {exc}")
    return card if card is not None else _error(f"No change set {raw_id!r} for this user.")


async def _rollback(
    change_set_id: str, *, user_id: UUID, on_change_set: Callable | None
) -> dict:
    raw_id = (change_set_id or "").strip()
    try:
        row = await asyncio.to_thread(_rollback_sync, raw_id, user_id=user_id)
    except ValueError:
        return _error(f"{raw_id!r} is not a valid change set id.")
    except Exception as exc:
        from service.execution.service import StateError

        if isinstance(exc, StateError):
            return _error(str(exc))
        logger.warning("RollbackChangeSet failed", exc_info=True)
        return _error(f"Rollback failed: {exc}")
    if row is None:
        return _error(f"No change set {raw_id!r} for this user.")
    return await _emit_card(row, on_change_set)


# ---------------------------------------------------------------------------
# LangChain binder (V1)
# ---------------------------------------------------------------------------

def build_execution_tools_lc(
    *,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    conversation_id: UUID | None = None,
    agent_type: str = "",
    connector_types: tuple[str, ...] = _DEFAULT_CONNECTORS,
    on_change_set: Callable | None = None,
    log_prefix: str = "agent",
) -> list:
    """The four staged-execution tools as LangChain ``StructuredTool``s.

    Returns nothing without a user AND a membership-checked project: acting on
    someone's ad account needs both, and mounting tools that fail when called
    is worse than not mounting them.
    """
    from langchain_core.tools import StructuredTool

    if user_id is None or project_id is None:
        return []
    _register_executors()

    async def list_executable_ops(connector_type: str = "") -> str:
        with tool_span(tool_name="ListExecutableOps", agent_name=log_prefix):
            return json.dumps(
                await _list_ops(
                    connector_type, user_id=user_id, connector_types=connector_types
                ),
                indent=2,
            )

    async def propose_changes(**args: Any) -> str:
        with tool_span(tool_name="ProposeChanges", agent_name=log_prefix):
            return json.dumps(
                await _propose(
                    args,
                    user_id=user_id, project_id=project_id,
                    conversation_id=conversation_id, agent_type=agent_type,
                    connector_types=connector_types, on_change_set=on_change_set,
                ),
                indent=2,
            )

    async def get_change_set_status(change_set_id: str) -> str:
        with tool_span(tool_name="GetChangeSetStatus", agent_name=log_prefix):
            return json.dumps(await _status(change_set_id, user_id=user_id), indent=2)

    async def rollback_change_set(change_set_id: str) -> str:
        with tool_span(tool_name="RollbackChangeSet", agent_name=log_prefix):
            return json.dumps(
                await _rollback(
                    change_set_id, user_id=user_id, on_change_set=on_change_set
                ),
                indent=2,
            )

    return [
        StructuredTool.from_function(
            coroutine=list_executable_ops,
            name="ListExecutableOps",
            description=LIST_OPS_DESCRIPTION,
            args_schema=ListOpsArgs,
        ),
        StructuredTool.from_function(
            coroutine=propose_changes,
            name="ProposeChanges",
            description=PROPOSE_DESCRIPTION,
            args_schema=ProposeChangesArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_change_set_status,
            name="GetChangeSetStatus",
            description=STATUS_DESCRIPTION,
            args_schema=ChangeSetArgs,
        ),
        StructuredTool.from_function(
            coroutine=rollback_change_set,
            name="RollbackChangeSet",
            description=ROLLBACK_DESCRIPTION,
            args_schema=ChangeSetArgs,
        ),
    ]


# ---------------------------------------------------------------------------
# Claude Agent SDK binder (V3)
# ---------------------------------------------------------------------------

def build_execution_mcp_server(
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    conversation_id: UUID | None = None,
    agent_type: str = "",
    connector_types: tuple[str, ...] = _DEFAULT_CONNECTORS,
    on_change_set=None,  # async (card: dict) -> None — in-chat change-set card emit
):
    """Build the ``duct_execute`` MCP server scoped to one user + project.

    ``user_id`` comes from the session's authenticated user; ``project_id`` from
    the membership-checked artifact scope (routes.agents stamps it only after
    verifying the caller belongs to the project) — same trust chain as the
    artifact tools.
    """
    from claude_agent_sdk import create_sdk_mcp_server, tool

    _register_executors()

    def _text(payload: dict) -> dict:
        body = {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}
        # is_error=True keeps the agent loop alive so the model can react/retry.
        if _is_error(payload):
            body["is_error"] = True
        return body

    @tool(
        name="ListExecutableOps",
        description=LIST_OPS_DESCRIPTION,
        input_schema=ListOpsArgs.model_json_schema(),
    )
    async def list_executable_ops(args: dict) -> dict:
        return _text(
            await _list_ops(
                str(args.get("connector_type") or ""),
                user_id=user_id, connector_types=connector_types,
            )
        )

    @tool(
        name="ProposeChanges",
        description=PROPOSE_DESCRIPTION,
        input_schema=ProposeChangesArgs.model_json_schema(),
    )
    async def propose_changes(args: dict) -> dict:
        return _text(
            await _propose(
                args,
                user_id=user_id, project_id=project_id,
                conversation_id=conversation_id, agent_type=agent_type,
                connector_types=connector_types, on_change_set=on_change_set,
            )
        )

    @tool(
        name="GetChangeSetStatus",
        description=STATUS_DESCRIPTION,
        input_schema=ChangeSetArgs.model_json_schema(),
    )
    async def get_change_set_status(args: dict) -> dict:
        return _text(await _status(str(args.get("change_set_id") or ""), user_id=user_id))

    @tool(
        name="RollbackChangeSet",
        description=ROLLBACK_DESCRIPTION,
        input_schema=ChangeSetArgs.model_json_schema(),
    )
    async def rollback_change_set(args: dict) -> dict:
        return _text(
            await _rollback(
                str(args.get("change_set_id") or ""),
                user_id=user_id, on_change_set=on_change_set,
            )
        )

    return create_sdk_mcp_server(
        "duct_execute",
        tools=[list_executable_ops, propose_changes, get_change_set_status, rollback_change_set],
    )
