"""Async wrapper around the ohmepy library (PyPI: ohme)."""

import asyncio
import logging
from ohme import ChargerStatus, OhmeApiClient

import config

logger = logging.getLogger(__name__)


async def get_charger_status(client: OhmeApiClient) -> ChargerStatus:
    """Refresh the charge session and return the charger's status.

    The network refresh is bounded by ``config.UPSTREAM_TIMEOUT`` so a hung Ohme
    request can't stall the poll loop — a timeout raises ``TimeoutError``, which
    the loop handles as a failed poll (keeps the last-known-good snapshot).
    """
    await asyncio.wait_for(client.async_get_charge_session(), config.UPSTREAM_TIMEOUT)
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
    await client.async_update_device_info()
    await client.async_get_charge_session()
    topup = target_percent - current_soc
    await client.async_set_target(target_percent=topup, target_time=target_time)
    await client.async_get_charge_session()  # refresh so client.slots reflects the new schedule
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
    await client.async_login()
    return client
