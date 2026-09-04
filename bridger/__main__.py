import asyncio
import logging
import signal
import time

from bridger.config import load_config
from bridger.opencode_client import OpencodeClient
from bridger.sse_listener import SSEListener
from bridger.telegram_bot import run_bot, pending_by_session

logger = logging.getLogger(__name__)


async def timeout_checker(client: OpencodeClient, config):
    """Auto-reject permission requests that exceed the timeout."""
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for reqs in list(pending_by_session.values()):
            for req in reqs[:]:
                if now - req.timestamp > config.bridger_timeout:
                    logger.warning("Request %s timed out, auto-rejecting", req.id)
                    try:
                        await client.reply(req.id, "reject", config.opencode_working_dir)
                    except Exception as e:
                        logger.error("Failed to auto-reject %s: %s", req.id, e)
                    reqs.remove(req)
        for sid in list(pending_by_session):
            if not pending_by_session[sid]:
                del pending_by_session[sid]


async def main():
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.bridger_log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting opencode-Telegram bridge")

    queue: asyncio.Queue = asyncio.Queue()
    client = OpencodeClient(config)
    sse = SSEListener(config, queue)

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    sse_task = asyncio.create_task(sse.listen())
    tg_task = asyncio.create_task(run_bot(queue, client, config))
    timeout_task = asyncio.create_task(timeout_checker(client, config))

    try:
        await shutdown_event.wait()
    finally:
        logger.info("Shutting down...")
        for t in (sse_task, tg_task, timeout_task):
            t.cancel()
        await asyncio.gather(sse_task, tg_task, timeout_task, return_exceptions=True)
        await client.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
