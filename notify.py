import logging
import aiohttp
import config

logger = logging.getLogger(__name__)


async def send(message: str) -> None:
    """Send a notification via ntfy. No-ops silently if NTFY_TOPIC is not configured."""
    if not config.NTFY_TOPIC:
        return

    url = f"{config.NTFY_URL}/{config.NTFY_TOPIC}"
    headers = {"Authorization": f"Bearer {config.NTFY_TOKEN}"} if config.NTFY_TOKEN else {}
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=message.encode(), headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("ntfy returned HTTP %s", resp.status)
    except Exception:
        logger.warning("Failed to send ntfy notification", exc_info=True)
