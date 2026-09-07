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
    # The bus delivers {event: {id, type, properties}}; everything lives in properties.
    evt = event.get("event") or event
    props = evt.get("properties") or evt

    # ponytail: runtime sends type="permission.asked" with the tool as
    # properties["permission"]; the SDK types.gen.d.ts wrongly declares
    # permission.updated with properties["type"]. Accept all three, mirror the plugin.
    req_id = props.get("id") or props.get("requestID") or props.get("permissionID")
    if not req_id:
        raise ValueError("Permission event missing id field")
    session_id = props.get("sessionID") or props.get("sessionId") or ""
    # tool = permission (runtime) ?? tool ?? type (si no es tipo de evento)
    tool = props.get("permission")
    if not isinstance(tool, str):
        tool = props.get("tool")
    if not isinstance(tool, str):
        cand = props.get("type")
        tool = cand if isinstance(cand, str) and not cand.startswith("permission.") else "unknown"
    patterns = props.get("patterns") or props.get("pattern") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    metadata = props.get("metadata") or {}
    return PermissionRequest(
        id=req_id,
        session_id=session_id,
        tool=tool,
        patterns=patterns,
        metadata=metadata,
        timestamp=time.time(),
    )