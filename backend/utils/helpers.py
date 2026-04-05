import json
from datetime import datetime
from enum import Enum
from typing import Any


def json_safe(value: Any) -> Any:
    """Recursively normalize values for JSON-ready structures (e.g. after ``dataclasses.asdict``).

    Maps ``Enum`` members to their ``.value``; recurses into ``dict`` and ``list``.
    """

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def safe_get(obj, *keys):
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            try:
                obj = getattr(obj, key, None)
            except Exception:
                return None
        if obj is None:
            return None
    return obj


def get_enum_from_string(enum_class, value):
    try:
        return enum_class[value]
    except KeyError:
        return None


def serialize_for_json(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, '__dict__'):
        return {k: serialize_for_json(v) for k, v in obj.__dict__.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif hasattr(obj, 'model_dump'):  # For pydantic models
        return serialize_for_json(obj.model_dump())
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)
    
def json_dumps(obj):
    return json.dumps(obj, default=serialize_for_json)
        
def datetime_to_iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt

def to_dict(obj):
    return serialize_for_json(obj)

