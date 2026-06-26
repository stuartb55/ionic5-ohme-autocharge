"""Unified notification dispatch — fans a message out to every channel.

Currently ntfy (``ntfy.send``) and web push (``push.send``). Each channel is
independently optional and swallows its own errors, so a missing/broken channel
never affects the others or the caller. Call sites use ``notify.send`` instead
of a specific channel so new channels need no further wiring.
"""

from __future__ import annotations

from typing import Optional

import ntfy
import push


async def send(message: str, *, title: Optional[str] = None, priority: Optional[str] = None) -> None:
    await ntfy.send(message, title=title, priority=priority)
    await push.send(message, title=title, priority=priority)
