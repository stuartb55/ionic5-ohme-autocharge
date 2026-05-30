"""
Monitors the Ohme charger for a plug-in event, then fetches the vehicle's
current battery SOC from Hyundai Bluelink and sets the Ohme charge target.

Run continuously:  python main.py
Run once (CI/test): python main.py --once
"""

import argparse
import asyncio
import logging

import bluelink
import ohme_client
import ntfy
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def handle_plugin_event(client) -> bool:
    """Called once per session when the car transitions from unplugged → plugged in.
    Returns True only when Ohme has been successfully updated (or no update was needed)."""
    logger.info("Plug-in detected — fetching battery SOC from Bluelink...")
    try:
        # hyundai_kia_connect_api is synchronous; run it in a thread to avoid blocking the loop
        soc = await asyncio.to_thread(bluelink.get_battery_percentage)
    except Exception:
        logger.exception("Failed to fetch SOC from Hyundai Bluelink — will retry next poll")
        return False

    if soc >= config.CHARGE_TARGET:
        logger.info(
            "SOC %s%% already at or above target %s%% — no action needed",
            soc,
            config.CHARGE_TARGET,
        )
        return True

    logger.info(
        "SOC %s%% is below target %s%% — configuring Ohme...",
        soc,
        config.CHARGE_TARGET,
    )
    try:
        await ohme_client.set_target(client, current_soc=soc, target_percent=config.CHARGE_TARGET)
        vehicle_name = client.current_vehicle or "EV"
        await ntfy.send(f"{vehicle_name} plugged in at {soc}% — Ohme target set to {config.CHARGE_TARGET}%")
        return True
    except Exception:
        logger.exception("Failed to set Ohme charge target — will retry next poll")
        return False


async def run_loop() -> None:
    logger.info(
        "Starting poll loop (interval=%ss, target=%s%%)",
        config.POLL_INTERVAL,
        config.CHARGE_TARGET,
    )
    if config.NTFY_TOPIC:
        logger.info("Ntfy notifications enabled (url=%s, topic=%s)", config.NTFY_URL, config.NTFY_TOPIC)
    else:
        logger.info("Ntfy notifications disabled — set NTFY_TOPIC to enable")

    client = await ohme_client.make_client()

    was_connected = False
    session_handled = False

    try:
        while True:
            try:
                mode = await ohme_client.get_session_mode(client)
                now_connected = ohme_client.is_connected(mode)

                if now_connected and not was_connected:
                    # Transition: disconnected → connected (car just plugged in)
                    session_handled = False

                if now_connected and not session_handled:
                    session_handled = await handle_plugin_event(client)

                if not now_connected and was_connected:
                    logger.info("Car unplugged (mode=%s). Waiting for next session.", mode)
                    session_handled = False

                was_connected = now_connected

            except Exception:
                logger.exception("Error during poll — will retry next interval")

            await asyncio.sleep(config.POLL_INTERVAL)
    finally:
        await client.close()


async def run_once() -> None:
    """Single execution: fetch SOC and set Ohme target regardless of plug state."""
    logger.info("Running in one-shot mode")
    client = await ohme_client.make_client()
    try:
        await handle_plugin_event(client)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch SOC and set target once then exit (skips plug-in detection)",
    )
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(run_loop())
