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