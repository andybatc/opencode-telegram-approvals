# tests/test_opencode_client.py
import pytest
import httpx
import json
from bridger.opencode_client import OpencodeClient
from bridger.config import Config


def make_config(**overrides) -> Config:
    defaults = {
        "telegram_bot_token": "test-token",
        "telegram_chat_id": "test-chat",
        "opencode_server_url": "http://127.0.0.1:4096",
        "opencode_working_dir": "/workspace",
        "bridger_timeout": 10,
        "bridger_log_level": "INFO",
    }
    defaults.update(overrides)
    return Config(**defaults)


@pytest.mark.asyncio
async def test_reply_success(httpx_mock):
    httpx_mock.add_response(method="POST", url="http://127.0.0.1:4096/permission/req-123/reply", status_code=200)
    config = make_config()
    client = OpencodeClient(config)
    await client.reply("req-123", "once", "/workspace")
    req = httpx_mock.get_request()
    assert req.method == "POST"
    assert req.url.path == "/permission/req-123/reply"
    assert req.headers["x-opencode-directory"] == "/workspace"
    assert json.loads(req.content) == {"reply": "once"}


@pytest.mark.asyncio
async def test_reply_retry_on_5xx(httpx_mock):
    httpx_mock.add_response(method="POST", status_code=500)
    httpx_mock.add_response(method="POST", status_code=200)
    config = make_config()
    client = OpencodeClient(config)
    await client.reply("req-123", "reject", "/workspace")
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_reply_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timeout"))
    config = make_config(bridger_timeout=0.01)
    client = OpencodeClient(config)
    with pytest.raises(httpx.TimeoutException):
        await client.reply("req-123", "once", "/workspace")


@pytest.mark.asyncio
async def test_reply_invalid_value(httpx_mock):
    config = make_config()
    client = OpencodeClient(config)
    with pytest.raises(ValueError, match="Invalid reply"):
        await client.reply("req-123", "invalid", "/workspace")
