from dataclasses import dataclass
from typing import Any
import time


@dataclass
class PermissionRequest:
    id: str
    session_id: str
    tool: str
    patterns: list[str]
    metadata: dict[str, Any]
    timestamp: float


def normalize_permission_event(event: dict[str, Any]) -> PermissionRequest:
    # opencode may send id, requestID, or permissionID — try all
    req_id = event.get("id") or event.get("requestID") or event.get("permissionID")
    if not req_id:
        raise ValueError("Permission event missing id field")
    session_id = event.get("sessionID") or event.get("sessionId") or ""
    tool = event.get("tool") or ""
    patterns = event.get("patterns") or []
    metadata = event.get("metadata") or {}
    return PermissionRequest(
        id=req_id,
        session_id=session_id,
        tool=tool,
        patterns=patterns,
        metadata=metadata,
        timestamp=time.time(),
    )