"""
push_payloads.py
────────────────
Shared helpers for consistent push-notification payload schema.
"""

from datetime import datetime, timezone
from typing import Optional


def build_push_data(
    *,
    event: str,
    url: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    role: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    data = {
        "event": event,
        "url": url,
        "entity_type": entity_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if entity_id is not None:
        data["entity_id"] = str(entity_id)
    if role:
        data["role"] = role
    if extra:
        for k, v in extra.items():
            data[k] = str(v)
    return data
