# bridger/opencode_client.py
import httpx
import logging

from .config import Config

logger = logging.getLogger(__name__)

VALID_REPLIES = {"once", "always", "reject"}


class OpencodeClient:
    def __init__(self, config: Config, timeout: float | None = None):
        self.base_url = config.opencode_server_url.rstrip("/")
        self.timeout = timeout if timeout is not None else config.bridger_timeout
        self._client = httpx.AsyncClient(timeout=self.timeout)

    @classmethod
    def from_config(cls, config: Config) -> "OpencodeClient":
        return cls(config)

    async def reply(self, request_id: str, reply: str, directory: str) -> None:
        if reply not in VALID_REPLIES:
            raise ValueError(f"Invalid reply: {reply!r}, must be one of {VALID_REPLIES}")
        url = f"{self.base_url}/permission/{request_id}/reply"
        headers = {"x-opencode-directory": directory}
        payload = {"reply": reply}
        for attempt in range(2):
            try:
                resp = await self._client.post(url, headers=headers, json=payload)
                if 500 <= resp.status_code < 600 and attempt == 0:
                    logger.warning("opencode returned %s, retrying...", resp.status_code)
                    continue
                resp.raise_for_status()
                return
            except httpx.HTTPStatusError as e:
                if 500 <= e.response.status_code < 600 and attempt == 0:
                    logger.warning("opencode returned %s, retrying...", e.response.status_code)
                    continue
                raise
        raise RuntimeError(f"Failed to reply to {request_id} after retries")

    async def close(self):
        await self._client.aclose()
