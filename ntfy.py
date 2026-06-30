import logging
import aiohttp
import config

logger = logging.getLogger(__name__)


async def send(
    message: str,
    *,
    title: str | None = None,
    priority: str | None = None,
    tags: str | None = None,
) -> None:
    """Send a notification via ntfy. No-ops silently if NTFY_TOPIC is not configured.

    ``priority`` is an ntfy priority name ("min" … "max"); use "high" for
    alerts that should break through quiet phone settings. ``tags`` is a
    comma-separated list of ntfy tags — emoji shortcodes like
    ``"electric_plug"`` render as an icon in front of the title on every
    client (unlike markdown, which phones show raw), so it's the readable way
    to make a notification's type recognisable at a glance.
    """
    if not config.NTFY_TOPIC:
        return

    url = f"{config.NTFY_URL}/{config.NTFY_TOPIC}"
    headers = {"Authorization": f"Bearer {config.NTFY_TOKEN}"} if config.NTFY_TOKEN else {}
    if title:
        headers["X-Title"] = title
    if priority:
        headers["X-Priority"] = priority
    if tags:
        headers["X-Tags"] = tags
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=message.encode(), headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("ntfy returned HTTP %s", resp.status)
    except Exception:
        logger.warning("Failed to send ntfy notification", exc_info=True)
