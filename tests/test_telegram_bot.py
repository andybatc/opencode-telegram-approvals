from bridger.models import PermissionRequest
from bridger.telegram_bot import format_request


def test_format_request_contains_key_fields():
    req = PermissionRequest(
        id="req-abc",
        session_id="sess-123",
        tool="bash",
        patterns=["*.py"],
        metadata={"command": "ls -la", "cwd": "/tmp"},
        timestamp=1234567890.0,
    )
    text = format_request(req)
    assert "bash" in text
    assert "req-abc" in text
    assert "sess-123" in text
    assert "ls -la" in text


def test_format_request_patterns_and_defaults():
    req = PermissionRequest(
        id="req-xyz",
        session_id="sess-999",
        tool="read",
        patterns=[],
        metadata={},
        timestamp=1234567890.0,
    )
    text = format_request(req)
    assert "(none)" in text
    assert "read" in text
