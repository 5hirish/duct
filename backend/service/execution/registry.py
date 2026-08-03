"""Executor registry — the strategy table for staged execution.

An executor owns one `op_type` (e.g. ``google_ads.add_negative_keywords``) and
provides three callables sharing the signature ``(change: dict, creds: dict) -> dict``:

- ``preview(change, creds)`` — read-only. Returns a dry-run rendering: the
  human-readable diff plus the raw payload that *would* be sent. May fetch the
  current entity state to snapshot into ``change["current"]``.
- ``apply(change, creds)`` — performs the mutation. Returns a result dict; put
  anything needed to undo under ``result["rollback"]``.
- ``rollback(change, creds)`` — optional. Reverts an applied change using
  ``change["result"]["rollback"]``.

``change`` is one element of ``ExecutionChangeSet.changes``; ``creds`` is the
per-request BYO credential dict (refresh_token, developer_token,
login_customer_id, client_id, client_secret) — never read from env here, the
route resolves them.

Executors must raise ``ValueError`` for bad input/credentials (→ 422 upstream)
and ``RuntimeError`` for upstream API failures (→ recorded on the change).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

ExecutorFn = Callable[[dict, dict], dict]


@dataclass(frozen=True)
class ExecutorSpec:
    op_type: str
    connector_type: str
    label: str
    preview: ExecutorFn
    apply: ExecutorFn
    rollback: ExecutorFn | None = None
    # True when the mutation is destructive/irreversible without the rollback
    # handle — surfaced in the review UI.
    destructive: bool = False


EXECUTOR_REGISTRY: dict[str, ExecutorSpec] = {}


def register_executor(spec: ExecutorSpec) -> None:
    EXECUTOR_REGISTRY[spec.op_type] = spec


def get_executor(op_type: str) -> ExecutorSpec:
    try:
        return EXECUTOR_REGISTRY[op_type]
    except KeyError as exc:
        raise KeyError(f"Unknown execution op_type: {op_type!r}") from exc


def executors_for_connector(connector_type: str) -> list[ExecutorSpec]:
    return [s for s in EXECUTOR_REGISTRY.values() if s.connector_type == connector_type]
