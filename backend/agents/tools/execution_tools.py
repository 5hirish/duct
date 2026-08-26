"""Staged-execution MCP tools — agents propose, humans approve.

Mounted as the ``duct_execute`` in-process MCP server for project-scoped agent
sessions. The tool surface is deliberately asymmetric:

- ``ProposeChanges`` stages a change set through the same service core as the
  HTTP route (preview + guardrails + autonomy policy). Reversible,
  allowlisted, guardrail-clean sets auto-apply when the project's autonomy
  level is ``assisted``; everything else waits for a human.
- ``RollbackChangeSet`` exists as the safe escape hatch.
- There is **no approve or apply tool** — approval is human-only by
  construction (service/execution/policy.py). An agent cannot talk itself past
  the review gate.

DB access runs in ``asyncio.to_thread`` (sync SQLModel sessions) so tool calls
never block the SSE event loop; executor previews/applies do network I/O and
run in the same thread. Credentials resolve from the user's stored encrypted
connector rows → server env (service/execution/creds.py) — agents never see
or pass credentials.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated
from uuid import UUID

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONNECTORS = ("google_ads", "ga4", "gtm")


def _text(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def _err(message: str) -> dict:
    # is_error=True keeps the agent loop alive so the model can react/retry.
    return {
        "content": [{"type": "text", "text": json.dumps({"status": "error", "message": message})}],
        "is_error": True,
    }


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


def build_execution_mcp_server(
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    conversation_id: UUID | None = None,
    agent_type: str = "",
    connector_types: tuple[str, ...] = _DEFAULT_CONNECTORS,
    on_change_set=None,  # async (card: dict) -> None — in-chat change-set card emit
) -> McpSdkServerConfig:
    """Build the ``duct_execute`` MCP server scoped to one user + project.

    ``user_id`` comes from the session's authenticated user;``project_id`` from
    the membership-checked artifact scope (routes.agents stamps it only after
    verifying the caller belongs to the project) — same trust chain as the
    artifact tools.
    """
    # Registration side effects — make sure every wave-1 executor is present.
    import service.execution.ga4_exec  # noqa: F401
    import service.execution.google_ads_exec  # noqa: F401
    import service.execution.gtm_exec  # noqa: F401

    async def _emit_card(row) -> dict:
        card = change_set_card(row)
        if on_change_set is not None:
            try:
                await on_change_set(card)
            except Exception:  # noqa: BLE001 — the card is UI sugar, never fatal
                logger.debug("change-set card emit failed", exc_info=True)
        return card

    @tool(
        name="ListExecutableOps",
        description=(
            "List the operations you can propose as staged change sets — op_type, "
            "connector, whether it is destructive, whether it can be rolled back — "
            "plus the account's active guardrail rules (invariants you must respect). "
            "Call this before your first ProposeChanges to see what is executable."
        ),
        input_schema={
            "connector_type": Annotated[
                str, "Filter by connector ('google_ads', 'ga4', 'gtm'). Empty = all available."
            ],
        },
    )
    async def list_executable_ops(args: dict) -> dict:
        wanted = (args.get("connector_type") or "").strip()
        if wanted and wanted not in connector_types:
            return _err(f"Connector {wanted!r} is not available here. Available: {list(connector_types)}")

        def _query() -> dict:
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

        try:
            payload = await asyncio.to_thread(_query)
        except Exception as exc:  # noqa: BLE001
            return _err(f"Listing executable ops failed: {exc}")
        return _text(payload)

    @tool(
        name="ProposeChanges",
        description=(
            "Propose a staged change set against the user's connected account. Every "
            "change is previewed (dry-run diff + current-state snapshot) and checked "
            "against the account's guardrails before anything is stored. THE CONTRACT: "
            "destructive operations (GTM publish, GA4 archive/unlink) ALWAYS wait for "
            "explicit human approval in the review UI — you cannot apply them, and no "
            "tool exists that approves a change set. Reversible, guardrail-clean, "
            "non-destructive changes may auto-apply only when the user has set this "
            "project's autonomy to 'assisted'. The result tells you what happened: "
            "status 'proposed' = waiting for the user's review (tell them, then move "
            "on — do not poll); status 'applied' with applied_by 'auto' = done, report "
            "the results. Always explain WHY in `context` — the user reads it in the "
            "review card."
        ),
        input_schema={
            "connector_type": Annotated[str, "Connector to execute against: 'google_ads', 'ga4', or 'gtm'."],
            "account_id": Annotated[
                str,
                "Account identifier: Google Ads customer id, GA4 property id, or GTM "
                "account id. May be empty when the target paths carry it.",
            ],
            "account_name": Annotated[str, "Human-readable account name for the review card. Optional."],
            "title": Annotated[str, "Short imperative title for the change set (e.g. 'Add 12 negative keywords')."],
            "context": Annotated[
                str,
                "Why these changes: the finding or reasoning behind them and the expected "
                "impact. Shown to the user in the review card.",
            ],
            "changes": Annotated[
                list[dict],
                "List of changes, each {op_type, summary, target: {...}, payload: {...}}. "
                "See ListExecutableOps for op_types; target/payload shapes follow each "
                "op's documented fields (e.g. google_ads.add_negative_keywords needs "
                "target.customer_id + target.campaign_id + payload.keywords).",
            ],
        },
    )
    async def propose_changes(args: dict) -> dict:
        connector_type = (args.get("connector_type") or "").strip()
        if connector_type not in connector_types:
            return _err(
                f"Connector {connector_type!r} is not available here. Available: {list(connector_types)}"
            )
        changes = args.get("changes") or []
        if not isinstance(changes, list) or not changes:
            return _err("changes must be a non-empty list of {op_type, summary, target, payload}.")

        def _propose():
            from db.session import get_session as db_session
            from service.execution.creds import resolve_execution_creds
            from service.execution.service import propose_change_set

            with next(db_session()) as db:
                # The row is card-serialized after this session closes; the
                # activity-log commits inside the service must not expire it.
                db.expire_on_commit = False
                creds = resolve_execution_creds(db, user_id, connector_type, args.get("account_id") or "")
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
                    changes=changes,
                    creds=creds,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    agent_type=agent_type,
                    source="agent",
                )

        try:
            row = await asyncio.to_thread(_propose)
        except KeyError as exc:
            detail = str(exc.args[0]) if exc.args else str(exc)
            return _err(detail)
        except ValueError as exc:
            return _err(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.warning("ProposeChanges failed", exc_info=True)
            return _err(f"Proposing the change set failed: {exc}")

        card = await _emit_card(row)
        auto_applied = row.status in ("applied", "partial") and row.applied_by == "auto"
        payload = dict(card)
        payload["auto_applied"] = auto_applied
        payload["next_step"] = (
            "Applied automatically (assisted autonomy) — report the per-change results to the user."
            if auto_applied
            else "Waiting for the user's approval in the review card — tell them what you proposed and why, then continue. Do not poll."
        )
        return _text(payload)

    @tool(
        name="GetChangeSetStatus",
        description=(
            "Fetch the current status of one change set you proposed earlier — overall "
            "status (proposed/approved/applied/partial/failed/rejected/rolled_back) "
            "plus per-change results and rollback availability. Use it when the user "
            "says they approved/applied something, or before proposing a rollback. "
            "Do not poll it while waiting for approval."
        ),
        input_schema={
            "change_set_id": Annotated[str, "The change set id (UUID) from ProposeChanges."],
        },
    )
    async def get_change_set_status(args: dict) -> dict:
        raw_id = (args.get("change_set_id") or "").strip()

        def _query():
            from db.session import get_session as db_session
            from models.execution import ExecutionChangeSet

            with next(db_session()) as db:
                row = db.get(ExecutionChangeSet, UUID(raw_id))
                if row is None or row.user_id != user_id:
                    return None
                return change_set_card(row)

        try:
            card = await asyncio.to_thread(_query)
        except ValueError:
            return _err(f"{raw_id!r} is not a valid change set id.")
        except Exception as exc:  # noqa: BLE001
            return _err(f"Status fetch failed: {exc}")
        if card is None:
            return _err(f"No change set {raw_id!r} for this user.")
        return _text(card)

    @tool(
        name="RollbackChangeSet",
        description=(
            "Revert an applied change set using the rollback handles recorded at apply "
            "time — the safe escape hatch when an applied change turns out wrong "
            "(including auto-applied ones). Only works on applied/partial sets; "
            "changes whose op has no rollback are reported, not silently skipped."
        ),
        input_schema={
            "change_set_id": Annotated[str, "The change set id (UUID) to roll back."],
        },
    )
    async def rollback_change_set(args: dict) -> dict:
        raw_id = (args.get("change_set_id") or "").strip()

        def _rollback():
            from db.session import get_session as db_session
            from models.execution import ExecutionChangeSet
            from service.execution.creds import resolve_execution_creds
            from service.execution.service import rollback_change_set as rollback_core

            with next(db_session()) as db:
                db.expire_on_commit = False  # card-serialized after the session closes
                row = db.get(ExecutionChangeSet, UUID(raw_id))
                if row is None or row.user_id != user_id:
                    return None
                creds = resolve_execution_creds(db, user_id, row.connector_type, row.account_id)
                return rollback_core(db, row, creds, actor="agent")

        try:
            row = await asyncio.to_thread(_rollback)
        except ValueError:
            return _err(f"{raw_id!r} is not a valid change set id.")
        except Exception as exc:
            from service.execution.service import StateError

            if isinstance(exc, StateError):
                return _err(str(exc))
            logger.warning("RollbackChangeSet failed", exc_info=True)
            return _err(f"Rollback failed: {exc}")
        if row is None:
            return _err(f"No change set {raw_id!r} for this user.")
        card = await _emit_card(row)
        return _text(card)

    return create_sdk_mcp_server(
        "duct_execute",
        tools=[list_executable_ops, propose_changes, get_change_set_status, rollback_change_set],
    )
