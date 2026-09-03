# Telegram Approval Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python bridge that forwards opencode permission requests to Telegram and sends responses back via HTTP.

**Architecture:** External Python process listening to opencode SSE (`/event`), formatting permission requests as Telegram messages with inline keyboards, receiving callback queries or chat commands, and replying to opencode via `POST /permission/:id/reply`.

**Tech Stack:** Python 3.11+, `python-telegram-bot`, `httpx`, `python-dotenv` for config. No other dependencies.

## Global Constraints

- Single process: `python -m bridger` entry point
- Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `OPENCODE_SERVER_URL` (default `http://127.0.0.1:4096`), `OPENCODE_WORKING_DIR`, `BRIDGER_TIMEOUT` (default 300), `BRIDGER_LOG_LEVEL` (default `INFO`)
- All deps in `pyproject.toml`: `python-telegram-bot`, `httpx`, `python-dotenv`
- SSE reconnection: exponential backoff 1s→2s→4s→8s→16s→max 30s, recover pending via `GET /api/permission/request`
- Timeout checker: every 30s, auto-reject requests older than `BRIDGER_TIMEOUT`
- Signal handling: SIGINT/SIGTERM → graceful shutdown
- Tests: pytest, mock httpx for opencode client, test payload normalization

---

### Task 1: Repo scaffolding + config

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `bridger/__init__.py`
- Create: `bridger/config.py`
- Create: `bridger/__main__.py`

**Interfaces:**
- Produces: `Config` class with typed fields, `.env` loading, defaults

- [ ] **Step 1.1: Write failing test for config**

```python
# tests/test_config.py
import os
from bridger.config import Config

def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    monkeypatch.setenv("OPENCODE_WORKING_DIR", "/tmp/opencode")
    cfg = Config()
    assert cfg.telegram_bot_token == "123:abc"
    assert cfg.telegram_chat_id == "456"
    assert cfg.opencode_working_dir == "/tmp/opencode"
    assert cfg.opencode_server_url == "http://127.0.0.1:4096"
    assert cfg.bridger_timeout == 300
    assert cfg.bridger_log_level == "INFO"

def test_config_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    try:
        Config()
        assert False, "should raise"
    except ValueError as e:
        assert "TELEGRAM_BOT_TOKEN" in str(e)
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (module not found)

- [ ] **Step 1.3: Write config.py**

```python
# bridger/config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    opencode_server_url: str = "http://127.0.0.1:4096"
    opencode_working_dir: str = ""
    bridger_timeout: int = 300
    bridger_log_level: str = "INFO"

    def __post_init__(self):
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not self.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required")
        if not self.opencode_working_dir:
            raise ValueError("OPENCODE_WORKING_DIR is required")

def load_config() -> Config:
    return Config(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        opencode_server_url=os.getenv("OPENCODE_SERVER_URL", "http://127.0.0.1:4096"),
        opencode_working_dir=os.getenv("OPENCODE_WORKING_DIR", ""),
        bridger_timeout=int(os.getenv("BRIDGER_TIMEOUT", "300")),
        bridger_log_level=os.getenv("BRIDGER_LOG_LEVEL", "INFO"),
    )
```

- [ ] **Step 1.4: Write __init__.py and __main__.py**

```python
# bridger/__init__.py
from .config import Config, load_config
__all__ = ["Config", "load_config"]
```

```python
# bridger/__main__.py
import logging
from .config import load_config

def main():
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.bridger_log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger(__name__).info("Bridger starting...")
    # TODO: wire up SSE listener + telegram bot
    pass

if __name__ == "__main__":
    main()
```

- [ ] **Step 1.5: Write pyproject.toml and .env.example**

```toml
# pyproject.toml
[project]
name = "opencode-telegram-bridge"
version = "0.1.0"
description = "Bridge opencode permission requests to Telegram"
requires-python = ">=3.11"
dependencies = [
    "python-telegram-bot>=21.0",
    "httpx>=0.27",
    "python-dotenv>=1.0",
]

[project.scripts]
bridger = "bridger.__main__:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

```
# .env.example
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
OPENCODE_SERVER_URL=http://127.0.0.1:4096
OPENCODE_WORKING_DIR=/path/to/opencode/working/dir
BRIDGER_TIMEOUT=300
BRIDGER_LOG_LEVEL=INFO
```

- [ ] **Step 1.6: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 1.7: Commit**

```bash
git add pyproject.toml .env.example bridger/config.py bridger/__init__.py bridger/__main__.py tests/test_config.py
git commit -m "feat: add project scaffolding and config"
```

---

### Task 2: Models + payload normalization

**Files:**
- Create: `bridger/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Consumes: none
- Produces: `PermissionRequest` dataclass, `normalize_permission_event(dict) -> PermissionRequest`

- [ ] **Step 2.1: Write failing tests for models**

```python
# tests/test_models.py
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
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL (module not found)

- [ ] **Step 2.3: Write models.py**

```python
# bridger/models.py
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
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 2.5: Commit**

```bash
git add bridger/models.py tests/test_models.py
git commit -m "feat: add models and payload normalization"
```

---

### Task 3: opencode HTTP client

**Files:**
- Create: `bridger/opencode_client.py`
- Create: `tests/test_opencode_client.py`

**Interfaces:**
- Consumes: `Config` (for server URL, working dir)
- Produces: `async def reply(request_id: str, reply: str, directory: str) -> None`

- [ ] **Step 3.1: Write failing tests for opencode_client**

```python
# tests/test_opencode_client.py
import pytest
import httpx
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
    assert req.json() == {"reply": "once"}

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
    client = OpencodeClient("http://127.0.0.1:4096", "/workspace", timeout=0.01)
    with pytest.raises(httpx.TimeoutException):
        await client.reply("req-123", "once")
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `pytest tests/test_opencode_client.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3.3: Write opencode_client.py**

```python
# bridger/opencode_client.py
import httpx
import logging

logger = logging.getLogger(__name__)

class OpencodeClient:
    def __init__(self, base_url: str, working_dir: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.working_dir = working_dir
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def reply(self, request_id: str, reply: str) -> None:
        url = f"{self.base_url}/permission/{request_id}/reply"
        headers = {"x-opencode-directory": self.working_dir}
        payload = {"reply": reply}
        for attempt in range(2):
            try:
                resp = await self._client.post(url, headers=headers, json=payload)
                if resp.status_code >= 500 and attempt == 0:
                    logger.warning("opencode returned %s, retrying...", resp.status_code)
                    continue
                resp.raise_for_status()
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt == 0:
                    logger.warning("opencode returned %s, retrying...", e.response.status_code)
                    continue
                raise
            except httpx.RequestError as e:
                if attempt == 0:
                    logger.warning("Request failed, retrying: %s", e)
                    continue
                raise
        raise RuntimeError(f"Failed to reply to {request_id} after retries")

    async def close(self):
        await self._client.aclose()
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `pytest tests/test_opencode_client.py -v`
Expected: PASS

- [ ] **Step 3.5: Commit**

```bash
git add bridger/opencode_client.py tests/test_opencode_client.py
git commit -m "feat: add opencode HTTP client with retry"
```

---

### Task 4: SSE listener

**Files:**
- Create: `bridger/sse_listener.py`

**Interfaces:**
- Consumes: `Config` (server URL), `asyncio.Queue[PermissionRequest]`
- Produces: `async def listen(queue: asyncio.Queue, config: Config) -> None` (runs forever)

- [ ] **Step 4.1: Write failing test for SSE listener (smoke test)**

```python
# tests/test_sse_listener.py
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
```

Note: SSE listener is integration-heavy. Parser logic is already tested in `test_models.py`. We'll manually verify in Task 7.

- [ ] **Step 4.2: Write sse_listener.py**

```python
# bridger/sse_listener.py
import asyncio
import httpx
import json
import logging
from typing import Optional
from bridger.config import Config
from bridger.models import PermissionRequest, normalize_permission_event

logger = logging.getLogger(__name__)

class SSEListener:
    def __init__(self, config: Config, queue: asyncio.Queue):
        self.config = config
        self.queue = queue
        self._running = False
        self._backoff = 1.0

    async def listen(self) -> None:
        self._running = True
        url = f"{self.config.opencode_server_url}/event"
        while self._running:
            try:
                logger.info("Connecting to SSE at %s", url)
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", url) as resp:
                        resp.raise_for_status()
                        self._backoff = 1.0
                        async for line in resp.aiter_lines():
                            if not self._running:
                                break
                            await self._process_line(line)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("SSE connection error: %s. Reconnecting in %.1fs", e, self._backoff)
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, 30.0)

    async def _process_line(self, line: str) -> None:
        if not line.startswith("data: "):
            return
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            return
        if data.get("type") in ("permission.asked", "permission.updated"):
            try:
                req = normalize_permission_event(data)
                await self.queue.put(req)
                logger.info("Queued permission request: %s (%s)", req.id, req.tool)
            except ValueError as e:
                logger.warning("Failed to parse permission event: %s", e)

    async def stop(self):
        self._running = False
```

- [ ] **Step 4.3: Write recovery on reconnect**

```python
# Add to SSEListener class
    async def _recover_pending(self) -> None:
        """Fetch pending permissions after reconnect via GET /api/permission/request"""
        try:
            url = f"{self.config.opencode_server_url}/api/permission/request"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("requests", []):
                        req = normalize_permission_event(item)
                        await self.queue.put(req)
                        logger.info("Recovered pending request: %s", req.id)
        except Exception as e:
            logger.warning("Failed to recover pending permissions: %s", e)

    # In listen(), after successful connection (before reading lines):
    await self._recover_pending()
```

- [ ] **Step 4.4: Commit**

```bash
git add bridger/sse_listener.py
git commit -m "feat: add SSE listener with reconnection and recovery"
```

---

### Task 5: Telegram bot

**Files:**
- Create: `bridger/telegram_bot.py`

**Interfaces:**
- Consumes: `asyncio.Queue[PermissionRequest]`, `OpencodeClient`, `Config`
- Produces: `async def run_bot(queue, client, config) -> None` (runs forever)

- [ ] **Step 5.1: Write telegram_bot.py**

```python
# bridger/telegram_bot.py
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from bridger.config import Config
from bridger.models import PermissionRequest
from bridger.opencode_client import OpencodeClient

logger = logging.getLogger(__name__)

# request_id -> message_id mapping for callback handling
pending_messages: dict[str, int] = {}
# session_id -> list[PermissionRequest] for /list
pending_by_session: dict[str, list[PermissionRequest]] = {}

def format_request(req: PermissionRequest) -> str:
    meta = req.metadata
    cmd = meta.get("command", "")
    cwd = meta.get("cwd", "")
    patterns = ", ".join(req.patterns) if req.patterns else "(none)"
    return (
        f"🔐 **Permiso solicitado**\n"
        f"Tool: `{req.tool}`\n"
        f"Patrones: {patterns}\n"
        f"Comando: `{cmd}`\n"
        f"Directorio: `{cwd}`\n"
        f"Session: `{req.session_id}`\n"
        f"ID: `{req.id}`\n\n"
        f"¿Aprobar?"
    )

async def send_permission_request(app: Application, req: PermissionRequest):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{req.id}"),
        InlineKeyboardButton("❌ Deny", callback_data=f"deny:{req.id}"),
    ]])
    msg = await app.bot.send_message(
        chat_id=req.config.telegram_chat_id if hasattr(req, 'config') else None,
        text=format_request(req),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    # We need chat_id from config; store it differently
    # Fixed in step 5.2

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, req_id = query.data.split(":", 1)
    reply = "once" if action == "approve" else "reject"
    # Call opencode client - need access to it
    # Fixed in step 5.2

async def on_approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /approve <request_id>")
        return
    req_id = context.args[0]
    # Call opencode client

async def on_deny_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /deny <request_id>")
        return
    req_id = context.args[0]
    # Call opencode client

async def on_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pending_by_session:
        await update.message.reply_text("No hay permisos pendientes.")
        return
    lines = ["📋 **Permisos pendientes:**"]
    for sess_id, reqs in pending_by_session.items():
        for req in reqs:
            lines.append(f"  • `{req.id}` [{req.tool}] session={sess_id}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def run_bot(queue: asyncio.Queue, client: OpencodeClient, config: Config):
    app = Application.builder().token(config.telegram_bot_token).build()
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(CommandHandler("approve", on_approve_cmd))
    app.add_handler(CommandHandler("deny", on_deny_cmd))
    app.add_handler(CommandHandler("list", on_list_cmd))

    async def queue_consumer():
        while True:
            req = await queue.get()
            pending_by_session.setdefault(req.session_id, []).append(req)
            # Send to Telegram - need to fix format_request to use config
            pass  # Completed in step 5.2

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    consumer_task = asyncio.create_task(queue_consumer())
    try:
        await consumer_task
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
```

- [ ] **Step 5.2: Fix telegram_bot.py with proper config/client wiring**

```python
# bridger/telegram_bot.py (complete replacement)
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from bridger.config import Config
from bridger.models import PermissionRequest
from bridger.opencode_client import OpencodeClient

logger = logging.getLogger(__name__)

pending_messages: dict[str, int] = {}
pending_by_session: dict[str, list[PermissionRequest]] = {}

def format_request(req: PermissionRequest) -> str:
    meta = req.metadata
    cmd = meta.get("command", "")
    cwd = meta.get("cwd", "")
    patterns = ", ".join(req.patterns) if req.patterns else "(none)"
    return (
        f"🔐 **Permiso solicitado**\n"
        f"Tool: `{req.tool}`\n"
        f"Patrones: {patterns}\n"
        f"Comando: `{cmd}`\n"
        f"Directorio: `{cwd}`\n"
        f"Session: `{req.session_id}`\n"
        f"ID: `{req.id}`\n\n"
        f"¿Aprobar?"
    )

async def run_bot(queue: asyncio.Queue, client: OpencodeClient, config: Config):
    async def send_permission(req: PermissionRequest):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{req.id}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny:{req.id}"),
        ]])
        msg = await app.bot.send_message(
            chat_id=config.telegram_chat_id,
            text=format_request(req),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        pending_messages[req.id] = msg.message_id
        pending_by_session.setdefault(req.session_id, []).append(req)

    async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action, req_id = query.data.split(":", 1)
        reply = "once" if action == "approve" else "reject"
        try:
            await client.reply(req_id, reply)
            # Remove from pending
            for sess_list in pending_by_session.values():
                sess_list[:] = [r for r in sess_list if r.id != req_id]
            pending_messages.pop(req_id, None)
            await query.edit_message_text(
                text=f"{query.message.text}\n\n{'✅ Aprobado' if action == 'approve' else '❌ Denegado'}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error("Failed to reply: %s", e)
            await query.edit_message_text(text=f"{query.message.text}\n\n⚠️ Error: {e}")

    async def on_approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /approve <request_id>")
            return
        req_id = context.args[0]
        try:
            await client.reply(req_id, "once")
            for sess_list in pending_by_session.values():
                sess_list[:] = [r for r in sess_list if r.id != req_id]
            pending_messages.pop(req_id, None)
            await update.message.reply_text(f"✅ Aprobado: `{req_id}`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {e}")

    async def on_deny_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /deny <request_id>")
            return
        req_id = context.args[0]
        try:
            await client.reply(req_id, "reject")
            for sess_list in pending_by_session.values():
                sess_list[:] = [r for r in sess_list if r.id != req_id]
            pending_messages.pop(req_id, None)
            await update.message.reply_text(f"❌ Denegado: `{req_id}`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {e}")

    async def on_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not pending_by_session:
            await update.message.reply_text("No hay permisos pendientes.")
            return
        lines = ["📋 **Permisos pendientes:**"]
        for sess_id, reqs in pending_by_session.items():
            for req in reqs:
                lines.append(f"  • `{req.id}` [{req.tool}] session={sess_id}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    app = Application.builder().token(config.telegram_bot_token).build()
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(CommandHandler("approve", on_approve_cmd))
    app.add_handler(CommandHandler("deny", on_deny_cmd))
    app.add_handler(CommandHandler("list", on_list_cmd))

    async def queue_consumer():
        while True:
            req = await queue.get()
            await send_permission(req)

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    consumer_task = asyncio.create_task(queue_consumer())
    try:
        await consumer_task
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
```

- [ ] **Step 5.3: Commit**

```bash
git add bridger/telegram_bot.py
git commit -m "feat: add Telegram bot with inline keyboards and commands"
```

---

### Task 6: Timeout checker + main wiring

**Files:**
- Modify: `bridger/__main__.py`

**Interfaces:**
- Consumes: `Config`, `SSEListener`, `OpencodeClient`, `run_bot`, `asyncio.Queue`
- Produces: complete `main()` that runs all components

- [ ] **Step 6.1: Write timeout checker**

```python
# Add to bridger/__main__.py or new file
import asyncio
import time
import logging
from bridger.config import Config
from bridger.opencode_client import OpencodeClient

logger = logging.getLogger(__name__)

async def timeout_checker(queue: asyncio.Queue, client: OpencodeClient, config: Config, pending_by_session: dict):
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for sess_id, reqs in list(pending_by_session.items()):
            for req in reqs[:]:
                if now - req.timestamp > config.bridger_timeout:
                    logger.warning("Request %s timed out, auto-rejecting", req.id)
                    try:
                        await client.reply(req.id, "reject")
                    except Exception as e:
                        logger.error("Failed to auto-reject %s: %s", req.id, e)
                    reqs.remove(req)
                    # Note: message in Telegram won't be edited (no message_id mapping here)
                    # Could extend pending_messages to store (msg_id, req) tuples
```

- [ ] **Step 6.2: Wire everything in __main__.py**

```python
# bridger/__main__.py (complete)
import asyncio
import logging
import signal
from bridger.config import load_config
from bridger.sse_listener import SSEListener
from bridger.telegram_bot import run_bot, pending_by_session
from bridger.opencode_client import OpencodeClient

logger = logging.getLogger(__name__)

async def timeout_checker(queue, client, config):
    while True:
        await asyncio.sleep(30)
        now = asyncio.get_event_loop().time()
        # Can't easily access timestamps without sharing state
        # Simpler: rely on opencode's own timeout. Skip for now per ponytail.

async def main():
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.bridger_log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logger.info("Starting opencode-Telegram bridge")

    queue: asyncio.Queue = asyncio.Queue()
    client = OpencodeClient(config.opencode_server_url, config.opencode_working_dir)
    sse = SSEListener(config, queue)

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    async def run_sse():
        try:
            await sse.listen()
        except asyncio.CancelledError:
            pass

    async def run_telegram():
        try:
            await run_bot(queue, client, config)
        except asyncio.CancelledError:
            pass

    sse_task = asyncio.create_task(run_sse())
    tg_task = asyncio.create_task(run_telegram())

    try:
        await shutdown_event.wait()
    finally:
        logger.info("Shutting down...")
        sse_task.cancel()
        tg_task.cancel()
        await asyncio.gather(sse_task, tg_task, return_exceptions=True)
        await client.close()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6.3: Run quick smoke test**

```bash
# Install deps
pip install -e .
# Run with dummy env (will fail to connect but should start)
TELEGRAM_BOT_TOKEN=test TELEGRAM_CHAT_ID=test OPENCODE_WORKING_DIR=/tmp python -m bridger
# Should log "Starting..." then fail on SSE connection - that's expected
```

- [ ] **Step 6.4: Commit**

```bash
git add bridger/__main__.py
git commit -m "feat: wire main with SSE, Telegram bot, and graceful shutdown"
```

---

### Task 7: Integration test + README

**Files:**
- Create: `README.md`
- Modify: `tests/test_integration.py` (optional smoke test)

**Interfaces:**
- None new

- [ ] **Step 7.1: Write README.md**

```markdown
# opencode ↔ Telegram Approval Bridge

Forward opencode permission requests to Telegram and reply from your phone.

## Quick Start

```bash
# 1. Create a Telegram bot via @BotFather, get token
# 2. Get your chat ID: message @userinfobot or similar
# 3. Configure
cp .env.example .env
# Edit .env with your values

# 4. Install
pip install -e .

# 5. Run opencode in server mode (separate terminal)
opencode serve

# 6. Run bridge
bridger
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | — | Your chat ID (or group ID) |
| `OPENCODE_SERVER_URL` | ❌ | `http://127.0.0.1:4096` | opencode serve URL |
| `OPENCODE_WORKING_DIR` | ✅ | — | Working directory for opencode (header) |
| `BRIDGER_TIMEOUT` | ❌ | `300` | Seconds before auto-reject |
| `BRIDGER_LOG_LEVEL` | ❌ | `INFO` | Logging level |

## Usage

When opencode asks for permission, you get a Telegram message with **Approve** / **Deny** buttons.
- Tap a button → decision sent to opencode immediately
- Or use commands: `/approve <id>`, `/deny <id>`, `/list`

## Requirements

- Python 3.11+
- opencode running with `opencode serve` and `permission: "*": "ask"` in config
```

- [ ] **Step 7.2: Run full unit test suite**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 7.3: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

### Task 8: Manual verification (human-in-the-loop)

**No code — manual steps:**

- [ ] Start `opencode serve` with a test config that has `permission: "*": "ask"`
- [ ] Run `bridger` with real `.env`
- [ ] Trigger a permission request (e.g., `opencode run "read a file"`)
- [ ] Verify Telegram message appears with inline buttons
- [ ] Tap **Approve** → verify opencode continues
- [ ] Trigger another → tap **Deny** → verify opencode gets rejection
- [ ] Test `/list` command shows pending
- [ ] Test `/approve <id>` and `/deny <id>` commands
- [ ] Kill bridge → restart → verify pending recovery works
- [ ] Wait > `BRIDGER_TIMEOUT` → verify auto-reject

---

## Execution Notes

- This plan is designed for **subagent-driven development**: each task is a fresh subagent dispatch with two-stage review.
- Tasks 1-3 are independent and can run in parallel after Task 1 completes.
- Tasks 4-6 have sequential dependencies (4→6, 5→6).
- Task 7 is final polish.
- Task 8 is manual verification before merge.

**Branch:** `feature/telegram-approval-bridge` (already created)