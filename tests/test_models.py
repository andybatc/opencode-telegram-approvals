import time
from bridger.models import PermissionRequest, normalize_permission_event


def test_permission_request_dataclass():
    req = PermissionRequest(
        id="req-123",
        session_id="sess-456",
        tool="bash",
        patterns=["*.py"],
        metadata={"command": "ls -la", "cwd": "/home/user"},
        timestamp=time.time(),
    )
    assert req.id == "req-123"
    assert req.tool == "bash"


def test_normalize_event_with_id_field():
    event = {
        "type": "permission.asked",
        "id": "req-123",
        "sessionID": "sess-456",
        "tool": "bash",
        "patterns": ["*.py"],
        "metadata": {"command": "ls", "cwd": "/tmp"},
    }
    req = normalize_permission_event(event)
    assert req.id == "req-123"
    assert req.session_id == "sess-456"
    assert req.tool == "bash"
    assert req.patterns == ["*.py"]
    assert req.metadata == {"command": "ls", "cwd": "/tmp"}


def test_normalize_event_with_requestID_field():
    event = {
        "type": "permission.asked",
        "requestID": "req-789",
        "sessionID": "sess-111",
        "tool": "edit",
        "patterns": ["main.py"],
        "metadata": {"file": "main.py"},
    }
    req = normalize_permission_event(event)
    assert req.id == "req-789"
    assert req.session_id == "sess-111"


def test_normalize_event_with_permissionID_field():
    event = {
        "type": "permission.asked",
        "permissionID": "req-999",
        "sessionID": "sess-222",
        "tool": "read",
        "patterns": ["*.md"],
        "metadata": {},
    }
    req = normalize_permission_event(event)
    assert req.id == "req-999"
    assert req.session_id == "sess-222"