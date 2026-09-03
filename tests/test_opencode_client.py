# tests/test_opencode_client.py
import pytest
import httpx
import json
from bridger.opencode_client import OpencodeClient


@pytest.mark.asyncio
async def test_reply_success(httpx_mock):
    httpx_mock.add_response(method="POST", url="http://127.0.0.1:4096/permission/req-123/reply", status_code=200)
    client = OpencodeClient("http://127.0.0.1:4096", "/workspace")
    await client.reply("req-123", "once")
    req = httpx_mock.get_request()
    assert req.method == "POST"
    assert req.url.path == "/permission/req-123/reply"
    assert req.headers["x-opencode-directory"] == "/workspace"
    assert json.loads(req.content) == {"reply": "once"}


@pytest.mark.asyncio
async def test_reply_retry_on_5xx(httpx_mock):
    httpx_mock.add_response(method="POST", status_code=500)
    httpx_mock.add_response(method="POST", status_code=200)
    client = OpencodeClient("http://127.0.0.1:4096", "/workspace")
    await client.reply("req-123", "reject")
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_reply_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timeout"))
    httpx_mock.add_exception(httpx.TimeoutException("timeout"))
    client = OpencodeClient("http://127.0.0.1:4096", "/workspace", timeout=0.01)
    with pytest.raises(httpx.TimeoutException):
        await client.reply("req-123", "once")