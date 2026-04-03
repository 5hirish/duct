import json
from datetime import datetime


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

