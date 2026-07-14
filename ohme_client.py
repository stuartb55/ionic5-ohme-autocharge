"""Async wrapper around the ohmepy library (PyPI: ohme)."""

import asyncio
import logging
from ohme import ChargerStatus, OhmeApiClient

import config

logger = logging.getLogger(__name__)


async def bounded(awaitable):
    """Await one Ohme network operation with the configured upper bound.

    Keeping the timeout in this module makes it difficult for a new Ohme call
    site to accidentally bypass the reliability boundary.  ``wait_for``
    cancels the in-flight coroutine on expiry; callers' ``async with`` blocks
    can then release ``store.client_lock`` normally.
    """
    return await asyncio.wait_for(awaitable, config.UPSTREAM_TIMEOUT)


async def update_device_info(client: OhmeApiClient) -> None:
    await bounded(client.async_update_device_info())


async def get_charge_summary(client: OhmeApiClient, **kwargs):
    return await bounded(client.async_get_charge_summary(**kwargs))


async def pause_charge(client: OhmeApiClient) -> None:
    await bounded(client.async_pause_charge())


async def resume_charge(client: OhmeApiClient) -> None:
    await bounded(client.async_resume_charge())


async def set_max_charge(client: OhmeApiClient, enabled: bool) -> None:
    await bounded(client.async_max_charge(enabled))


async def close_client(client: OhmeApiClient | None) -> None:
    """Best-effort bounded cleanup for fully or partially initialised clients."""
    if client is None:
        return
    try:
        await bounded(client.close())
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Could not close Ohme client cleanly", exc_info=True)


async def get_charger_status(client: OhmeApiClient) -> ChargerStatus:
    """Refresh the charge session and return the charger's status.

    The network refresh is bounded by ``config.UPSTREAM_TIMEOUT`` so a hung Ohme
    request can't stall the poll loop — a timeout raises ``TimeoutError``, which
    the loop handles as a failed poll (keeps the last-known-good snapshot).
    """
    await bounded(client.async_get_charge_session())
    try:
        status = client.status
    except KeyError:
        # Session response without a mode — same graceful default the previous
        # raw-mode implementation used.
        status = ChargerStatus.UNPLUGGED
    logger.debug("Ohme charger status: %s", status)
    return status


def is_connected(status: ChargerStatus) -> bool:
    """True when the car is physically plugged into the Ohme charger."""
    return status is not ChargerStatus.UNPLUGGED


def is_charging(status: ChargerStatus) -> bool:
    """True when the charger is actively delivering energy to the car."""
    return status is ChargerStatus.CHARGING


async def set_target(
    client: OhmeApiClient,
    current_soc: int,
    target_percent: int,
    target_time: tuple[int, int] | None = None,
) -> None:
    """Calculate charge needed and set Ohme to add that amount (does not send SOC to charger).

    ``target_time`` is an optional ``(hour, minute)`` "ready-by" time; when given,
    Ohme schedules the charge to complete by then instead of on its default
    smart schedule.
    """
    # async_update_device_info must run first to populate _cars and serial (needed for internal API calls).
    await update_device_info(client)
    await bounded(client.async_get_charge_session())
    # A cancelled one-off override may restore a normal target that the battery
    # has already reached. Ohme represents "stop here" as a zero top-up; never
    # send a negative percentage to its internal API.
    topup = max(0, target_percent - current_soc)
    await bounded(client.async_set_target(target_percent=topup, target_time=target_time))
    # Refresh so client.slots reflects the new schedule.  This is deliberately
    # a separate bounded operation: a successful write followed by a hung read
    # is reported as an uncertain/failed apply and retried safely by the plug-in
    # detector instead of holding the shared client lock forever.
    await bounded(client.async_get_charge_session())
    logger.info(
        "Ohme target set: current SOC=%s%%, target=%s%%, top-up=%s%%, ready_by=%s",
        current_soc,
        target_percent,
        topup,
        target_time,
    )


async def make_client() -> OhmeApiClient:
    """Create and authenticate a fresh Ohme client."""
    client = OhmeApiClient(config.OHME_EMAIL, config.OHME_PASSWORD)
    try:
        await bounded(client.async_login())
        return client
    except BaseException:
        # Login can allocate an HTTP session before failing or being cancelled.
        # Do not leak it across an unbounded retry loop.
        try:
            await close_client(client)
        except asyncio.CancelledError:
            # Preserve the original cancellation after cleanup was attempted.
            pass
        raise
