"""Async wrapper around the ohmepy library (PyPI: ohme)."""

import logging
from ohme import OhmeApiClient

import config

logger = logging.getLogger(__name__)

DISCONNECTED_MODE = "DISCONNECTED"


async def get_session_mode(client: OhmeApiClient) -> str:
    """Return the raw Ohme session mode string, e.g. 'DISCONNECTED' or 'SMART_CHARGE'."""
    await client.async_get_charge_session()
    mode = client._charge_session.get("mode", DISCONNECTED_MODE)
    logger.debug("Ohme session mode: %s", mode)
    return mode


def is_connected(mode: str) -> bool:
    """True when the car is physically plugged into the Ohme charger."""
    return mode != DISCONNECTED_MODE


async def set_target(client: OhmeApiClient, current_soc: int, target_percent: int) -> None:
    """Calculate charge needed and set Ohme to add that amount (does not send SOC to charger)."""
    # async_update_device_info must run first to populate _cars and serial (needed for internal API calls).
    await client.async_update_device_info()
    await client.async_get_charge_session()
    topup = target_percent - current_soc
    await client.async_set_target(target_percent=topup)
    await client.async_get_charge_session()  # refresh so client.slots reflects the new schedule
    logger.info(
        "Ohme target set: current SOC=%s%%, target=%s%%, top-up=%s%%",
        current_soc,
        target_percent,
        topup,
    )


async def make_client() -> OhmeApiClient:
    """Create and authenticate a fresh Ohme client."""
    client = OhmeApiClient(config.OHME_EMAIL, config.OHME_PASSWORD)
    await client.async_login()
    return client
