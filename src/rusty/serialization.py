from __future__ import annotations

import json
from typing import Any


def json_object(value: Any) -> dict[str, Any]:
    """Decode a stored JSON object, returning an empty object for legacy invalid data."""

    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
