"""Fake chat models that drive the real V1 agent loop — no API key, no network.

Four test modules each carried their own copy of ``ToolCallingFake``, and two
of them the failing variants beside it. One copy here, so a change to how the
loop is faked (a new failure shape, a provider's new stop marker) lands once.

The property that matters, and the one the stock LangChain fakes lack: they
raise ``NotImplementedError`` on ``bind_tools``, which every agent factory
calls. These accept it and ignore the schema, so a canned response can carry
``tool_calls`` and the harness runs the real tool.

``FakeMessagesListChatModel`` *cycles* its responses rather than exhausting
them: a two-turn test needs two entries, and a turn that must fail needs
``RaisingFake`` or ``FlakyFake`` rather than an empty list.
"""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


class ToolCallingFake(FakeMessagesListChatModel):
    """A fake that accepts ``bind_tools``, so it can drive a real agent loop."""

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002 - the fake ignores the schema
        return self


class RaisingFake(ToolCallingFake):
    """Answers the first call, then fails — the "one bad turn" case."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if getattr(self, "_used", False):
            raise RuntimeError("provider blew up")
        self._used = True
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class RateLimitError(Exception):
    """Named like the provider SDK's, which is how the classifier knows it."""


class AuthenticationError(Exception):
    """Ditto — a rejected key, which must not be retried."""


class FlakyFake(ToolCallingFake):
    """Fails ``failures`` times with ``exc``, then answers — a provider having a moment."""

    failures: int = 2
    exc: type[Exception] = RateLimitError

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        calls = getattr(self, "_calls", 0)
        self._calls = calls + 1
        if calls < self.failures:
            raise self.exc("429 rate limited")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def fake_llm(*responses: str, cls: type[ToolCallingFake] = ToolCallingFake) -> ToolCallingFake:
    """A fake that replies with ``responses`` in order, one per model call."""
    return cls(responses=[AIMessage(content=r) for r in responses])


def tool_names(agent) -> set[str]:
    """Tool names bound into a compiled agent graph.

    Walks the graph rather than asking the runner, so a tool the runner
    *believes* it mounted but the harness dropped shows up as absent.
    """
    for node in agent.nodes.values():
        seq = getattr(getattr(node, "bound", None), "steps", None) or []
        for step in seq:
            if hasattr(step, "tools_by_name"):
                return set(step.tools_by_name)
    # Fall back to the ToolNode's registry wherever it lives.
    tool_node = agent.nodes.get("tools")
    inner = getattr(tool_node, "bound", tool_node)
    return set(getattr(inner, "tools_by_name", {}))


class ContextOverflowError(Exception):
    """The provider's "prompt is too long" — LangChain's name for it, which is
    how the classifier knows it."""


class OverflowFake(ToolCallingFake):
    """Rejects the request as too long `overflows` times, the way a provider
    does when the summariser's estimate ran behind the real count; answers
    otherwise — including the summary an emergency compaction asks it for.
    Set `_overflowed = -1` to let one turn through before the overflows start."""

    overflows: int = 1

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        # The summary request carries the summariser's own prompt; it has to
        # succeed or no compaction can happen.
        is_summary = any("extract" in str(getattr(m, "content", "")).lower() for m in messages)
        if not is_summary and getattr(self, "_overflowed", 0) < self.overflows:
            self._overflowed = getattr(self, "_overflowed", 0) + 1
            if self._overflowed > 0:
                raise ContextOverflowError("prompt is too long: 213000 tokens > 200000 maximum")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


# ---------------------------------------------------------------------------
# Google Ads — the real protos, with the transport taken out
# ---------------------------------------------------------------------------
#
# The eight Google Ads executors mutate a customer's live ad account, and until
# this fake existed none of their apply or rollback paths had ever run: building
# a `GoogleAdsClient` performs an OAuth refresh against Google *at construction
# time* (`load_from_dict` → `oauth2.get_credentials` → `credentials.refresh`), so
# there was no offline way in.
#
# The temptation is a stub client made of attribute bags. That fake passes while
# the field is misspelled, the enum is not a member, and the update mask names a
# path the API would reject — which is the entire class of bug worth catching
# here. So this keeps everything the library computes locally (`get_type`,
# `enums`, `copy_from`, and the GAPIC path helpers, all pure) and replaces only
# the part that talks: `get_service`. A test that names a field wrong fails on
# the proto, the way production would fail on the wire.

from typing import Any, NamedTuple  # noqa: E402


class RecordedMutation(NamedTuple):
    """One mutate_* call an executor made, as the API would have received it."""

    method: str
    customer_id: str
    operations: list[Any]


class _MutateResult:
    def __init__(self, resource_name: str) -> None:
        self.resource_name = resource_name


class _MutateResponse:
    """Only ``.results[i].resource_name`` is ever read, so only that is built.

    The real response protos would add fidelity nowhere — no executor branches
    on anything else in them, and mapping eight methods to eight response types
    would be ceremony that tests nothing.
    """

    def __init__(self, resource_names: list[str]) -> None:
        self.results = [_MutateResult(name) for name in resource_names]


class FakeAdsService:
    """A Google Ads ``*Service`` whose mutations are recorded, not sent.

    Path helpers (``campaign_path`` and friends) delegate to the real generated
    client: they are static string formatting, and a hand-written copy is one
    more thing to drift from ``customers/{cid}/adGroupCriteria/{ag}~{crit}``.
    """

    def __init__(self, name: str, client: "FakeAdsClient") -> None:
        self._name = name
        self._client = client

    def __getattr__(self, attr: str):
        if attr.startswith("mutate_"):
            return lambda customer_id, operations, **kw: self._client._mutate(
                self._name, attr, customer_id, list(operations)
            )
        if attr.endswith("_path"):
            return getattr(_real_ads_service_class(self._name), attr)
        raise AttributeError(f"{self._name} has no attribute {attr!r} (add it to FakeAdsService)")


def _real_ads_service_class(name: str):
    """``CampaignService`` → the generated ``CampaignServiceClient`` class."""
    import importlib
    import re

    from google.ads.googleads.client import _DEFAULT_VERSION

    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    module = importlib.import_module(
        f"google.ads.googleads.{_DEFAULT_VERSION}.services.services.{snake}"
    )
    return getattr(module, f"{name}Client")


class FakeAdsClient:
    """Stands in for ``GoogleAdsClient`` in an executor, minus the network.

    ``rows`` is what the next ``_run_query`` should return — set it directly, or
    pass ``query_rows`` per test. ``mutations`` is what the executor sent, in
    order, for a test to assert on. ``fail_with`` makes the next mutate raise,
    which is how the "upstream rejected it" branch gets exercised.
    """

    def __init__(
        self,
        rows: list[Any] | None = None,
        *,
        resource_names: list[str] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        from google.ads.googleads.client import _EnumGetter

        self.version = None
        self.use_proto_plus = True
        self.enums = _EnumGetter(self)
        self.rows = list(rows or [])
        self.mutations: list[RecordedMutation] = []
        self.fail_with = fail_with
        self._resource_names = resource_names

    # The three the library computes locally — reused, not reimplemented.
    from google.ads.googleads.client import GoogleAdsClient as _Real

    _get_api_services_by_version = _Real._get_api_services_by_version
    get_type = _Real.get_type
    copy_from = staticmethod(_Real.copy_from)
    del _Real

    def get_service(self, name: str, **kwargs) -> FakeAdsService:
        return FakeAdsService(name, self)

    def _mutate(self, service: str, method: str, customer_id: str, operations: list) -> _MutateResponse:
        self.mutations.append(RecordedMutation(method, str(customer_id), operations))
        if self.fail_with is not None:
            raise self.fail_with
        names = self._resource_names
        if names is None:
            names = [f"customers/{customer_id}/{service}/{i}" for i in range(len(operations) or 1)]
        return _MutateResponse(names)

    def row(self, **fields: Any):
        """A ``GoogleAdsRow`` from dotted paths: ``row(**{"campaign.id": 5})``.

        Enum fields accept their name as a string — proto-plus resolves it — so
        a test reads as the API docs do, and a name that is not a member raises
        here rather than passing silently.
        """
        row = self.get_type("GoogleAdsRow")
        for path, value in fields.items():
            target = row
            *parents, leaf = path.split(".")
            for part in parents:
                target = getattr(target, part)
            setattr(target, leaf, value)
        return row


# ---------------------------------------------------------------------------
# Google Discovery APIs (GA4 Admin, and anything else built by `discovery.build`)
# ---------------------------------------------------------------------------
#
# `googleapiclient.discovery.build()` fetches the API's discovery document over
# the network before it returns a client, so an executor built on one cannot be
# reached offline at all — the same wall `FakeAdsClient` exists to get past.
#
# The shape it fakes is the fluent chain: `service.properties().keyEvents()
# .list(parent=...).execute()`. Collections are the links with no arguments;
# the named verbs below are the terminals that carry kwargs and return a
# request. Responses are keyed by the dotted path so a test declares what the
# API answers rather than assembling a nest of stub classes.
#
# The GTM fake in `test_execution_policy.py` is deliberately *not* replaced by
# this: it keeps container state (tags by name, incrementing version ids) so it
# can answer a read that follows a write. This one records calls and replays
# canned answers, which is all the GA4 executors need. Two different jobs.

_DISCOVERY_TERMINALS = frozenset(
    {"list", "get", "create", "delete", "patch", "update", "batchGet", "archive"}
)


class _DiscoveryRequest:
    def __init__(self, service: "FakeDiscoveryService", path: str, kwargs: dict):
        self._service = service
        self._path = path
        self._kwargs = kwargs

    def execute(self, **_):
        self._service.calls.append((self._path, self._kwargs))
        answer = self._service.responses.get(self._path, {})
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return answer(**self._kwargs)
        return answer


class FakeDiscoveryService:
    """Stands in for a `discovery.build()` client.

    ``responses`` maps a dotted call path — ``"properties.keyEvents.list"`` — to
    the body ``execute()`` should return, an ``Exception`` it should raise, or a
    callable taking the request kwargs. ``calls`` is every ``execute()`` that
    happened, in order, as ``(path, kwargs)``.
    """

    def __init__(self, responses: dict[str, Any] | None = None, _path: str = "") -> None:
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, dict]] = []
        self._path = _path

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        path = f"{self._path}.{name}" if self._path else name

        def call(**kwargs):
            if name in _DISCOVERY_TERMINALS:
                return _DiscoveryRequest(self, path, kwargs)
            if kwargs:
                raise AssertionError(
                    f"{path}() took arguments but is not a known terminal verb; "
                    f"add it to _DISCOVERY_TERMINALS if the API has one."
                )
            child = FakeDiscoveryService(_path=path)
            # The root owns the script and the log, so a chain any depth down
            # reads the same responses and appends to the same call list.
            child.responses = self.responses
            child.calls = self.calls
            return child

        return call
