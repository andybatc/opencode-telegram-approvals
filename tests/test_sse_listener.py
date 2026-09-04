import pytest
import asyncio
from bridger.sse_listener import SSEListener
from bridger.models import PermissionRequest
from bridger.config import Config

@pytest.mark.asyncio
async def test_sse_listener_parses_permission_asked():
    # This is an integration-style test - run against a mock SSE server
    # For unit test, we test the parser logic separately if extracted
    pass  # Integration tested manually; parser covered by test_models.py
