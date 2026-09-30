"""The Google Ads brief leaves ``to_dict`` holding plain values, not enum members.

``asdict`` keeps the schema's ``StrEnum`` members, and a ``StrEnum`` compares
equal to its string, so an equality check on the payload cannot tell whether
the conversion ran. These assert on types. Nothing exercised ``_json_safe`` or
``GoogleAdsBrief.to_dict`` before, so the helper's pass-through cases are pinned
too: it is not a JSON encoder, and a caller expecting a ``datetime`` to come
back as a string would be wrong.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from service.google.brief import build_brief, demo_raw_payload
from service.google.schema import ActionType, _json_safe


class _Rank(Enum):
    FIRST = 1


def _values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _values(item)
    else:
        yield value


def test_demo_brief_to_dict_carries_no_enum_members():
    payload = build_brief(demo_raw_payload("google_ads")).to_dict()

    assert [v for v in _values(payload) if isinstance(v, Enum)] == []
    action = payload["campaigns"][0]["action"]
    assert type(action) is str and action in set(ActionType)


def test_json_safe_swaps_enums_in_nested_dicts_and_lists():
    out = _json_safe({"action": ActionType.PAUSE, "rows": [{"rank": _Rank.FIRST}]})

    assert out == {"action": "pause", "rows": [{"rank": 1}]}
    assert type(out["action"]) is str
    assert type(out["rows"][0]["rank"]) is int


def test_json_safe_returns_other_values_untouched():
    for value in (
        datetime(2026, 9, 30, tzinfo=timezone.utc),
        uuid4(),
        Decimal("1.50"),
        (ActionType.PAUSE,),
        None,
    ):
        assert _json_safe({"v": value})["v"] is value
