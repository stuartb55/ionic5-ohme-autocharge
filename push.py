"""Optional web push notifications (VAPID / Web Push protocol).

Enabled only when both VAPID keys are configured; otherwise every function is a
no-op, mirroring the graceful-degradation pattern of ntfy/db. Browser push
subscriptions are persisted to a small JSON file so they survive restarts.

Sends are best-effort: pywebpush is synchronous, so each delivery runs in a
thread; failures are swallowed and subscriptions the push service reports as
gone (404/410) are pruned.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import threading
from typing import Any, Optional

import config

logger = logging.getLogger(__name__)

# Guards the subscriptions file (read-modify-write from request handlers and the
# poll loop's send path, both of which can run concurrently).
_lock = threading.Lock()


def is_enabled() -> bool:
    """True when web push is configured (both VAPID keys present)."""
    return bool(config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY)


def public_key() -> str:
    """The VAPID application server key the browser subscribes with."""
    return config.VAPID_PUBLIC_KEY


def _load() -> list[dict]:
    try:
        with open(config.PUSH_SUBSCRIPTIONS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("Ignoring unreadable push subscriptions file", exc_info=True)
        return []


def _save(subscriptions: list[dict]) -> bool:
    path = config.PUSH_SUBSCRIPTIONS_PATH
    try:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".push-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(subscriptions, fh)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    except OSError:
        logger.warning("Could not persist push subscriptions to %s", path, exc_info=True)
        return False


def _endpoint(sub: dict) -> Optional[str]:
    ep = sub.get("endpoint")
    return ep if isinstance(ep, str) else None


def add_subscription(subscription: dict) -> bool:
    """Store a browser subscription (replacing any with the same endpoint)."""
    endpoint = _endpoint(subscription)
    if not endpoint:
        return False
    with _lock:
        subs = [s for s in _load() if _endpoint(s) != endpoint]
        subs.append(subscription)
        return _save(subs)


def remove_subscription(endpoint: str) -> bool:
    """Drop the subscription with the given endpoint."""
    with _lock:
        subs = [s for s in _load() if _endpoint(s) != endpoint]
        return _save(subs)


def _send_one(subscription: dict, payload: str) -> Optional[str]:
    """Deliver to one subscription. Returns the endpoint to prune (gone), or None."""
    from pywebpush import WebPushException, webpush  # lazy: only needed when enabled

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=config.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": config.VAPID_SUBJECT},
        )
        return None
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            return _endpoint(subscription)  # subscription is gone — prune it
        logger.warning("Web push delivery failed (status=%s)", status, exc_info=True)
        return None
    except Exception:
        logger.warning("Web push delivery error", exc_info=True)
        return None


def _send_all(message: str, title: Optional[str]) -> None:
    """Synchronous fan-out to every subscription (runs in a worker thread)."""
    payload = json.dumps({"title": title or "Autocharge", "body": message})
    with _lock:
        subs = _load()
    if not subs:
        return
    gone = {ep for ep in (_send_one(sub, payload) for sub in subs) if ep}
    if gone:
        with _lock:
            remaining = [s for s in _load() if _endpoint(s) not in gone]
            _save(remaining)
        logger.info("Pruned %d expired push subscription(s)", len(gone))


async def send(message: str, *, title: Optional[str] = None, priority: Optional[str] = None) -> None:
    """Send a push to all subscriptions. No-op when disabled. Never raises.

    ``priority`` is accepted for a uniform notification interface but unused here.
    """
    if not is_enabled():
        return
    try:
        await asyncio.to_thread(_send_all, message, title)
    except Exception:  # noqa: BLE001 - a push failure must never disrupt the caller
        logger.warning("Web push send failed", exc_info=True)
