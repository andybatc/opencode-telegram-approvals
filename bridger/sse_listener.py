# bridger/sse_listener.py
import asyncio
import httpx
import json
import logging
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
                        await self._recover_pending()
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

    async def _recover_pending(self) -> None:
        """Fetch pending permissions after reconnect via GET /api/permission/request"""
        try:
            url = f"{self.config.opencode_server_url}/api/permission/request"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        try:
                            req = normalize_permission_event(item)
                            await self.queue.put(req)
                            logger.info("Recovered pending request: %s", req.id)
                        except Exception as e:
                            logger.warning("Failed to parse pending request: %s", e)
        except Exception as e:
            logger.warning("Failed to recover pending permissions: %s", e)
